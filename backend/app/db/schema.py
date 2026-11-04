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


def ensure_job_schema(engine) -> None:
    tables = [
        CatalogSyncRun.__table__,
        ProductMatchMiss.__table__,
        JobState.__table__,
        DiscountNotification.__table__,
        JobRun.__table__,
    ]

    if engine.dialect.name != "postgresql":
        Base.metadata.create_all(
            bind=engine,
            tables=tables,
        )
        _add_columns(engine)
        return

    with engine.connect() as lock_connection:
        # Ждём, если схему прямо сейчас
        # обновляет другой процесс.
        lock_connection.execute(
            text("SELECT pg_advisory_lock(:key)"),
            {"key": SCHEMA_LOCK_KEY},
        )
        lock_connection.commit()

        try:
            Base.metadata.create_all(
                bind=engine,
                tables=tables,
            )
            _add_columns(engine)
            _create_indexes(engine)
        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"),
                {"key": SCHEMA_LOCK_KEY},
            )
            lock_connection.commit()


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
