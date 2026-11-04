import os
from urllib.parse import parse_qs, urlparse

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.metrics import install_sql_counters

settings = get_settings()

database_url = settings.database_url

# Railway отдаёт URL как postgresql://...
# SQLAlchemy по умолчанию пытается использовать psycopg2.
# Мы используем psycopg v3.
if database_url.startswith("postgresql://"):
    database_url = database_url.replace(
        "postgresql://",
        "postgresql+psycopg://",
        1,
    )


def describe_database_url(url: str) -> dict:
    """Тип подключения без секретов.

    Возвращает только класс адреса:
    railway_private (*.railway.internal) — приватная сеть,
    railway_public_proxy (*.proxy.rlwy.net и т. п.) —
    публичный TCP-прокси, трафик тарифицируется как egress.
    Хост, пользователь и пароль не возвращаются.
    """

    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        query = parse_qs(parsed.query)
    except Exception:
        return {"host_kind": "unparsed"}

    if host.endswith(".railway.internal"):
        kind = "railway_private"
    elif host.endswith("rlwy.net") or host.endswith(
        ".railway.app"
    ):
        kind = "railway_public_proxy"
    elif host in {"localhost", "127.0.0.1", "::1", ""}:
        kind = "local"
    else:
        kind = "other"

    return {
        "driver": parsed.scheme,
        "host_kind": kind,
        "sslmode": (query.get("sslmode") or [None])[0],
    }


engine_kwargs = {
    "pool_pre_ping": True,
}

if not database_url.startswith("sqlite"):
    # Размер пула задаётся явно на каждый процесс.
    # Сумма по всем процессам должна быть меньше
    # max_connections PostgreSQL (см. план Railway).
    engine_kwargs.update(
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        pool_recycle=1800,
        connect_args={
            # Без этого недоступная база (например, приватная
            # сеть ещё не готова) вешает старт без ошибок.
            "connect_timeout": int(os.getenv("DB_CONNECT_TIMEOUT", "10")),
            "application_name": os.getenv(
                "DB_APPLICATION_NAME",
                os.getenv("RAILWAY_SERVICE_NAME", "cosmi"),
            )[:60],
        },
    )

engine = create_engine(database_url, **engine_kwargs)

install_sql_counters(engine)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
