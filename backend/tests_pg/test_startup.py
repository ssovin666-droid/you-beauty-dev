"""Старт API и бота не должен зависать.

Сценарии, из-за которых тестовый API отвечал 502:
старт во время первого импорта каталога и
одновременный старт API и бота.
"""

import threading
import time

import pytest
from sqlalchemy import select, text

from app.core.locks import advisory_lock
from app.db import schema
from app.db.session import SessionLocal, engine
from app.main import prepare_database
from app.models import Brand, Product, StoreCatalogItem
from app.services.golden_apple_feed import sync_golden_apple_feed
from app.services.product_matcher import link_product_to_best_match

from tests_pg.conftest import feed_item


ITEMS = [feed_item(i, "Clarins", f"Clarins Serum {i}", 1000 + i, volume=50) for i in range(1, 6)]


def _hold_import_transaction(release: threading.Event, started: threading.Event):
    """Имитирует долгую транзакцию импорта, держащую строки каталога."""

    with engine.connect() as connection:
        connection.execute(text("UPDATE store_catalog_items SET synced_at = now()"))
        connection.execute(text("SELECT id FROM stores FOR UPDATE"))
        started.set()
        release.wait(30)
        connection.rollback()


def test_api_startup_does_not_wait_for_running_import(fake_feed):
    fake_feed.set_items(ITEMS)
    sync_golden_apple_feed()

    release, started = threading.Event(), threading.Event()
    holder = threading.Thread(target=_hold_import_transaction, args=(release, started))
    holder.start()
    started.wait(5)
    try:
        t0 = time.monotonic()
        prepare_database()
        schema.ensure_job_schema(engine)
        assert time.monotonic() - t0 < 3
    finally:
        release.set()
        holder.join()


def test_startup_skips_schema_lock_when_schema_is_complete():
    # Схему держит другой процесс (например, бот строит индексы).
    with engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": schema.SCHEMA_LOCK_KEY})
        other.commit()
        try:
            t0 = time.monotonic()
            schema.ensure_job_schema(engine)
            assert time.monotonic() - t0 < 2
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": schema.SCHEMA_LOCK_KEY})
            other.commit()


def test_schema_lock_wait_is_bounded(monkeypatch):
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE store_catalog_items DROP COLUMN content_hash"))
    monkeypatch.setattr(schema, "SCHEMA_LOCK_WAIT_SECONDS", 2)

    with engine.connect() as other:
        other.execute(text("SELECT pg_advisory_lock(:k)"), {"k": schema.SCHEMA_LOCK_KEY})
        other.commit()
        try:
            t0 = time.monotonic()
            with pytest.raises(RuntimeError):
                schema.ensure_job_schema(engine)
            assert time.monotonic() - t0 < 6
        finally:
            other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": schema.SCHEMA_LOCK_KEY})
            other.commit()

    schema.ensure_job_schema(engine)
    with engine.connect() as connection:
        columns = {r[0] for r in connection.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='store_catalog_items'"))}
    assert "content_hash" in columns


def test_concurrent_api_and_bot_first_start_on_old_schema():
    with engine.begin() as connection:
        for column in ("content_hash", "changed_version", "match_changed_version"):
            connection.execute(text(f"ALTER TABLE store_catalog_items DROP COLUMN {column}"))
        connection.execute(text("DROP TABLE discount_notifications, job_runs, job_state, product_match_misses, catalog_sync_runs"))

    errors = []

    def run(fn):
        try:
            fn()
        except Exception as exc:  # pragma: no cover
            errors.append(exc)

    api = threading.Thread(target=run, args=(lambda: (prepare_database(), schema.ensure_job_schema(engine)),))
    bot = threading.Thread(target=run, args=(lambda: (schema.ensure_job_schema(engine), schema.ensure_job_indexes(engine)),))
    t0 = time.monotonic()
    api.start(); bot.start(); api.join(30); bot.join(30)
    assert not api.is_alive() and not bot.is_alive()
    assert not errors
    assert time.monotonic() - t0 < 10
    assert schema._schema_complete(engine)


def test_user_request_does_not_wait_for_import_row_locks(db, fake_feed):
    fake_feed.set_items(ITEMS)
    sync_golden_apple_feed()

    brand = db.scalar(select(Brand).where(Brand.name == "Clarins")) or Brand(name="Clarins", slug="clarins")
    db.add(brand)
    db.flush()
    product = Product(brand_id=brand.id, name="Serum 3", size="50 мл", canonical_key="clarins-serum-3")
    db.add(product)
    db.commit()

    release, started = threading.Event(), threading.Event()
    holder = threading.Thread(target=_hold_import_transaction, args=(release, started))
    holder.start()
    started.wait(5)
    try:
        session = SessionLocal()
        t0 = time.monotonic()
        result = link_product_to_best_match(session, session.get(Product, product.id))
        elapsed = time.monotonic() - t0
        session.close()
        assert result.matched is True
        assert result.offer_id is None  # связь отложена
        assert elapsed < 6
    finally:
        release.set()
        holder.join()

    # После импорта связь создаётся как обычно.
    session = SessionLocal()
    result = link_product_to_best_match(session, session.get(Product, product.id))
    assert result.offer_id is not None
    linked = session.scalar(select(StoreCatalogItem.product_id).where(StoreCatalogItem.id == result.catalog_item_id))
    assert linked == product.id
    session.close()


def test_index_build_does_not_block_and_releases_timeouts():
    with advisory_lock(engine, schema.INDEX_LOCK_NAME) as acquired:
        assert acquired
        t0 = time.monotonic()
        schema.ensure_job_indexes(engine)  # другой процесс строит — пропуск
        assert time.monotonic() - t0 < 1

    schema.ensure_job_indexes(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SHOW lock_timeout")).scalar() == "0"
        assert connection.execute(text("SHOW statement_timeout")).scalar() == "0"
