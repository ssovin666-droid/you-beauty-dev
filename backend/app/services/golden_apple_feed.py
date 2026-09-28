import os
import re
import tempfile
import unicodedata
import zipfile
from datetime import datetime
from urllib.parse import parse_qs, urlparse

import httpx
import ijson
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.db.session import SessionLocal
from app.models import Store, StoreCatalogItem


GOLDEN_APPLE_FEED_URL = (
    "https://feeds.advcake.ru/feed/download/"
    "eaf9bd97fc9740d0d1d99ce280968d7c"
)

STORE_NAME = "Golden Apple"
STORE_SLUG = "golden-apple"

BATCH_SIZE = 500


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    value = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    value = value.casefold()

    value = re.sub(
        r"[^\w\s]+",
        " ",
        value,
        flags=re.UNICODE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def make_size(
    params: dict,
) -> str | None:
    volume = (
        params.get("Объем")
        or params.get("Объём")
    )

    unit = params.get(
        "Единица измерения"
    )

    if not volume:
        return None

    if unit:
        return f"{volume} {unit}".strip()

    return str(volume).strip()


def extract_variant(
    params: dict,
) -> str | None:
    return (
        params.get("Оттенок")
        or params.get("Цвет")
        or None
    )


def extract_picture(
    value,
) -> str | None:
    if isinstance(value, str):
        return value

    if isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                return item

    return None


def extract_product_url(
    affiliate_url: str | None,
) -> str | None:
    if not affiliate_url:
        return None

    try:
        parsed = urlparse(
            affiliate_url
        )

        query = parse_qs(
            parsed.query
        )

        urls = query.get("dl")

        if urls:
            return urls[0]

    except Exception:
        pass

    return None


def get_brand_name(
    item: dict,
    params: dict,
) -> str | None:
    brand = params.get("Бренд")

    if brand:
        return str(brand).strip()

    vendor = item.get("vendor")

    if vendor:
        return str(vendor).strip()

    return None


def get_or_create_store(
    db,
) -> Store:
    store = db.scalar(
        select(Store).where(
            Store.slug == STORE_SLUG
        )
    )

    if store:
        return store

    store = Store(
        name=STORE_NAME,
        slug=STORE_SLUG,
        active=True,
        affiliate_enabled=True,
        affiliate_network="Advcake",
    )

    db.add(store)
    db.commit()
    db.refresh(store)

    return store


def download_feed() -> str:
    temp_file = tempfile.NamedTemporaryFile(
        suffix=".zip",
        delete=False,
    )

    temp_path = temp_file.name
    temp_file.close()

    try:
        with httpx.stream(
            "GET",
            GOLDEN_APPLE_FEED_URL,
            follow_redirects=True,
            timeout=httpx.Timeout(
                300.0,
                connect=30.0,
            ),
        ) as response:
            response.raise_for_status()

            with open(
                temp_path,
                "wb",
            ) as output:
                for chunk in response.iter_bytes(
                    chunk_size=1024 * 1024
                ):
                    output.write(chunk)

        if not zipfile.is_zipfile(
            temp_path
        ):
            try:
                with open(
                    temp_path,
                    "rb",
                ) as source:
                    message = (
                        source
                        .read(500)
                        .decode(
                            "utf-8",
                            errors="ignore",
                        )
                    )
            except Exception:
                message = ""

            raise RuntimeError(
                "Golden Apple feed "
                "is not a valid ZIP. "
                f"Response: {message}"
            )

        return temp_path

    except Exception:
        if os.path.exists(
            temp_path
        ):
            os.remove(
                temp_path
            )

        raise


def prepare_row(
    item: dict,
    store_id: int,
    synced_at: datetime,
) -> dict | None:
    external_id = item.get("id")

    if external_id is None:
        return None

    name = str(
        item.get("name") or ""
    ).strip()

    if not name:
        return None

    params = item.get("params")

    if not isinstance(
        params,
        dict,
    ):
        params = {}

    brand_name = get_brand_name(
        item,
        params,
    )

    affiliate_url = item.get(
        "url"
    )

    return {
        "store_id": store_id,
        "external_id": str(
            external_id
        ),
        "group_id": (
            str(item["group_id"])
            if item.get("group_id")
            is not None
            else None
        ),
        "brand_name": brand_name,
        "brand_normalized": (
            normalize_text(
                brand_name
            )
            if brand_name
            else None
        ),
        "name": name,
        "name_normalized": (
            normalize_text(name)
        ),
        "type_prefix": (
            str(item["typePrefix"])
            if item.get("typePrefix")
            else None
        ),
        "model": (
            str(item["model"])
            if item.get("model")
            else None
        ),
        "variant": extract_variant(
            params
        ),
        "size": make_size(
            params
        ),
        "barcode": (
            str(item["barcode"])
            if item.get("barcode")
            else None
        ),
        "category_id": (
            str(item["categoryId"])
            if item.get("categoryId")
            is not None
            else None
        ),
        "image_url": extract_picture(
            item.get("picture")
        ),
        "product_url": (
            extract_product_url(
                affiliate_url
            )
        ),
        "affiliate_url": (
            str(affiliate_url)
            if affiliate_url
            else None
        ),
        "current_price": (
            item.get("price")
        ),
        "old_price": (
            item.get("oldprice")
        ),
        "currency": (
            str(item["currencyId"])
            if item.get("currencyId")
            else None
        ),
        "available": bool(
            item.get(
                "available",
                True,
            )
        ),
        "raw_params": params,
        "synced_at": synced_at,
    }


def deduplicate_rows(
    rows: list[dict],
) -> list[dict]:
    """
    В Golden Apple feed встречаются
    повторяющиеся external_id.

    PostgreSQL не позволяет в одном
    INSERT ... ON CONFLICT дважды
    обновить одну и ту же строку.

    Поэтому внутри каждой партии
    оставляем только последнюю запись
    для пары store_id + external_id.
    """

    unique: dict[
        tuple[int, str],
        dict,
    ] = {}

    for row in rows:
        key = (
            row["store_id"],
            row["external_id"],
        )

        unique[key] = row

    return list(
        unique.values()
    )


def upsert_batch(
    db,
    rows: list[dict],
):
    if not rows:
        return

    rows = deduplicate_rows(
        rows
    )

    if not rows:
        return

    statement = insert(
        StoreCatalogItem
    ).values(rows)

    statement = (
        statement.on_conflict_do_update(
            index_elements=[
                "store_id",
                "external_id",
            ],
            set_={
                "group_id":
                    statement.excluded.group_id,

                "brand_name":
                    statement.excluded.brand_name,

                "brand_normalized":
                    statement.excluded.brand_normalized,

                "name":
                    statement.excluded.name,

                "name_normalized":
                    statement.excluded.name_normalized,

                "type_prefix":
                    statement.excluded.type_prefix,

                "model":
                    statement.excluded.model,

                "variant":
                    statement.excluded.variant,

                "size":
                    statement.excluded.size,

                "barcode":
                    statement.excluded.barcode,

                "category_id":
                    statement.excluded.category_id,

                "image_url":
                    statement.excluded.image_url,

                "product_url":
                    statement.excluded.product_url,

                "affiliate_url":
                    statement.excluded.affiliate_url,

                "current_price":
                    statement.excluded.current_price,

                "old_price":
                    statement.excluded.old_price,

                "currency":
                    statement.excluded.currency,

                "available":
                    statement.excluded.available,

                "raw_params":
                    statement.excluded.raw_params,

                "synced_at":
                    statement.excluded.synced_at,
            },
        )
    )

    db.execute(
        statement
    )

    db.commit()


def sync_golden_apple_feed():
    sync_started_at = (
        datetime.utcnow()
    )

    zip_path = None
    db = SessionLocal()

    processed = 0
    skipped = 0

    try:
        print(
            "GOLDEN_APPLE_SYNC | START"
        )

        store = get_or_create_store(
            db
        )

        print(
            "GOLDEN_APPLE_SYNC | "
            "DOWNLOADING FEED"
        )

        zip_path = download_feed()

        print(
            "GOLDEN_APPLE_SYNC | "
            "DOWNLOAD COMPLETE"
        )

        with zipfile.ZipFile(
            zip_path,
            "r",
        ) as archive:
            json_files = [
                name
                for name
                in archive.namelist()
                if name
                .lower()
                .endswith(".json")
            ]

            if not json_files:
                raise RuntimeError(
                    "JSON file was not found "
                    "inside Golden Apple ZIP"
                )

            json_name = json_files[0]

            print(
                "GOLDEN_APPLE_SYNC | "
                f"JSON={json_name}"
            )

            batch: list[dict] = []

            with archive.open(
                json_name,
                "r",
            ) as json_file:
                products = ijson.items(
                    json_file,
                    "products.item",
                )

                for item in products:
                    row = prepare_row(
                        item,
                        store.id,
                        sync_started_at,
                    )

                    if not row:
                        skipped += 1
                        continue

                    batch.append(
                        row
                    )

                    processed += 1

                    if (
                        len(batch)
                        >= BATCH_SIZE
                    ):
                        upsert_batch(
                            db,
                            batch,
                        )

                        batch = []

                    if (
                        processed % 5000
                        == 0
                    ):
                        print(
                            "GOLDEN_APPLE_SYNC | "
                            f"PROCESSED={processed} "
                            f"SKIPPED={skipped}"
                        )

                if batch:
                    upsert_batch(
                        db,
                        batch,
                    )

        # Если товар был в старой выгрузке,
        # но его нет в новой — считаем,
        # что сейчас он недоступен.
        db.execute(
            update(
                StoreCatalogItem
            )
            .where(
                StoreCatalogItem.store_id
                == store.id,
                StoreCatalogItem.synced_at
                < sync_started_at,
            )
            .values(
                available=False
            )
        )

        db.commit()

        result = {
            "ok": True,
            "store": STORE_NAME,
            "processed": processed,
            "skipped": skipped,
            "synced_at": (
                sync_started_at.isoformat()
            ),
        }

        print(
            "GOLDEN_APPLE_SYNC | "
            f"DONE | {result}"
        )

        return result

    except Exception as exc:
        db.rollback()

        print(
            "GOLDEN_APPLE_SYNC | "
            f"FAILED | {type(exc).__name__}: "
            f"{exc}"
        )

        raise

    finally:
        db.close()

        if (
            zip_path
            and os.path.exists(
                zip_path
            )
        ):
            os.remove(
                zip_path
            )
