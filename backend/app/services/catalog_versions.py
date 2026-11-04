"""Версии каталога и водяные знаки фоновых задач."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CatalogSyncRun, JobState


STATUS_RUNNING = "running"
STATUS_PUBLISHED = "published"
STATUS_NOT_MODIFIED = "not_modified"
STATUS_FAILED = "failed"


def get_published_version(
    db: Session,
    store_id: int,
) -> int | None:
    return db.scalar(
        select(func.max(CatalogSyncRun.id)).where(
            CatalogSyncRun.store_id == store_id,
            CatalogSyncRun.status == STATUS_PUBLISHED,
        )
    )


def get_job_state(
    db: Session,
    key: str,
) -> int | None:
    row = db.get(JobState, key)
    return row.int_value if row else None


def set_job_state(
    db: Session,
    key: str,
    value: int | None,
) -> None:
    row = db.get(JobState, key)
    now = datetime.now(timezone.utc)
    if row is None:
        db.add(
            JobState(
                key=key,
                int_value=value,
                updated_at=now,
            )
        )
    else:
        row.int_value = value
        row.updated_at = now
