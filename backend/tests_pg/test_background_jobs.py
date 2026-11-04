import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, update

from app.core.locks import advisory_lock
from app.core.metrics import JobMetrics
from app.db.session import SessionLocal, engine
from app.models import (
    Brand,
    CatalogSyncRun,
    DiscountNotification,
    ListType,
    Offer,
    Product,
    ProductMatchMiss,
    StoreCatalogItem,
    TrackedItem,
    User,
)
from app.services import discount_monitor, golden_apple_feed
from app.services.discount_monitor import (
    apply_catalog_version,
    claim_notifications,
    deliver_notifications,
    initialize_new_subscriptions,
)
from app.services.golden_apple_feed import sync_golden_apple_feed
from app.services.product_matcher import link_product_to_best_match

from tests_pg.conftest import feed_item


# -------------------------
# helpers
# -------------------------


def make_user(db, telegram_user_id):
    user = User(telegram_user_id=telegram_user_id, username=f"u{telegram_user_id}")
    db.add(user)
    db.commit()
    return user


def make_product(db, brand_name, name, size=None, variant=None):
    brand = db.scalar(select(Brand).where(Brand.name == brand_name))
    if brand is None:
        brand = Brand(name=brand_name, slug=brand_name.lower())
        db.add(brand)
        db.flush()
    product = Product(
        brand_id=brand.id,
        name=name,
        size=size,
        variant=variant,
        canonical_key=f"{brand_name}|{name}|{size}|{variant}".lower(),
    )
    db.add(product)
    db.commit()
    return product


def track(db, user, product, list_type=ListType.wishlist):
    item = TrackedItem(
        user_id=user.id,
        product_id=product.id,
        list_type=list_type,
        notifications_enabled=True,
    )
    db.add(item)
    db.commit()
    return item


def run_cycle(bot):
    """Один проход monitor'а, как в bot.main, с метриками."""

    metrics = JobMetrics("test_cycle")
    with metrics:
        db = SessionLocal()
        try:
            init = initialize_new_subscriptions(db)
            version = apply_catalog_version(db)
        finally:
            db.close()
        delivery = asyncio.run(deliver_notifications(bot, SessionLocal))
    return metrics, init, version, delivery


BASE_ITEMS = [
    feed_item(1, "Clarins", "Clarins Double Serum", 2500, volume=50),
    feed_item(2, "Clarins", "Clarins Hydra Essentiel Cream", 3100, volume=50),
    feed_item(3, "Dior", "Dior Addict Lip Glow", 3900, shade="001 Pink"),
    feed_item(4, "Dior", "Dior Forever Foundation", 5200, volume=30, shade="1N"),
]


def items_with(**overrides):
    items = [dict(item) for item in BASE_ITEMS]
    for item in items:
        if item["id"] in overrides:
            item.update(overrides[item["id"]])
    return items


# -------------------------
# 1. неизменный каталог
# -------------------------


def test_no_repeated_heavy_search_when_catalog_unchanged(db, fake_feed, fake_bot):
    fake_feed.set_items(BASE_ITEMS)
    assert sync_golden_apple_feed()["status"] == "published"

    user = make_user(db, 1001)
    missing = make_product(db, "Clarins", "Totally Unknown Balm", size="15 мл")
    track(db, user, missing)

    metrics, init, _version, _delivery = run_cycle(fake_bot)
    assert metrics.get("match_searches") == 1
    assert init["unmatched"] == 1

    # Повторные 5-минутные проходы без изменений
    # каталога не ищут этот товар снова.
    for _ in range(3):
        metrics, init, version, _ = run_cycle(fake_bot)
        assert metrics.get("match_searches") == 0
        assert init["new_products"] == 0
        assert version["products"] == 0
        assert metrics.get("sql_statements") <= 8

    # Тот же фид: 304 по ETag, версия не публикуется.
    result = sync_golden_apple_feed()
    assert result["status"] == "not_modified"
    assert fake_feed.conditional_hits == 1

    # Без поддержки ETag — пропуск по SHA-256.
    fake_feed.supports_etag = False
    assert sync_golden_apple_feed()["status"] == "not_modified"
    fake_feed.supports_etag = True

    metrics, *_ = run_cycle(fake_bot)
    assert metrics.get("match_searches") == 0

    # Изменилась только цена другого бренда:
    # отрицательный кэш Clarins остаётся.
    fake_feed.set_items(items_with(**{"3": {"price": 3500}}))
    assert sync_golden_apple_feed()["status"] == "published"
    metrics, *_ = run_cycle(fake_bot)
    assert metrics.get("match_searches") == 0

    # Только цена Clarins — match-поля не менялись,
    # кэш тоже остаётся.
    fake_feed.set_items(items_with(**{"3": {"price": 3500}, "1": {"price": 2400}}))
    sync_golden_apple_feed()
    metrics, *_ = run_cycle(fake_bot)
    assert metrics.get("match_searches") == 0

    # Появился новый товар Clarins — кэш устарел,
    # поиск выполняется один раз и находит товар.
    items = items_with(**{"3": {"price": 3500}, "1": {"price": 2400}})
    items.append(feed_item(5, "Clarins", "Clarins Totally Unknown Balm", 1900, volume=15))
    fake_feed.set_items(items)
    sync_golden_apple_feed()
    metrics, init, *_ = run_cycle(fake_bot)
    assert metrics.get("match_searches") == 1
    assert init["initialized"] == 1

    metrics, *_ = run_cycle(fake_bot)
    assert metrics.get("match_searches") == 0


def test_import_sends_only_changed_rows(db, fake_feed):
    fake_feed.set_items(BASE_ITEMS)
    first = sync_golden_apple_feed()
    assert first["inserted"] == 4

    fake_feed.set_items(items_with(**{"2": {"price": 2999}}))
    second = sync_golden_apple_feed()
    assert second["status"] == "published"
    assert second["updated"] == 1
    assert second["unchanged"] == 3
    assert second["inserted"] == 0

    row = db.scalar(select(StoreCatalogItem).where(StoreCatalogItem.external_id == "2"))
    assert float(row.current_price) == 2999
    assert row.changed_version == second["version"]
    # цена не входит в match-поля
    assert row.match_changed_version == first["version"]

    untouched = db.scalar(select(StoreCatalogItem).where(StoreCatalogItem.external_id == "1"))
    assert untouched.changed_version == first["version"]


# -------------------------
# 2. один товар — несколько пользователей
# -------------------------


def test_one_product_many_subscribers(db, fake_feed, fake_bot):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()

    product = make_product(db, "Clarins", "Double Serum", size="50 мл")
    users = [make_user(db, 2000 + i) for i in range(5)]
    for user in users:
        track(db, user, product)

    metrics, init, *_ = run_cycle(fake_bot)
    # один поиск на товар, а не на подписку
    assert metrics.get("match_searches") == 1
    assert init["new_products"] == 1
    assert init["initialized"] == 5
    assert fake_bot.sent == []

    fake_feed.set_items(items_with(**{"1": {"price": 2000, "oldprice": 2500}}))
    sync_golden_apple_feed()

    metrics, _init, version, delivery = run_cycle(fake_bot)
    assert version["products"] == 1
    assert version["subscriptions"] == 5
    assert version["enqueued"] == 5
    assert delivery["sent"] == 5
    assert metrics.get("match_searches") == 0
    assert sorted(m["chat_id"] for m in fake_bot.sent) == [2000, 2001, 2002, 2003, 2004]


# -------------------------
# 3. первое сохранение
# -------------------------


def test_first_save_does_not_send_existing_discount(db, fake_feed, fake_bot):
    fake_feed.set_items(items_with(**{"1": {"price": 1500, "oldprice": 2500}}))
    sync_golden_apple_feed()

    user = make_user(db, 3001)
    product = make_product(db, "Clarins", "Double Serum", size="50 мл")
    tracked = track(db, user, product)

    run_cycle(fake_bot)
    run_cycle(fake_bot)

    assert fake_bot.sent == []
    db.refresh(tracked)
    assert tracked.last_seen_has_discount is True
    assert float(tracked.last_seen_price) == 1500

    # Новая версия каталога с той же ценой — тоже без рассылки.
    fake_feed.set_items(items_with(**{"1": {"price": 1500, "oldprice": 2500}, "2": {"price": 1}}))
    sync_golden_apple_feed()
    run_cycle(fake_bot)
    assert fake_bot.sent == []


def test_first_observation_in_new_version_is_baseline(db, fake_feed, fake_bot):
    """Подписка без baseline, которую впервые увидел шаг версии."""

    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()

    user = make_user(db, 3101)
    product = make_product(db, "Clarins", "Double Serum", size="50 мл")
    link_product_to_best_match(db, product)
    tracked = track(db, user, product)

    # Цена появилась с уже действующей скидкой до первого прохода.
    fake_feed.set_items(items_with(**{"1": {"price": 1500, "oldprice": 2500}}))
    sync_golden_apple_feed()
    run_cycle(fake_bot)

    assert fake_bot.sent == []
    db.refresh(tracked)
    assert tracked.last_price_checked_at is not None


# -------------------------
# 4. скидка и дальнейшее снижение
# -------------------------


def test_discount_appears_then_drops_further(db, fake_feed, fake_bot):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()

    user = make_user(db, 4001)
    product = make_product(db, "Dior", "Addict Lip Glow", variant="001 Pink")
    tracked = track(db, user, product)
    run_cycle(fake_bot)
    assert fake_bot.sent == []

    fake_feed.set_items(items_with(**{"3": {"price": 3500, "oldprice": 3900}}))
    sync_golden_apple_feed()
    run_cycle(fake_bot)
    assert len(fake_bot.sent) == 1

    db.refresh(tracked)
    assert float(tracked.last_notified_price) == 3500
    assert tracked.last_notified_discount_percent == 10

    # та же цена, другой товар изменился — без повторов
    fake_feed.set_items(items_with(**{"3": {"price": 3500, "oldprice": 3900}, "4": {"price": 1}}))
    sync_golden_apple_feed()
    run_cycle(fake_bot)
    assert len(fake_bot.sent) == 1

    # дальнейшее снижение
    fake_feed.set_items(items_with(**{"3": {"price": 3000, "oldprice": 3900}, "4": {"price": 1}}))
    sync_golden_apple_feed()
    run_cycle(fake_bot)
    assert len(fake_bot.sent) == 2

    # отключённые уведомления
    tracked = db.get(TrackedItem, tracked.id)
    tracked.notifications_enabled = False
    db.commit()
    fake_feed.set_items(items_with(**{"3": {"price": 2500, "oldprice": 3900}, "4": {"price": 1}}))
    sync_golden_apple_feed()
    run_cycle(fake_bot)
    assert len(fake_bot.sent) == 2


# -------------------------
# 5. исчезновение и возвращение
# -------------------------


def test_product_disappears_and_returns(db, fake_feed, fake_bot):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()

    user = make_user(db, 5001)
    product = make_product(db, "Clarins", "Hydra Essentiel Cream", size="50 мл")
    tracked = track(db, user, product)
    run_cycle(fake_bot)

    # Товар исчез из выгрузки.
    fake_feed.set_items([i for i in BASE_ITEMS if i["id"] != "2"])
    result = sync_golden_apple_feed()
    assert result["marked_unavailable"] == 1

    run_cycle(fake_bot)
    row = db.scalar(select(StoreCatalogItem).where(StoreCatalogItem.external_id == "2"))
    assert row.available is False
    offer = db.scalar(select(Offer).where(Offer.product_id == product.id))
    assert offer.in_stock is False
    assert fake_bot.sent == []

    # Пока товара нет, проходы не ищут его снова
    metrics, *_ = run_cycle(fake_bot)
    assert metrics.get("match_searches") == 0

    # Вернулся по той же цене — без уведомления.
    fake_feed.set_items(BASE_ITEMS)
    result = sync_golden_apple_feed()
    assert result["returned_to_stock"] == 1
    run_cycle(fake_bot)
    db.expire_all()
    assert db.get(Offer, offer.id).in_stock is True
    assert fake_bot.sent == []

    # Снова пропал и вернулся уже со скидкой — уведомление.
    fake_feed.set_items([i for i in BASE_ITEMS if i["id"] != "2"])
    sync_golden_apple_feed()
    run_cycle(fake_bot)
    fake_feed.set_items(items_with(**{"2": {"price": 2500, "oldprice": 3100}}))
    sync_golden_apple_feed()
    run_cycle(fake_bot)
    assert len(fake_bot.sent) == 1
    db.refresh(tracked)
    assert float(tracked.last_seen_price) == 2500


def test_empty_feed_does_not_hide_catalog(db, fake_feed):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()

    fake_feed.set_items([])
    with pytest.raises(RuntimeError):
        sync_golden_apple_feed()

    available = db.scalar(
        select(func.count()).select_from(StoreCatalogItem).where(StoreCatalogItem.available.is_(True))
    )
    assert available == 4


# -------------------------
# 6. сбой и повтор импорта
# -------------------------


def test_import_failure_publishes_nothing_and_retry_succeeds(db, fake_feed, fake_bot, monkeypatch):
    golden_apple_feed.BATCH_SIZE, old_batch = 2, golden_apple_feed.BATCH_SIZE
    try:
        fake_feed.set_items(BASE_ITEMS)
        first = sync_golden_apple_feed()
        first_version = first["version"]

        user = make_user(db, 6001)
        product = make_product(db, "Clarins", "Double Serum", size="50 мл")
        track(db, user, product)
        run_cycle(fake_bot)

        # Все цены изменились и товар 4 пропал;
        # падение после первого пакета.
        changed = [dict(i, price=100, oldprice=5000) for i in BASE_ITEMS if i["id"] != "4"]
        fake_feed.set_items(changed)

        real_upsert = golden_apple_feed.upsert_changed_batch
        calls = {"n": 0}

        def flaky(db_, rows, version):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("connection lost")
            return real_upsert(db_, rows, version)

        monkeypatch.setattr(golden_apple_feed, "upsert_changed_batch", flaky)

        with pytest.raises(RuntimeError):
            sync_golden_apple_feed()

        db.expire_all()
        prices = dict(
            db.execute(select(StoreCatalogItem.external_id, StoreCatalogItem.current_price)).all()
        )
        assert {k: float(v) for k, v in prices.items()} == {"1": 2500, "2": 3100, "3": 3900, "4": 5200}
        assert db.scalar(
            select(StoreCatalogItem.available).where(StoreCatalogItem.external_id == "4")
        ) is True
        statuses = [r.status for r in db.scalars(select(CatalogSyncRun).order_by(CatalogSyncRun.id))]
        assert statuses == ["published", "failed"]

        # мониторинг не видит новой версии
        _m, _i, version, _d = run_cycle(fake_bot)
        assert version["products"] == 0
        assert fake_bot.sent == []

        # повтор после сбоя (фид тот же, но версия не
        # была опубликована — пропуска по хешу нет)
        monkeypatch.setattr(golden_apple_feed, "upsert_changed_batch", real_upsert)
        retry = sync_golden_apple_feed()
        assert retry["status"] == "published"
        assert retry["version"] > first_version
        assert retry["updated"] == 3
        assert retry["marked_unavailable"] == 1

        run_cycle(fake_bot)
        assert len(fake_bot.sent) == 1
    finally:
        golden_apple_feed.BATCH_SIZE = old_batch


def test_crash_between_send_and_save_is_not_resent(db, fake_feed, fake_bot, monkeypatch):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()
    user = make_user(db, 6101)
    product = make_product(db, "Clarins", "Double Serum", size="50 мл")
    track(db, user, product)
    run_cycle(fake_bot)

    fake_feed.set_items(items_with(**{"1": {"price": 2000, "oldprice": 2500}}))
    sync_golden_apple_feed()

    def broken_mark_sent(*args, **kwargs):
        raise RuntimeError("db down after send")

    monkeypatch.setattr(discount_monitor, "mark_sent", broken_mark_sent)
    with pytest.raises(RuntimeError):
        run_cycle(fake_bot)
    assert len(fake_bot.sent) == 1

    notification = db.scalar(select(DiscountNotification))
    assert notification.status == "sending"

    # Через SENDING_STALE_AFTER строка становится uncertain
    # и повторно не отправляется.
    db.execute(
        update(DiscountNotification).values(
            claimed_at=datetime.now(timezone.utc) - timedelta(hours=1)
        )
    )
    db.commit()
    monkeypatch.undo()
    run_cycle(fake_bot)
    db.expire_all()
    assert db.scalar(select(DiscountNotification.status)) == "uncertain"
    assert len(fake_bot.sent) == 1


def test_phase_crash_midway_is_idempotent(db, fake_feed, fake_bot, monkeypatch):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()
    products = [
        make_product(db, "Clarins", "Double Serum", size="50 мл"),
        make_product(db, "Clarins", "Hydra Essentiel Cream", size="50 мл"),
    ]
    user = make_user(db, 6201)
    for product in products:
        track(db, user, product)
    run_cycle(fake_bot)

    fake_feed.set_items(
        items_with(**{"1": {"price": 2000, "oldprice": 2500}, "2": {"price": 2000, "oldprice": 3100}})
    )
    sync_golden_apple_feed()

    monkeypatch.setattr(discount_monitor, "PRODUCT_BATCH_SIZE", 1)
    real = discount_monitor._apply_state_to_subscribers
    calls = {"n": 0}

    def crash_on_second(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("worker killed")
        return real(*args, **kwargs)

    monkeypatch.setattr(discount_monitor, "_apply_state_to_subscribers", crash_on_second)
    db2 = SessionLocal()
    with pytest.raises(RuntimeError):
        apply_catalog_version(db2, batch_size=1)
    db2.rollback()
    db2.close()

    monkeypatch.setattr(discount_monitor, "_apply_state_to_subscribers", real)
    run_cycle(fake_bot)
    run_cycle(fake_bot)
    assert len(fake_bot.sent) == 2
    assert db.scalar(select(func.count()).select_from(DiscountNotification)) == 2


# -------------------------
# 7. два worker'а одновременно
# -------------------------


def test_two_imports_at_once_only_one_runs(db, fake_feed):
    fake_feed.set_items(BASE_ITEMS)
    started = threading.Event()

    def slow():
        started.set()
        time.sleep(1.0)

    fake_feed.before_return = slow
    results = []

    def worker():
        results.append(sync_golden_apple_feed())

    first = threading.Thread(target=worker)
    first.start()
    started.wait(5)
    fake_feed.before_return = None
    second = threading.Thread(target=worker)
    second.start()
    first.join()
    second.join()

    statuses = sorted(r["status"] for r in results)
    assert statuses == ["published", "skipped_locked"]
    assert db.scalar(select(func.count()).select_from(CatalogSyncRun)) == 1


def test_advisory_lock_is_exclusive_and_released_on_disconnect():
    with advisory_lock(engine, "discount_monitor") as first:
        assert first is True
        with advisory_lock(engine, "discount_monitor") as second:
            assert second is False
    with advisory_lock(engine, "discount_monitor") as again:
        assert again is True

    # Падение процесса: соединение закрывается — блокировка снимается.
    connection = engine.connect()
    from sqlalchemy import text

    from app.core.locks import lock_key

    connection.execute(text("SELECT pg_advisory_lock(:k)"), {"k": lock_key("catalog_import:x")})
    connection.commit()
    with advisory_lock(engine, "catalog_import:x") as busy:
        assert busy is False
    connection.invalidate()
    connection.close()
    with advisory_lock(engine, "catalog_import:x") as free:
        assert free is True


def test_two_delivery_workers_send_each_notification_once(db, fake_feed):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()
    product = make_product(db, "Clarins", "Double Serum", size="50 мл")
    users = [make_user(db, 7000 + i) for i in range(40)]
    for user in users:
        track(db, user, product)

    from tests_pg.conftest import FakeBot

    run_cycle(FakeBot())
    fake_feed.set_items(items_with(**{"1": {"price": 2000, "oldprice": 2500}}))
    sync_golden_apple_feed()

    session = SessionLocal()
    apply_catalog_version(session)
    session.close()

    # Конкурентный claim двумя соединениями: наборы не пересекаются.
    s1, s2 = SessionLocal(), SessionLocal()
    barrier = threading.Barrier(2)
    claimed = {}

    def claim(name, session):
        barrier.wait()
        claimed[name] = [c["id"] for c in claim_notifications(session, limit=25)]

    t1 = threading.Thread(target=claim, args=("a", s1))
    t2 = threading.Thread(target=claim, args=("b", s2))
    t1.start(); t2.start(); t1.join(); t2.join()
    s1.close(); s2.close()
    assert not set(claimed["a"]) & set(claimed["b"])
    assert len(claimed["a"]) + len(claimed["b"]) == 40

    # вернуть в очередь и отправить двумя async-worker'ами
    db.execute(update(DiscountNotification).values(status="pending", attempts=0))
    db.commit()

    bot_a, bot_b = FakeBot(), FakeBot()

    async def both():
        await asyncio.gather(
            deliver_notifications(bot_a, SessionLocal, limit=40),
            deliver_notifications(bot_b, SessionLocal, limit=40),
        )

    asyncio.run(both())
    chats = [m["chat_id"] for m in bot_a.sent + bot_b.sent]
    assert len(chats) == 40
    assert len(set(chats)) == 40


def test_rerun_same_version_creates_no_duplicates(db, fake_feed, fake_bot):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()
    user = make_user(db, 7101)
    product = make_product(db, "Clarins", "Double Serum", size="50 мл")
    track(db, user, product)
    run_cycle(fake_bot)

    fake_feed.set_items(items_with(**{"1": {"price": 2000, "oldprice": 2500}}))
    sync_golden_apple_feed()

    session = SessionLocal()
    apply_catalog_version(session)
    # водяной знак сброшен, как будто процесс упал до его записи
    from app.services.catalog_versions import set_job_state

    set_job_state(session, discount_monitor.WATERMARK_KEY, 0)
    session.commit()
    apply_catalog_version(session)
    session.close()

    assert db.scalar(select(func.count()).select_from(DiscountNotification)) == 1


def test_negative_cache_invalidated_when_product_changes(db, fake_feed):
    fake_feed.set_items(BASE_ITEMS)
    sync_golden_apple_feed()
    product = make_product(db, "Clarins", "Duble Serm XL", size="30 мл")
    result = link_product_to_best_match(db, product)
    assert result.matched is False
    assert db.get(ProductMatchMiss, (product.id, result.store_id)) is not None

    # исправили название/объём — отпечаток другой, поиск заново
    product.name = "Double Serum"
    product.size = "50 мл"
    db.commit()
    result = link_product_to_best_match(db, product)
    assert result.matched is True
    assert db.get(ProductMatchMiss, (product.id, result.store_id)) is None
