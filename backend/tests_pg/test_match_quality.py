"""Качество сопоставления не изменилось.

Сравниваем новую реализацию (лёгкие кандидаты,
ORDER BY id, отрицательный кэш выключен) с исходной
product_matcher.py из HEAD на одинаковом
синтетическом каталоге с шумными названиями,
объёмами, оттенками и брендами с «&».
"""

import random

from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.models import Brand, Product
from app.services import product_matcher as new_matcher
from app.services.golden_apple_feed import sync_golden_apple_feed
from tests_pg import legacy_product_matcher as old_matcher
from tests_pg.conftest import feed_item


BRANDS = ["Clarins", "Dior", "Rom&nd", "La Roche-Posay", "Estée Lauder", "MAC", "Kiko Milano", "3INA"]
LINES = ["Double Serum", "Hydra Cream", "Lip Tint", "Glow Foundation", "Velvet Matte Lipstick",
         "Cleansing Gel", "Eye Shadow Palette", "Body Lotion", "Hair Mask", "Sun Fluid SPF50",
         "Juicy Lasting Tint", "Effaclar Duo", "Cicaplast Baume B5", "Night Repair", "Mellow Gel"]
SHADES = [None, "01 Nude", "02 Rose", "03 Berry", "N1", "N2", "Ivory", "Sand"]
VOLUMES = [None, 5, 15, 30, 50, 100, 200, 400]


def build_catalog(rng):
    items = []
    next_id = 1
    for brand in BRANDS:
        for line in LINES:
            for volume in rng.sample(VOLUMES, 3):
                for shade in rng.sample(SHADES, 2):
                    name = f"{brand} {line}"
                    if rng.random() < 0.3:
                        name += " для лица"
                    items.append(
                        feed_item(
                            next_id,
                            brand,
                            name,
                            rng.randint(300, 9000),
                            volume=volume,
                            shade=shade,
                        )
                    )
                    next_id += 1
    return items


def make_products(db, rng, items):
    products = []
    for index in range(250):
        source = rng.choice(items)
        brand = source["params"]["Бренд"]
        name = source["name"].replace(brand, "").strip()
        roll = rng.random()
        if roll < 0.2:
            name = name.lower()
        elif roll < 0.35:
            name = name + " new"
        elif roll < 0.45:
            name = " ".join(reversed(name.split()))
        elif roll < 0.55:
            name = "Unknown " + name.split()[0]
        size = None
        if source["params"].get("Объем") and rng.random() < 0.8:
            size = f'{source["params"]["Объем"]} ml'
            if rng.random() < 0.15:
                size = "999 ml"
        variant = source["params"].get("Оттенок") if rng.random() < 0.7 else None
        brand_row = db.scalar(select(Brand).where(Brand.name == brand))
        if brand_row is None:
            brand_row = Brand(name=brand, slug=f"b{len(products)}-{index}")
            db.add(brand_row)
            db.flush()
        product = Product(
            brand_id=brand_row.id,
            name=name,
            size=size,
            variant=variant,
            category="Уход за лицом" if rng.random() < 0.3 else None,
            canonical_key=f"p{index}",
        )
        db.add(product)
        products.append(product)
    db.commit()
    return [
        db.scalar(select(Product).where(Product.id == p.id).options(joinedload(Product.brand)))
        for p in products
    ]


def test_match_quality_is_unchanged(db, fake_feed):
    rng = random.Random(20261104)
    items = build_catalog(rng)
    fake_feed.set_items(items)
    sync_golden_apple_feed()

    products = make_products(db, rng, items)

    same = 0
    matched = 0
    for product in products:
        old = old_matcher.find_best_match(db, product, "golden-apple")
        new = new_matcher.find_best_match(db, product, "golden-apple")

        assert new.matched == old.matched, product.id
        assert new.confidence == old.confidence, product.id

        if old.catalog_item_id == new.catalog_item_id:
            same += 1
        else:
            # Разный победитель допустим только при равном
            # счёте (порядок кандидатов без ORDER BY не задан).
            old_item = db.get(old_matcher.StoreCatalogItem, old.catalog_item_id)
            new_item = db.get(old_matcher.StoreCatalogItem, new.catalog_item_id)
            assert old_matcher.calculate_match_score(product, old_item) == \
                new_matcher.calculate_match_score(product, new_item)

        matched += int(new.matched)

    print(f"MATCH_QUALITY products={len(products)} matched={matched} same_item={same}")
    assert matched > 50
    assert same >= len(products) * 0.95
