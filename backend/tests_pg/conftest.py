"""Интеграционные тесты фоновых задач на настоящем PostgreSQL.

Запуск:
    TEST_DATABASE_URL=postgresql://user@host:port/db \
        python -m pytest tests_pg -q

База очищается перед каждым тестом. Не указывайте рабочую базу.
"""

import io
import json
import os
import zipfile
from decimal import Decimal

import pytest

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

if not TEST_DATABASE_URL:
    pytest.skip(
        "TEST_DATABASE_URL is not set",
        allow_module_level=True,
    )

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("APP_ENV", "test")

from sqlalchemy import text  # noqa: E402

from app.db.schema import ensure_job_indexes, ensure_job_schema  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.services import golden_apple_feed  # noqa: E402


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    # Пересозданный enum получает новый OID:
    # соединения пула со старым кэшем типов закрываем.
    engine.dispose()
    Base.metadata.create_all(engine)
    ensure_job_schema(engine)
    ensure_job_indexes(engine)
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def feed_item(
    external_id,
    brand,
    name,
    price,
    old_price=None,
    volume=None,
    unit="мл",
    shade=None,
    available=True,
):
    params = {"Бренд": brand}
    if volume is not None:
        params["Объем"] = str(volume)
        params["Единица измерения"] = unit
    if shade:
        params["Оттенок"] = shade
    item = {
        "id": str(external_id),
        "name": name,
        "vendor": brand,
        "params": params,
        "price": Decimal(str(price)),
        "currencyId": "RUB",
        "categoryId": 10,
        "picture": [f"https://img.example/{external_id}.jpg"],
        "url": (
            "https://ad.example/click?dl="
            f"https%3A%2F%2Fgoldapple.example%2F{external_id}"
        ),
        "available": available,
    }
    if old_price is not None:
        item["oldprice"] = Decimal(str(old_price))
    return item


class FakeFeed:
    """Подменяет скачивание фида.

    Поддерживает ETag: если фид не менялся
    и клиент прислал тот же ETag — 304.
    """

    def __init__(self, tmp_path, supports_etag=True):
        self.tmp_path = tmp_path
        self.items = []
        self.supports_etag = supports_etag
        self.downloads = 0
        self.conditional_hits = 0
        self.before_return = None

    def set_items(self, items):
        self.items = [dict(item) for item in items]

    def _payload(self):
        return json.dumps(
            {"products": self.items},
            ensure_ascii=False,
            default=str,
            sort_keys=True,
        ).encode("utf-8")

    def etag(self):
        import hashlib

        return '"' + hashlib.md5(self._payload()).hexdigest() + '"'

    def download(self, etag=None, last_modified=None):
        if self.before_return is not None:
            self.before_return()

        if self.supports_etag and etag and etag == self.etag():
            self.conditional_hits += 1
            return golden_apple_feed.FeedDownload(
                path=None,
                not_modified=True,
                etag=etag,
                last_modified=last_modified,
                sha256=None,
            )

        self.downloads += 1
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("feed.json", self._payload())
        data = buffer.getvalue()

        path = self.tmp_path / f"feed-{self.downloads}.zip"
        path.write_bytes(data)

        import hashlib

        return golden_apple_feed.FeedDownload(
            path=str(path),
            not_modified=False,
            etag=self.etag() if self.supports_etag else None,
            last_modified=None,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )


@pytest.fixture
def fake_feed(tmp_path, monkeypatch):
    feed = FakeFeed(tmp_path)
    monkeypatch.setattr(
        golden_apple_feed,
        "download_feed",
        feed.download,
    )
    return feed


class FakeBot:
    def __init__(self):
        self.sent = []
        self.fail_with = None
        self._message_id = 0

    async def send_message(self, chat_id, text, **kwargs):
        if self.fail_with is not None:
            raise self.fail_with
        self._message_id += 1
        self.sent.append({"chat_id": chat_id, "text": text})

        class _Message:
            message_id = self._message_id

        return _Message()


@pytest.fixture
def fake_bot():
    return FakeBot()
