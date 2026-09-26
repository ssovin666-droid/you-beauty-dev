from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import BigInteger, inspect, text

from app.api.routes import router
from app.db.session import engine


def prepare_database():
    with engine.begin() as connection:
        inspector = inspect(connection)

        if "users" not in inspector.get_table_names():
            return

        columns = {
            column["name"]: column
            for column in inspector.get_columns("users")
        }

        telegram_column = columns.get(
            "telegram_user_id"
        )

        if not telegram_column:
            return

        if not isinstance(
            telegram_column["type"],
            BigInteger,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
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


@app.get("/")
def root():
    return {
        "ok": True,
        "service": "you-beauty-api",
    }
