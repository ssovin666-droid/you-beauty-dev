"""Сравнение нагрузки фоновых задач до и после.

Запускает одинаковый сценарий на указанной версии кода
и считает ТОЧНЫЕ байты на проводе между процессом и
PostgreSQL через локальный TCP-прокси:

    to_db   — байты процесс → БД  (на Railway: egress бота)
    from_db — байты БД → процесс  (на Railway: egress Postgres)

Только для тестовой/локальной базы: схема public
пересоздаётся. Пример:

    python scripts/bench_background_jobs.py \
        --code-dir /path/to/old/backend --mode old \
        --pg-host 127.0.0.1 --pg-port 5433 --db bench_old

Размер каталога и подписок — синтетические параметры
(--items, --users ...). Абсолютные цифры зависят от
реального фида; сравнивать нужно версии между собой.
"""

import argparse
import asyncio
import io
import json
import os
import random
import socket
import sys
import threading
import time
import zipfile
from decimal import Decimal


# -------------------------
# TCP-прокси со счётчиками
# -------------------------


class CountingProxy:
    def __init__(self, target_host, target_port):
        self.target = (target_host, target_port)
        self.to_db = 0
        self.from_db = 0
        self.lock = threading.Lock()
        self.server = socket.socket()
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(64)
        self.port = self.server.getsockname()[1]
        threading.Thread(target=self._accept, daemon=True).start()

    def reset(self):
        with self.lock:
            snapshot = (self.to_db, self.from_db)
            self.to_db = 0
            self.from_db = 0
        return snapshot

    def _accept(self):
        while True:
            client, _ = self.server.accept()
            upstream = socket.create_connection(self.target)
            threading.Thread(target=self._pipe, args=(client, upstream, "to_db"), daemon=True).start()
            threading.Thread(target=self._pipe, args=(upstream, client, "from_db"), daemon=True).start()

    def _pipe(self, source, sink, counter):
        try:
            while True:
                data = source.recv(65536)
                if not data:
                    break
                with self.lock:
                    setattr(self, counter, getattr(self, counter) + len(data))
                sink.sendall(data)
        except OSError:
            pass
        finally:
            for s in (source, sink):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass


# -------------------------
# Синтетические данные
# -------------------------

BRANDS = [f"Brand{i:03d}" for i in range(120)]
WORDS = ["serum", "cream", "tint", "glow", "matte", "velvet", "hydra", "repair", "night",
         "day", "balm", "gel", "fluid", "mask", "toner", "essence", "lipstick", "palette",
         "cushion", "primer", "mist", "oil", "foam", "scrub"]


def make_feed_items(n_items, seed, price_change_share=0.0, drop_share=0.0, base=None):
    rng = random.Random(seed)
    if base is None:
        items = []
        for i in range(n_items):
            brand = rng.choice(BRANDS)
            name = f"{brand} " + " ".join(rng.sample(WORDS, 3)) + f" {i}"
            ext = str(100000 + i)
            items.append({
                "id": ext,
                "group_id": str(rng.randint(1, n_items // 3)),
                "name": name,
                "vendor": brand,
                "typePrefix": rng.choice(["Сыворотка для лица", "Крем для лица", "Помада", "Тинт для губ"]),
                "model": name[:60],
                "barcode": str(4600000000000 + i),
                "categoryId": rng.randint(1, 400),
                "picture": [f"https://cdn.goldapple.example/images/catalog/{ext}/main_{rng.randint(1, 9)}.jpg"],
                "url": (
                    "https://ad.advcake.example/click/partner/1234567/offer/7654321/?erid=LjN8KXYZabc"
                    f"&dl=https%3A%2F%2Fgoldapple.example%2F{ext}-{name.replace(' ', '-').lower()}"
                    "%3Futm_source%3Dadvcake%26utm_medium%3Dcpa%26utm_campaign%3Dfeed"
                ),
                "price": Decimal(rng.randint(300, 15000)),
                "oldprice": None,
                "currencyId": "RUB",
                "available": True,
                "params": {
                    "Бренд": brand,
                    "Объем": str(rng.choice([5, 15, 30, 50, 100, 200])),
                    "Единица измерения": "мл",
                    "Оттенок": rng.choice(["01", "02", "Nude", "Rose", None]) or "",
                    "Страна производства": rng.choice(["Франция", "Корея", "Италия"]),
                    "Тип кожи": "для всех типов кожи",
                    "Назначение": "увлажнение, питание, восстановление",
                    "Активные компоненты": "гиалуроновая кислота, ниацинамид, пептиды",
                    "Пол": "женский",
                    "Артикул": ext,
                },
            })
        return items

    items = [dict(item) for item in base]
    rng = random.Random(seed)
    for item in items:
        if rng.random() < price_change_share:
            item["oldprice"] = item["price"]
            item["price"] = Decimal(int(item["price"] * Decimal("0.8")))
    if drop_share:
        items = [item for item in items if rng.random() >= drop_share]
    return items


def write_feed(path, items):
    payload = json.dumps({"products": items}, ensure_ascii=False, default=str).encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("feed.json", payload)
    with open(path, "wb") as out:
        out.write(buffer.getvalue())
    return len(payload)


# -------------------------
# Сценарий
# -------------------------


class NullBot:
    sent = 0

    async def send_message(self, **kwargs):
        NullBot.sent += 1

        class M:
            message_id = NullBot.sent

        return M()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-dir", required=True)
    parser.add_argument("--mode", choices=["old", "new"], required=True)
    parser.add_argument("--pg-host", default="127.0.0.1")
    parser.add_argument("--pg-port", type=int, default=5432)
    parser.add_argument("--pg-user", default="postgres")
    parser.add_argument("--db", required=True)
    parser.add_argument("--items", type=int, default=30000)
    parser.add_argument("--users", type=int, default=300)
    parser.add_argument("--subscriptions", type=int, default=900)
    parser.add_argument("--unique-products", type=int, default=400)
    parser.add_argument("--unmatched-share", type=float, default=0.2)
    parser.add_argument("--workdir", default="/tmp")
    args = parser.parse_args()

    proxy = CountingProxy(args.pg_host, args.pg_port)
    os.environ["DATABASE_URL"] = (
        f"postgresql://{args.pg_user}@127.0.0.1:{proxy.port}/{args.db}"
    )
    sys.path.insert(0, args.code_dir)

    from sqlalchemy import text

    from app.db.session import SessionLocal, engine
    from app.models import Base, Brand, ListType, Product, TrackedItem, User
    from app.services import golden_apple_feed

    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    Base.metadata.create_all(engine)
    if args.mode == "new":
        from app.db.schema import ensure_job_schema

        ensure_job_schema(engine)

    feed_path = os.path.join(args.workdir, f"bench-feed-{args.mode}.zip")
    current = {"path": feed_path}

    if args.mode == "old":
        def fake_download():
            import shutil

            tmp = current["path"] + ".copy"
            shutil.copy(current["path"], tmp)
            return tmp

        golden_apple_feed.download_feed = fake_download
    else:
        import hashlib
        import shutil

        def fake_download(etag=None, last_modified=None):
            tmp = current["path"] + ".copy"
            shutil.copy(current["path"], tmp)
            data = open(tmp, "rb").read()
            return golden_apple_feed.FeedDownload(
                path=tmp, not_modified=False, etag=None, last_modified=None,
                sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
            )

        golden_apple_feed.download_feed = fake_download

    results = {"mode": args.mode, "params": vars(args) | {"code_dir": "<path>"}}

    def measure(name, fn):
        proxy.reset()
        t0 = time.perf_counter()
        out = fn()
        elapsed = time.perf_counter() - t0
        to_db, from_db = proxy.reset()
        results[name] = {
            "to_db_bytes": to_db,
            "from_db_bytes": from_db,
            "seconds": round(elapsed, 2),
        }
        print(name, results[name], flush=True)
        return out

    base_items = make_feed_items(args.items, 1)
    results["feed_json_bytes"] = write_feed(feed_path, base_items)

    measure("import_initial", golden_apple_feed.sync_golden_apple_feed)

    # пользователи и подписки
    rng = random.Random(2)
    db = SessionLocal()
    brands = {}
    products = []
    for index in range(args.unique_products):
        source = rng.choice(base_items)
        brand_name = source["params"]["Бренд"]
        if brand_name not in brands:
            brand = Brand(name=brand_name, slug=brand_name.lower())
            db.add(brand)
            db.flush()
            brands[brand_name] = brand
        if rng.random() < args.unmatched_share:
            name = "nonexistent " + " ".join(rng.sample(WORDS, 2)) + f" x{index}"
        else:
            name = source["name"].replace(brand_name, "").strip()
        product = Product(
            brand_id=brands[brand_name].id,
            name=name,
            size=f'{source["params"]["Объем"]} мл',
            canonical_key=f"bench-{index}",
        )
        db.add(product)
        products.append(product)
    users = []
    for index in range(args.users):
        user = User(telegram_user_id=10_000_000 + index, username=None)
        db.add(user)
        users.append(user)
    db.flush()
    pairs = set()
    while len(pairs) < args.subscriptions:
        pairs.add((rng.choice(users).id, rng.choice(products).id))
    for user_id, product_id in pairs:
        db.add(TrackedItem(user_id=user_id, product_id=product_id, list_type=ListType.wishlist, notifications_enabled=True))
    db.commit()
    db.close()

    def tick():
        if args.mode == "old":
            from app.services.discount_monitor import check_discount_notifications

            session = SessionLocal()
            try:
                return asyncio.run(check_discount_notifications(NullBot(), session))
            finally:
                session.close()
        from app.services.discount_monitor import (
            apply_catalog_version,
            deliver_notifications,
            initialize_new_subscriptions,
        )

        session = SessionLocal()
        try:
            initialize_new_subscriptions(session)
            apply_catalog_version(session)
        finally:
            session.close()
        return asyncio.run(deliver_notifications(NullBot(), SessionLocal))

    measure("tick_first_after_subscribe", tick)
    measure("tick_steady_unchanged_catalog", tick)

    changed = make_feed_items(0, 3, price_change_share=0.05, drop_share=0.01, base=base_items)
    write_feed(feed_path, changed)
    measure("import_changed_5pct", golden_apple_feed.sync_golden_apple_feed)
    NullBot.sent = 0
    measure("tick_after_changed_import", tick)
    results["notifications_after_change"] = NullBot.sent
    measure("import_identical", golden_apple_feed.sync_golden_apple_feed)
    measure("tick_steady_after", tick)

    print("BENCH_RESULT " + json.dumps(results, default=str))


if __name__ == "__main__":
    main()
