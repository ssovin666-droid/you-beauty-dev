"""Схема для фоновых задач.

Вызывается и API (prepare_database), и ботом при старте:
бот и API развёртываются независимо, и бот не должен
зависеть от того, кто стартовал первым.

Все изменения аддитивные и повторяемые:
- новые таблицы (create_all с checkfirst);
- nullable-колонки без DEFAULT — в PostgreSQL это
  изменение метаданных без перезаписи таблицы;
- индексы CREATE INDEX CONCURRENTLY IF NOT EXISTS —
  без блокировки записи в store_catalog_items.

Старый код продолжает работать с новой схемой,
поэтому откат приложения не требует отката схемы.
"""

from __future__ import annotations

import time

from sqlalchemy import inspect, text

from app.models import (
    CatalogSyncRun,
    DiscountNotification,
    JobRun,
    JobState,
    ProductMatchMiss,
)
from app.models.base import Base


SCHEMA_LOCK_KEY = 7_302_551_119  # произвольная константа


NEW_COLUMNS = {
    "store_catalog_items": {
        "content_hash": "BIGINT",
        "changed_version": "INTEGER",
        "match_changed_version": "INTEGER",
    },
}


# (имя, таблица, определение)
NEW_INDEXES = [
    (
        "ix_sci_store_changed_version",
        "store_catalog_items",
        "(store_id, changed_version) "
        "WHERE product_id IS NOT NULL",
    ),
    (
        "ix_sci_store_match_version",
        "store_catalog_items",
        "(store_id, match_changed_version)",
    ),
    (
        "ix_tracked_items_uninitialized",
        "tracked_items",
        "(product_id) "
        "WHERE last_price_checked_at IS NULL",
    ),
]


# Сколько ждать, если схему прямо сейчас
# обновляет другой процесс.
SCHEMA_LOCK_WAIT_SECONDS = 60

# Блокировка таблицы для DDL: лучше быстро
# упасть с понятной ошибкой (Railway перезапустит),
# чем молча висеть за долгой транзакцией.
DDL_LOCK_TIMEOUT = "5s"

# Построение одного индекса CONCURRENTLY.
INDEX_STATEMENT_TIMEOUT = "300s"

INDEX_LOCK_NAME = "schema:indexes"

JOB_TABLES = (
    CatalogSyncRun.__table__,
    ProductMatchMiss.__table__,
    JobState.__table__,
    DiscountNotification.__table__,
    JobRun.__table__,
)


def _log(message: str) -> None:
    print(f"SCHEMA | {message}", flush=True)


def _schema_complete(engine) -> bool:
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())

        if any(table.name not in tables for table in JOB_TABLES):
            return False

        for table, columns in NEW_COLUMNS.items():
            if table not in tables:
                continue
            existing = {
                column["name"]
                for column in inspector.get_columns(table)
            }
            if any(name not in existing for name in columns):
                return False

    return True


def ensure_job_schema(engine) -> None:
    """Таблицы и колонки фоновых задач.

    Быстрый путь: если всё уже есть, только
    читаем каталог схемы и не берём блокировок.
    Индексы здесь НЕ строятся — см. ensure_job_indexes
    (их строит бот в фоне), поэтому старт API
    не ждёт ни бота, ни импорта каталога.
    """

    if engine.dialect.name != "postgresql":
        Base.metadata.create_all(
            bind=engine,
            tables=list(JOB_TABLES),
        )
        _add_columns(engine)
        return

    if _schema_complete(engine):
        _log("up to date")
        return

    with engine.connect() as lock_connection:
        deadline = time.monotonic() + SCHEMA_LOCK_WAIT_SECONDS
        acquired = False

        while True:
            acquired = bool(
                lock_connection.execute(
                    text("SELECT pg_try_advisory_lock(:key)"),
                    {"key": SCHEMA_LOCK_KEY},
                ).scalar()
            )
            # Не держим транзакцию (и снимок), пока ждём.
            lock_connection.commit()

            if acquired or time.monotonic() > deadline:
                break

            _log("waiting for another process")
            time.sleep(1)

        if not acquired:
            raise RuntimeError(
                "schema lock is held by another process "
                f"for more than {SCHEMA_LOCK_WAIT_SECONDS}s"
            )

        try:
            if _schema_complete(engine):
                _log("up to date (after lock)")
                return

            with engine.begin() as connection:
                connection.execute(
                    text(
                        f"SET LOCAL lock_timeout = '{DDL_LOCK_TIMEOUT}'"
                    )
                )
                Base.metadata.create_all(
                    bind=connection,
                    tables=list(JOB_TABLES),
                )

            _add_columns(engine)
            _log("tables and columns created")

        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": SCHEMA_LOCK_KEY},
            )
            lock_connection.commit()


def ensure_job_indexes(engine) -> None:
    """Индексы фоновых задач. Только оптимизация.

    Вызывается ботом в фоне после старта.
    Не блокирует запись в таблицы, ограничен
    по времени; ошибка не останавливает процесс —
    повторится при следующем старте.
    """

    if engine.dialect.name != "postgresql":
        return

    from app.core.locks import advisory_lock

    with advisory_lock(engine, INDEX_LOCK_NAME) as acquired:
        if not acquired:
            _log("indexes: another process is building them")
            return

        try:
            _create_indexes(engine)
            _log("indexes ready")
        except Exception as exc:
            _log(
                "indexes: skipped, will retry on next start: "
                f"{type(exc).__name__}"
            )


def _add_columns(engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())

        if engine.dialect.name == "postgresql":
            # ALTER ждёт ACCESS EXCLUSIVE. Если таблицу
            # держит долгая транзакция импорта, лучше
            # быстро упасть и повторить при следующем
            # старте, чем остановить все запросы к ней.
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))

        for table, columns in NEW_COLUMNS.items():
            if table not in table_names:
                continue

            existing = {
                column["name"]
                for column in inspector.get_columns(table)
            }

            for name, sql_type in columns.items():
                if name in existing:
                    continue
                connection.execute(
                    text(
                        f"ALTER TABLE {table} "
                        f"ADD COLUMN IF NOT EXISTS {name} {sql_type}"
                    )
                )


def _create_indexes(engine) -> None:
    autocommit = engine.execution_options(
        isolation_level="AUTOCOMMIT"
    )

    with autocommit.connect() as connection:
        connection.execute(
            text(f"SET lock_timeout = '{DDL_LOCK_TIMEOUT}'")
        )
        connection.execute(
            text(
                f"SET statement_timeout = '{INDEX_STATEMENT_TIMEOUT}'"
            )
        )

        try:
            for name, table, definition in NEW_INDEXES:
                # Недостроенный CONCURRENTLY-индекс остаётся
                # INVALID — удаляем и строим заново.
                invalid = connection.execute(
                    text(
                        """
                        SELECT 1
                        FROM pg_index i
                        JOIN pg_class c ON c.oid = i.indexrelid
                        WHERE c.relname = :name
                          AND NOT i.indisvalid
                        """
                    ),
                    {"name": name},
                ).first()

                if invalid:
                    connection.execute(
                        text(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
                    )

                connection.execute(
                    text(
                        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS "
                        f"{name} ON {table} {definition}"
                    )
                )
        finally:
            # Соединение вернётся в пул: сбрасываем
            # таймауты, чтобы они не достались запросам.
            connection.execute(text("RESET ALL"))
