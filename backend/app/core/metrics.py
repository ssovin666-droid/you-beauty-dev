"""Технические метрики фоновых задач.

Что считается:
- число SQL-запросов и строк (rowcount драйвера);
- оценка объёма параметров, отправленных в базу
  (sql_params_bytes_est — это оценка по размеру
  значений, а не точный размер протокола PostgreSQL);
- счётчики самой задачи (товары, кандидаты,
  вставленные/изменённые/пропущенные строки);
- длительность и пиковая память процесса.

Точный сетевой трафик между сервисами здесь
не измеряется — для него используются метрики
Railway и pg_stat_statements (см. docs/railway-cost-plan.md).

В метрики никогда не попадают токены, initData,
строки подключения, тексты сообщений и URL.
"""

from __future__ import annotations

import contextvars
import json
import resource
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import event


_current: contextvars.ContextVar["JobMetrics | None"] = (
    contextvars.ContextVar(
        "job_metrics",
        default=None,
    )
)

_installed_engines: set[int] = set()


def _estimate_bytes(value: Any) -> int:
    if value is None:
        return 1

    if isinstance(value, (bytes, bytearray, memoryview)):
        return len(value)

    if isinstance(value, str):
        return len(value.encode("utf-8"))

    if isinstance(value, (bool, int, float, Decimal)):
        return 8

    if isinstance(value, datetime):
        return 8

    if isinstance(value, dict):
        return sum(
            _estimate_bytes(item)
            for item in value.values()
        )

    if isinstance(value, (list, tuple, set)):
        return sum(
            _estimate_bytes(item)
            for item in value
        )

    return len(str(value))


def _rss_mb() -> float | None:
    try:
        with open("/proc/self/statm") as source:
            pages = int(source.read().split()[1])
        return round(
            pages
            * resource.getpagesize()
            / 1024
            / 1024,
            1,
        )
    except Exception:
        return None


class JobMetrics:
    def __init__(self, job: str):
        self.job = job
        self.started_at = datetime.now(timezone.utc)
        self._t0 = time.perf_counter()
        self.counters: dict[str, Any] = {
            "sql_statements": 0,
            "sql_rows": 0,
            "sql_params_bytes_est": 0,
        }
        self._token = None
        self.ok = True
        self.duration_ms = 0

    # -------------------------
    # API счётчиков
    # -------------------------

    def inc(self, key: str, value: int | float = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + value

    def set(self, key: str, value: Any) -> None:
        self.counters[key] = value

    def get(self, key: str, default: Any = 0) -> Any:
        return self.counters.get(key, default)

    # -------------------------
    # Контекст
    # -------------------------

    def __enter__(self) -> "JobMetrics":
        self._token = _current.set(self)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            self.ok = False
            self.set("error_type", exc_type.__name__)
        self.finish()
        if self._token is not None:
            _current.reset(self._token)
            self._token = None

    def finish(self) -> dict:
        self.duration_ms = int(
            (time.perf_counter() - self._t0) * 1000
        )
        self.set("rss_mb", _rss_mb())
        self.set(
            "max_rss_mb",
            round(
                resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss
                / 1024,
                1,
            ),
        )
        summary = self.summary()
        print(
            "JOB_METRICS "
            + json.dumps(
                summary,
                ensure_ascii=False,
                default=str,
                sort_keys=True,
            ),
            flush=True,
        )
        return summary

    def summary(self) -> dict:
        return {
            "job": self.job,
            "ok": self.ok,
            "duration_ms": self.duration_ms,
            **self.counters,
        }


def current_metrics() -> JobMetrics | None:
    return _current.get()


def inc(key: str, value: int | float = 1) -> None:
    metrics = _current.get()
    if metrics is not None:
        metrics.inc(key, value)


def persist_job_run(session_factory, metrics: JobMetrics) -> None:
    """Сохраняет сводку запуска в job_runs. Best effort."""

    from app.models import JobRun

    db = session_factory()
    try:
        db.add(
            JobRun(
                job=metrics.job,
                started_at=metrics.started_at,
                duration_ms=metrics.duration_ms,
                ok=metrics.ok,
                metrics=json.loads(
                    json.dumps(
                        metrics.counters,
                        default=str,
                    )
                ),
            )
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        print(
            "JOB_METRICS_PERSIST_ERROR:",
            type(exc).__name__,
        )
    finally:
        db.close()


def install_sql_counters(engine) -> None:
    """Подключает счётчики SQL к движку один раз."""

    if id(engine) in _installed_engines:
        return

    _installed_engines.add(id(engine))

    @event.listens_for(engine, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):
        metrics = _current.get()
        if metrics is None:
            return
        metrics.inc("sql_statements")
        metrics.inc(
            "sql_params_bytes_est",
            _estimate_bytes(parameters)
            + len(statement),
        )

    @event.listens_for(engine, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):
        metrics = _current.get()
        if metrics is None:
            return
        rowcount = getattr(cursor, "rowcount", -1)
        if rowcount and rowcount > 0:
            metrics.inc("sql_rows", rowcount)
