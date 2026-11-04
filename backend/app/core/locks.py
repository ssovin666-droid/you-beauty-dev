"""Межпроцессные блокировки фоновых задач.

Используются session-level advisory locks PostgreSQL
на отдельном соединении:

- блокировка живёт, пока живо соединение. Если процесс
  упал или Railway остановил старое развёртывание,
  PostgreSQL снимает её сам — после перезапуска
  ничего чистить не нужно;
- при пересечении старого и нового развёртываний
  второй процесс не получает блокировку и пропускает
  этот проход (pg_try_advisory_lock не ждёт);
- через PgBouncer в режиме transaction pooling
  такие блокировки не работают. Railway Postgres
  подключается напрямую, это условие выполняется.

Блокировка — оптимизация от лишней работы.
Корректность импорта дополнительно защищена
блокировкой строки магазина внутри транзакции
публикации, а уведомлений — уникальным dedupe_key
и FOR UPDATE SKIP LOCKED.
"""

from __future__ import annotations

import hashlib
import threading
from contextlib import contextmanager

from sqlalchemy import text


_local_locks: dict[str, threading.Lock] = {}
_local_guard = threading.Lock()


def lock_key(name: str) -> int:
    digest = hashlib.blake2b(
        name.encode("utf-8"),
        digest_size=8,
    ).digest()
    return int.from_bytes(
        digest,
        "big",
        signed=True,
    )


@contextmanager
def advisory_lock(engine, name: str):
    """Пытается взять блокировку, не ожидая.

    yield True — блокировка получена,
    yield False — её держит другой процесс.
    """

    if engine.dialect.name != "postgresql":
        # Тесты на SQLite: блокировка внутри процесса.
        with _local_guard:
            lock = _local_locks.setdefault(
                name,
                threading.Lock(),
            )
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()
        return

    key = lock_key(name)
    connection = engine.connect()
    acquired = False

    try:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:key)"),
                {"key": key},
            ).scalar()
        )
        # Не держим соединение в открытой транзакции.
        connection.commit()

        yield acquired

    finally:
        if acquired:
            try:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": key},
                )
                connection.commit()
            except Exception:
                # Соединение сломано: закрываем его
                # физически, сервер снимет блокировку.
                connection.invalidate()
        connection.close()
