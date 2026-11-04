import hashlib
import json
import os
import re
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import httpx
import ijson
from sqlalchemy import case, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.locks import advisory_lock
from app.core.metrics import JobMetrics, persist_job_run
from app.db.session import SessionLocal, engine
from app.models import (
    CatalogSyncRun,
    ProductMatchMiss,
    Store,
    StoreCatalogItem,
)
from app.services.catalog_versions import (
    STATUS_FAILED,
    STATUS_NOT_MODIFIED,
    STATUS_PUBLISHED,
    STATUS_RUNNING,
)


GOLDEN_APPLE_FEED_URL = (
    "https://feeds.advcake.ru/feed/download/"
    "eaf9bd97fc9740d0d1d99ce280968d7c"
)

STORE_NAME = "Golden Apple"
STORE_SLUG = "golden-apple"

BATCH_SIZE = 500

# Сколько id исчезнувших товаров отправлять
# одним UPDATE.
DISAPPEARED_BATCH_SIZE = 5000

IMPORT_LOCK_NAME = f"catalog_import:{STORE_SLUG}"

# Поля фида. Хеш считается по ним всем,
# поэтому любое изменение в выгрузке
# (цена, ссылка, параметры, наличие)
# приводит к записи строки.
FEED_FIELDS = (
    "group_id",
    "brand_name",
    "brand_normalized",
    "name",
    "name_normalized",
    "type_prefix",
    "model",
    "variant",
    "size",
    "barcode",
    "category_id",
    "image_url",
    "product_url",
    "affiliate_url",
    "current_price",
    "old_price",
    "currency",
    "available",
    "raw_params",
)

# Поля, которые читает сопоставление товаров.
# Их изменение (или изменение наличия)
# инвалидирует отрицательный кэш бренда.
MATCH_FIELDS = (
    "brand_name",
    "brand_normalized",
    "name",
    "model",
    "type_prefix",
    "size",
    "variant",
    "available",
)


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




def _json_default(value):
    return str(value)


def content_hash(row: dict) -> int:
    """64-битный хеш полей фида (signed BIGINT)."""

    payload = json.dumps(
        [row.get(name) for name in FEED_FIELDS],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    )

    digest = hashlib.blake2b(
        payload.encode("utf-8"),
        digest_size=8,
    ).digest()

    return int.from_bytes(
        digest,
        "big",
        signed=True,
    )


@dataclass
class FeedDownload:
    path: str | None
    not_modified: bool
    etag: str | None
    last_modified: str | None
    sha256: str | None
    size_bytes: int = 0


def download_feed(
    etag: str | None = None,
    last_modified: str | None = None,
) -> FeedDownload:
    """Скачивает ZIP во временный файл.

    Отправляет If-None-Match / If-Modified-Since,
    если они известны из прошлого импорта.
    Параллельно считает SHA-256 файла.
    Входящий трафик Railway не тарифицирует,
    но 304 экономит и время, и CPU.
    """

    headers = {}

    if etag:
        headers["If-None-Match"] = etag

    if last_modified:
        headers["If-Modified-Since"] = last_modified

    temp_file = tempfile.NamedTemporaryFile(
        suffix=".zip",
        delete=False,
    )

    temp_path = temp_file.name
    temp_file.close()

    digest = hashlib.sha256()
    size = 0

    try:
        with httpx.stream(
            "GET",
            GOLDEN_APPLE_FEED_URL,
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(
                300.0,
                connect=30.0,
            ),
        ) as response:
            if response.status_code == 304:
                os.remove(temp_path)
                return FeedDownload(
                    path=None,
                    not_modified=True,
                    etag=etag,
                    last_modified=last_modified,
                    sha256=None,
                )

            response.raise_for_status()

            with open(
                temp_path,
                "wb",
            ) as output:
                for chunk in response.iter_bytes(
                    chunk_size=1024 * 1024
                ):
                    digest.update(chunk)
                    size += len(chunk)
                    output.write(chunk)

            new_etag = response.headers.get("etag")
            new_last_modified = response.headers.get(
                "last-modified"
            )

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
                        .read(200)
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

        return FeedDownload(
            path=temp_path,
            not_modified=False,
            etag=new_etag,
            last_modified=new_last_modified,
            sha256=digest.hexdigest(),
            size_bytes=size,
        )

    except Exception:
        if os.path.exists(
            temp_path
        ):
            os.remove(
                temp_path
            )

        raise


def iter_feed_items(zip_path: str):
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

        with archive.open(
            json_files[0],
            "r",
        ) as json_file:
            yield from ijson.items(
                json_file,
                "products.item",
            )


def upsert_changed_batch(
    db,
    rows: list[dict],
    version: int,
):
    """Отправляет в базу только изменившиеся строки.

    Сравнение по хешу делается до отправки,
    поэтому неизменившиеся товары вообще
    не попадают в SQL. WHERE в ON CONFLICT —
    дополнительная защита от холостой записи
    на диск, если хеши в памяти устарели.
    """

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

    excluded = statement.excluded
    table = StoreCatalogItem.__table__.c

    match_changed = or_(
        *[
            table[name].is_distinct_from(
                excluded[name]
            )
            for name in MATCH_FIELDS
        ]
    )

    set_ = {
        name: excluded[name]
        for name in FEED_FIELDS
    }

    set_.update(
        {
            "synced_at": excluded.synced_at,
            "content_hash": excluded.content_hash,
            "changed_version": version,
            "match_changed_version": case(
                (match_changed, version),
                else_=table.match_changed_version,
            ),
        }
    )

    statement = statement.on_conflict_do_update(
        index_elements=[
            "store_id",
            "external_id",
        ],
        set_=set_,
        where=or_(
            table.content_hash.is_distinct_from(
                excluded.content_hash
            ),
            table.available.is_distinct_from(
                excluded.available
            ),
        ),
    )

    db.execute(
        statement
    )


def _last_feed_markers(db, store_id: int):
    return db.execute(
        select(
            CatalogSyncRun.feed_etag,
            CatalogSyncRun.feed_last_modified,
            CatalogSyncRun.feed_sha256,
        )
        .where(
            CatalogSyncRun.store_id == store_id,
            CatalogSyncRun.status.in_(
                [STATUS_PUBLISHED, STATUS_NOT_MODIFIED]
            ),
            CatalogSyncRun.feed_sha256.is_not(None),
        )
        .order_by(CatalogSyncRun.id.desc())
        .limit(1)
    ).first()


def _finish_run(
    run_id: int,
    status: str,
    stats: dict,
    error: str | None = None,
    download: FeedDownload | None = None,
):
    db = SessionLocal()
    try:
        run = db.get(CatalogSyncRun, run_id)
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        run.stats = json.loads(
            json.dumps(stats, default=str)
        )
        run.error = error[:500] if error else None
        if download is not None:
            run.feed_etag = download.etag
            run.feed_last_modified = download.last_modified
            run.feed_sha256 = download.sha256
        db.commit()
    finally:
        db.close()


@dataclass(slots=True)
class _ExistingRow:
    id: int
    hash: int | None
    available: bool
    seen: bool


def _load_compact_state(db, store_id: int, metrics):
    """Только (external_id, id, hash, available).

    Это ~30–40 байт на товар вместо полной строки
    с raw_params и ссылками. Читается потоково.
    """

    existing: dict[str, _ExistingRow] = {}

    result = db.execute(
        select(
            StoreCatalogItem.external_id,
            StoreCatalogItem.id,
            StoreCatalogItem.content_hash,
            StoreCatalogItem.available,
        )
        .where(
            StoreCatalogItem.store_id == store_id
        )
        .execution_options(
            yield_per=10000
        )
    )

    for external_id, row_id, row_hash, available in result:
        existing[external_id] = _ExistingRow(
            row_id,
            row_hash,
            bool(available),
            False,
        )

    metrics.set("db_rows_compact_loaded", len(existing))
    return existing


def sync_golden_apple_feed(
    force: bool = False,
):
    """Импорт каталога Golden Apple.

    1. Межпроцессная блокировка: второй процесс
       (старое развёртывание, API /admin/sync)
       не запускает параллельный импорт.
    2. Если фид не изменился (304 или тот же
       SHA-256) — база не трогается, новая версия
       каталога не публикуется.
    3. Изменившийся фид сравнивается с компактными
       хешами из базы; отправляются только новые
       и изменившиеся строки.
    4. Всё применяется одной транзакцией:
       изменённые строки, недоступность исчезнувших
       товаров, инвалидирование отрицательного кэша
       и публикация версии. Ошибка на любом шаге —
       откат, неполная версия не публикуется.

    force=True — игнорировать ETag/хеш и сравнить
    фид с базой (например, после ручной правки).
    """

    metrics = JobMetrics("catalog_import")

    with metrics:
        with advisory_lock(engine, IMPORT_LOCK_NAME) as acquired:
            if not acquired:
                metrics.set("status", "skipped_locked")
                print(
                    "GOLDEN_APPLE_SYNC | SKIPPED | "
                    "another import holds the lock"
                )
                return {
                    "ok": True,
                    "status": "skipped_locked",
                }

            result = _sync_locked(
                metrics,
                force,
            )

    persist_job_run(SessionLocal, metrics)
    return result


def _sync_locked(
    metrics: JobMetrics,
    force: bool,
):
    started_at = datetime.now(timezone.utc)

    db = SessionLocal()
    download: FeedDownload | None = None
    run_id: int | None = None

    try:
        store = get_or_create_store(db)
        store_id = store.id

        markers = _last_feed_markers(db, store_id)

        # Мы держим блокировку импорта, значит
        # «running»-запуски остались от упавшего
        # процесса. Помечаем их, чтобы расписание
        # и мониторинг видели сбой.
        db.execute(
            update(CatalogSyncRun)
            .where(
                CatalogSyncRun.store_id == store_id,
                CatalogSyncRun.status == STATUS_RUNNING,
            )
            .values(
                status=STATUS_FAILED,
                finished_at=started_at,
                error="orphaned: process stopped during import",
            )
        )

        run = CatalogSyncRun(
            store_id=store_id,
            status=STATUS_RUNNING,
            started_at=started_at,
        )
        db.add(run)
        db.commit()
        run_id = run.id

        download = download_feed(
            etag=None if force or not markers else markers.feed_etag,
            last_modified=(
                None if force or not markers
                else markers.feed_last_modified
            ),
        )

        metrics.set("feed_bytes_downloaded", download.size_bytes)

        if download.not_modified or (
            not force
            and markers is not None
            and download.sha256 == markers.feed_sha256
        ):
            metrics.set("status", STATUS_NOT_MODIFIED)
            metrics.set(
                "not_modified_by",
                "http_304"
                if download.not_modified
                else "sha256",
            )

            if download.not_modified and markers is not None:
                # Сохраняем прежние маркеры, чтобы
                # следующий запрос тоже был условным.
                download.sha256 = markers.feed_sha256

            _finish_run(
                run_id,
                STATUS_NOT_MODIFIED,
                metrics.counters,
                download=download,
            )

            print("GOLDEN_APPLE_SYNC | NOT MODIFIED")

            return {
                "ok": True,
                "status": STATUS_NOT_MODIFIED,
                "version": None,
            }

        version = run_id

        # -------------------------
        # Одна транзакция применения
        # -------------------------

        # Сериализуем публикации: даже если
        # advisory lock потерян (обрыв соединения),
        # второй импорт будет ждать здесь.
        db.execute(
            select(Store.id)
            .where(Store.id == store_id)
            .with_for_update()
        )

        existing = _load_compact_state(db, store_id, metrics)

        batch: list[dict] = []
        processed = 0
        skipped_invalid = 0
        inserted = 0
        updated = 0
        unchanged = 0
        returned = 0

        for item in iter_feed_items(download.path):
            row = prepare_row(
                item,
                store_id,
                started_at,
            )

            if not row:
                skipped_invalid += 1
                continue

            processed += 1

            row_hash = content_hash(row)
            current = existing.get(row["external_id"])

            if current is not None:
                current.seen = True

                if (
                    current.hash == row_hash
                    and current.available == row["available"]
                ):
                    unchanged += 1
                    continue

                if not current.available and row["available"]:
                    returned += 1

                updated += 1
                # Повтор external_id в фиде:
                # побеждает последняя запись,
                # как и раньше.
                current.hash = row_hash
                current.available = row["available"]

            else:
                inserted += 1
                existing[row["external_id"]] = _ExistingRow(
                    0,
                    row_hash,
                    row["available"],
                    True,
                )

            row["content_hash"] = row_hash
            row["changed_version"] = version
            row["match_changed_version"] = version
            batch.append(row)

            if len(batch) >= BATCH_SIZE:
                upsert_changed_batch(db, batch, version)
                metrics.inc("batches_sent")
                metrics.inc("rows_sent", len(batch))
                batch = []

            if processed % 20000 == 0:
                print(
                    "GOLDEN_APPLE_SYNC | "
                    f"PROCESSED={processed} "
                    f"CHANGED={inserted + updated}"
                )

        if batch:
            upsert_changed_batch(db, batch, version)
            metrics.inc("rows_sent", len(batch))

        if processed == 0:
            # Пустой фид почти наверняка ошибка
            # поставщика: не делаем весь каталог
            # недоступным.
            raise RuntimeError(
                "Golden Apple feed contains no products"
            )

        # Товары, которых нет в этой выгрузке,
        # становятся недоступными только здесь —
        # в той же транзакции, что и публикация.
        disappeared_ids = [
            state.id
            for state in existing.values()
            if not state.seen
            and state.available
            and state.id
        ]

        for start in range(
            0,
            len(disappeared_ids),
            DISAPPEARED_BATCH_SIZE,
        ):
            chunk = disappeared_ids[
                start:start + DISAPPEARED_BATCH_SIZE
            ]
            db.execute(
                update(StoreCatalogItem)
                .where(StoreCatalogItem.id.in_(chunk))
                .values(
                    available=False,
                    changed_version=version,
                    match_changed_version=version,
                    synced_at=started_at,
                )
            )

        existing.clear()

        # Отрицательный кэш сопоставления:
        # устаревает, только если изменились строки
        # бренда (или, для поиска по частичному
        # бренду, любые match-поля каталога).
        stale_result = db.execute(
            update(ProductMatchMiss)
            .where(
                ProductMatchMiss.store_id == store_id,
                ProductMatchMiss.stale.is_(False),
                or_(
                    (
                        ProductMatchMiss.brand_exact.is_(True)
                    )
                    & select(StoreCatalogItem.id)
                    .where(
                        StoreCatalogItem.store_id == store_id,
                        StoreCatalogItem.brand_normalized
                        == ProductMatchMiss.brand_normalized,
                        StoreCatalogItem.match_changed_version
                        == version,
                    )
                    .exists(),
                    (
                        ProductMatchMiss.brand_exact.is_(False)
                    )
                    & select(StoreCatalogItem.id)
                    .where(
                        StoreCatalogItem.store_id == store_id,
                        StoreCatalogItem.match_changed_version
                        == version,
                    )
                    .exists(),
                ),
            )
            .values(stale=True)
            .execution_options(synchronize_session=False)
        )

        run_row = db.get(CatalogSyncRun, run_id)
        run_row.status = STATUS_PUBLISHED
        run_row.finished_at = datetime.now(timezone.utc)
        run_row.feed_etag = download.etag
        run_row.feed_last_modified = download.last_modified
        run_row.feed_sha256 = download.sha256

        stats = {
            "processed": processed,
            "skipped_invalid": skipped_invalid,
            "inserted": inserted,
            "updated": updated,
            "unchanged": unchanged,
            "returned_to_stock": returned,
            "marked_unavailable": len(disappeared_ids),
            "match_misses_invalidated": stale_result.rowcount,
        }

        for key, value in stats.items():
            metrics.set(key, value)

        metrics.set("status", STATUS_PUBLISHED)
        metrics.set("version", version)

        run_row.stats = json.loads(
            json.dumps(metrics.counters, default=str)
        )

        db.commit()

        result = {
            "ok": True,
            "status": STATUS_PUBLISHED,
            "store": STORE_NAME,
            "version": version,
            **stats,
        }

        print(
            "GOLDEN_APPLE_SYNC | "
            f"DONE | {result}"
        )

        return result

    except Exception as exc:
        db.rollback()
        metrics.ok = False
        metrics.set("status", STATUS_FAILED)

        print(
            "GOLDEN_APPLE_SYNC | "
            f"FAILED | {type(exc).__name__}: "
            f"{str(exc)[:200]}"
        )

        if run_id is not None:
            try:
                _finish_run(
                    run_id,
                    STATUS_FAILED,
                    metrics.counters,
                    error=f"{type(exc).__name__}: {exc}",
                )
            except Exception as finish_exc:
                print(
                    "GOLDEN_APPLE_SYNC | "
                    "FAILED TO RECORD FAILURE:",
                    type(finish_exc).__name__,
                )

        raise

    finally:
        db.close()

        if (
            download is not None
            and download.path
            and os.path.exists(
                download.path
            )
        ):
            os.remove(
                download.path
            )
