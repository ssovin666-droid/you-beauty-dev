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

        # -------------------------
        # USERS
        # -------------------------

        if "users" in table_names:
            user_columns = {
                column["name"]: column
                for column
                in inspector.get_columns(
                    "users"
                )
            }

            telegram_column = (
                user_columns.get(
                    "telegram_user_id"
                )
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

            # Старое поле first-touch.
            # Оставляем для совместимости
            # с существующей аналитикой
            # и Amplitude.
            if (
                "traffic_source"
                not in user_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS
                        traffic_source VARCHAR(500)
                        """
                    )
                )

            # Первый источник пользователя.
            if (
                "first_source"
                not in user_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS
                        first_source VARCHAR(500)
                        """
                    )
                )

            # Последний источник запуска.
            if (
                "last_source"
                not in user_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS
                        last_source VARCHAR(500)
                        """
                    )
                )

            # Первый запуск бота.
            if (
                "bot_started_at"
                not in user_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS
                        bot_started_at
                        TIMESTAMP WITH TIME ZONE
                        """
                    )
                )

            # Последний запуск /start.
            if (
                "last_started_at"
                not in user_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE users
                        ADD COLUMN IF NOT EXISTS
                        last_started_at
                        TIMESTAMP WITH TIME ZONE
                        """
                    )
                )

            # -------------------------
            # BACKFILL EXISTING USERS
            # -------------------------
            #
            # Старые данные не теряем:
            #
            # traffic_source →
            # first_source + last_source
            #
            # bot_started_at →
            # last_started_at
            #
            # COALESCE не перезаписывает
            # уже заполненные новые поля.
            # -------------------------

            connection.execute(
                text(
                    """
                    UPDATE users
                    SET first_source =
                        COALESCE(
                            first_source,
                            traffic_source
                        )
                    WHERE first_source IS NULL
                    """
                )
            )

            connection.execute(
                text(
                    """
                    UPDATE users
                    SET last_source =
                        COALESCE(
                            last_source,
                            traffic_source
                        )
                    WHERE last_source IS NULL
                    """
                )
            )

            connection.execute(
                text(
                    """
                    UPDATE users
                    SET last_started_at =
                        COALESCE(
                            last_started_at,
                            bot_started_at
                        )
                    WHERE last_started_at IS NULL
                    """
                )
            )

        # -------------------------
        # TRACKED ITEMS
        # Price tracking memory
        # -------------------------

        if "tracked_items" in table_names:
            tracked_columns = {
                column["name"]: column
                for column
                in inspector.get_columns(
                    "tracked_items"
                )
            }

            if (
                "last_seen_price"
                not in tracked_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE tracked_items
                        ADD COLUMN IF NOT EXISTS
                        last_seen_price NUMERIC(12, 2)
                        """
                    )
                )

            if (
                "last_seen_old_price"
                not in tracked_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE tracked_items
                        ADD COLUMN IF NOT EXISTS
                        last_seen_old_price NUMERIC(12, 2)
                        """
                    )
                )

            if (
                "last_seen_has_discount"
                not in tracked_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE tracked_items
                        ADD COLUMN IF NOT EXISTS
                        last_seen_has_discount BOOLEAN
                        """
                    )
                )

            if (
                "last_price_checked_at"
                not in tracked_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE tracked_items
                        ADD COLUMN IF NOT EXISTS
                        last_price_checked_at
                        TIMESTAMP WITH TIME ZONE
                        """
                    )
                )

            if (
                "last_notified_price"
                not in tracked_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE tracked_items
                        ADD COLUMN IF NOT EXISTS
                        last_notified_price NUMERIC(12, 2)
                        """
                    )
                )

            if (
                "last_notified_discount_percent"
                not in tracked_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE tracked_items
                        ADD COLUMN IF NOT EXISTS
                        last_notified_discount_percent
                        INTEGER
                        """
                    )
                )

            if (
                "last_notified_at"
                not in tracked_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE tracked_items
                        ADD COLUMN IF NOT EXISTS
                        last_notified_at
                        TIMESTAMP WITH TIME ZONE
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
