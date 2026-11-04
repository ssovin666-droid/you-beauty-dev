from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import BigInteger, inspect, text

from app.api.match_admin import (
    router as match_admin_router,
)
from app.api.character_admin import (
    router as character_admin_router,
)
from app.api.character_routes import (
    router as character_router,
)
from app.api.routes import router
from app.db.schema import ensure_job_schema
from app.db.session import (
    SessionLocal,
    describe_database_url,
    database_url,
    engine,
)
from app.models import Base
from app.services.character import seed_items


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
        # PRODUCTS
        # shade_group для персонажа
        # -------------------------

        if "products" in table_names:
            product_columns = {
                column["name"]
                for column
                in inspector.get_columns(
                    "products"
                )
            }

            if (
                "shade_group"
                not in product_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE products
                        ADD COLUMN IF NOT EXISTS
                        shade_group VARCHAR(20)
                        """
                    )
                )

        # -------------------------
        # USER CHARACTERS
        # seed уникальной формы звезды
        # -------------------------

        if "user_characters" in table_names:
            character_columns = {
                column["name"]
                for column
                in inspector.get_columns(
                    "user_characters"
                )
            }

            if (
                "shape_seed"
                not in character_columns
            ):
                connection.execute(
                    text(
                        """
                        ALTER TABLE user_characters
                        ADD COLUMN IF NOT EXISTS
                        shape_seed INTEGER
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
    print(
        "DB_CONNECTION |",
        describe_database_url(database_url),
    )

    prepare_database()

    # Таблицы и индексы фоновых задач
    # (каталог, уведомления, метрики).
    ensure_job_schema(engine)

    db = SessionLocal()
    try:
        seed_items(db)
    finally:
        db.close()

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

app.include_router(
    character_router,
    prefix="/api",
)

app.include_router(
    character_admin_router,
    prefix="/api/admin",
)
