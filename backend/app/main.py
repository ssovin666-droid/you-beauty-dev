from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import BigInteger, inspect, text

from app.api.match_admin import (
    router as match_admin_router,
)
from app.api.routes import router
from app.db.session import engine
from app.models import Base


def prepare_database():
    Base.metadata.create_all(
        bind=engine
    )

    with engine.begin() as connection:
        inspector = inspect(
            connection
        )

        table_names = (
            inspector.get_table_names()
        )

        if "users" not in table_names:
            return

        columns = {
            column["name"]: column
            for column
            in inspector.get_columns(
                "users"
            )
        }

        telegram_column = columns.get(
            "telegram_user_id"
        )

        if (
            telegram_column
            and not isinstance(
                telegram_column["type"],
                BigInteger,
            )
        ):
            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ALTER COLUMN telegram_user_id
                    TYPE BIGINT
                    USING telegram_user_id::bigint
                    """
                )
            )

        if "traffic_source" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS
                    traffic_source VARCHAR(500)
                    """
                )
            )

        if "bot_started_at" not in columns:
            connection.execute(
                text(
                    """
                    ALTER TABLE users
                    ADD COLUMN IF NOT EXISTS
                    bot_started_at TIMESTAMP WITH TIME ZONE
                    """
                )
            )


@asynccontextmanager
async def lifespan(
    app: FastAPI,
):
    prepare_database()
    yield


app = FastAPI(
    title="You Beauty API",
    version="0.1.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(
    router,
    prefix="/api",
)

app.include_router(
    match_admin_router,
    prefix="/api/admin",
)
