import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Offer,
    Product,
    Store,
    StoreCatalogItem,
)


AUTO_MATCH_THRESHOLD = 90.0
POSSIBLE_MATCH_THRESHOLD = 80.0
MAX_CANDIDATES = 1000


@dataclass
class MatchResult:
    matched: bool
    confidence: float

    catalog_item_id: int | None
    external_id: str | None

    store_id: int | None
    store: str | None

    brand: str | None
    name: str | None
    size: str | None
    variant: str | None

    current_price: float | None
    old_price: float | None
    currency: str | None

    available: bool | None

    affiliate_url: str | None
    product_url: str | None

    offer_id: int | None = None


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

    value = value.replace(
        "ё",
        "е",
    )

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


def normalize_size(
    value: str | None,
) -> str:
    if not value:
        return ""

    value = normalize_text(
        value
    )

    value = value.replace(
        ",",
        ".",
    )

    value = re.sub(
        r"\s+",
        "",
        value,
    )

    replacements = {
        "миллилитров": "мл",
        "миллилитра": "мл",
        "миллилитр": "мл",
        "milliliters": "ml",
        "milliliter": "ml",
        "grams": "g",
        "gram": "g",
        "граммов": "г",
        "грамма": "г",
        "грамм": "г",
    }

    for old, new in replacements.items():
        value = value.replace(
            old,
            new,
        )

    return value


def tokenize(
    value: str | None,
) -> set[str]:
    normalized = normalize_text(
        value
    )

    if not normalized:
        return set()

    return {
        token
        for token in normalized.split()
        if len(token) > 1
    }


def remove_brand_from_name(
    name: str,
    brand: str | None,
) -> str:
    normalized_name = normalize_text(
        name
    )

    normalized_brand = normalize_text(
        brand
    )

    if not normalized_brand:
        return normalized_name

    brand_tokens = set(
        normalized_brand.split()
    )

    name_tokens = (
        normalized_name.split()
    )

    cleaned = [
        token
        for token in name_tokens
        if token not in brand_tokens
    ]

    return " ".join(
        cleaned
    ).strip()


def sequence_score(
    a: str,
    b: str,
) -> float:
    if not a or not b:
        return 0.0

    return (
        SequenceMatcher(
            None,
            a,
            b,
        ).ratio()
        * 100
    )


def token_score(
    a: str,
    b: str,
) -> float:
    tokens_a = tokenize(a)
    tokens_b = tokenize(b)

    if not tokens_a or not tokens_b:
        return 0.0

    intersection = len(
        tokens_a & tokens_b
    )

    union = len(
        tokens_a | tokens_b
    )

    if union == 0:
        return 0.0

    return (
        intersection
        / union
        * 100
    )


def size_score(
    product_size: str | None,
    candidate_size: str | None,
) -> float | None:
    a = normalize_size(
        product_size
    )

    b = normalize_size(
        candidate_size
    )

    if not a or not b:
        return None

    if a == b:
        return 100.0

    return sequence_score(
        a,
        b,
    )


def variant_score(
    product_variant: str | None,
    candidate_variant: str | None,
) -> float | None:
    a = normalize_text(
        product_variant
    )

    b = normalize_text(
        candidate_variant
    )

    if not a or not b:
        return None

    if a == b:
        return 100.0

    return max(
        sequence_score(
            a,
            b,
        ),
        token_score(
            a,
            b,
        ),
    )


def calculate_match_score(
    product: Product,
    candidate: StoreCatalogItem,
) -> float:
    product_brand = (
        product.brand.name
        if product.brand
        else None
    )

    product_name = (
        remove_brand_from_name(
            product.name,
            product_brand,
        )
    )

    candidate_name = (
        remove_brand_from_name(
            candidate.name,
            candidate.brand_name,
        )
    )

    name_sequence = sequence_score(
        product_name,
        candidate_name,
    )

    name_tokens = token_score(
        product_name,
        candidate_name,
    )

    name_score = max(
        name_sequence,
        name_tokens,
    )

    total_score = (
        name_score * 0.75
    )

    remaining_weight = 0.25

    candidate_size_score = (
        size_score(
            product.size,
            candidate.size,
        )
    )

    if (
        candidate_size_score
        is not None
    ):
        total_score += (
            candidate_size_score
            * 0.15
        )

        remaining_weight -= 0.15

    candidate_variant_score = (
        variant_score(
            product.variant,
            candidate.variant,
        )
    )

    if (
        candidate_variant_score
        is not None
    ):
        total_score += (
            candidate_variant_score
            * 0.10
        )

        remaining_weight -= 0.10

    if remaining_weight > 0:
        total_score += (
            name_score
            * remaining_weight
        )

    return round(
        min(
            total_score,
            100.0,
        ),
        2,
    )


def empty_result(
    store: Store | None = None,
) -> MatchResult:
    return MatchResult(
        matched=False,
        confidence=0.0,
        catalog_item_id=None,
        external_id=None,
        store_id=(
            store.id
            if store
            else None
        ),
        store=(
            store.name
            if store
            else None
        ),
        brand=None,
        name=None,
        size=None,
        variant=None,
        current_price=None,
        old_price=None,
        currency=None,
        available=None,
        affiliate_url=None,
        product_url=None,
        offer_id=None,
    )


def get_store(
    db: Session,
    store_slug: str,
) -> Store | None:
    return db.scalar(
        select(Store).where(
            Store.slug == store_slug
        )
    )


def get_candidates(
    db: Session,
    product: Product,
    store: Store,
) -> list[StoreCatalogItem]:
    brand_name = (
        product.brand.name
        if product.brand
        else None
    )

    brand_normalized = (
        normalize_text(
            brand_name
        )
    )

    if not brand_normalized:
        return []

    stmt = (
        select(
            StoreCatalogItem
        )
        .where(
            StoreCatalogItem.store_id
            == store.id,

            StoreCatalogItem.brand_normalized
            == brand_normalized,

            StoreCatalogItem.available.is_(
                True
            ),
        )
        .limit(
            MAX_CANDIDATES
        )
    )

    return list(
        db.scalars(
            stmt
        ).all()
    )


def find_best_match(
    db: Session,
    product: Product,
    store_slug: str = "golden-apple",
) -> MatchResult:
    store = get_store(
        db,
        store_slug,
    )

    if not store:
        return empty_result()

    candidates = get_candidates(
        db,
        product,
        store,
    )

    if not candidates:
        return empty_result(
            store
        )

    best_candidate = None
    best_score = 0.0

    for candidate in candidates:
        score = (
            calculate_match_score(
                product,
                candidate,
            )
        )

        if score > best_score:
            best_score = score
            best_candidate = candidate

    if not best_candidate:
        return empty_result(
            store
        )

    return MatchResult(
        matched=(
            best_score
            >= AUTO_MATCH_THRESHOLD
        ),
        confidence=best_score,
        catalog_item_id=(
            best_candidate.id
        ),
        external_id=(
            best_candidate.external_id
        ),
        store_id=store.id,
        store=store.name,
        brand=(
            best_candidate.brand_name
        ),
        name=(
            best_candidate.name
        ),
        size=(
            best_candidate.size
        ),
        variant=(
            best_candidate.variant
        ),
        current_price=(
            float(
                best_candidate.current_price
            )
            if best_candidate.current_price
            is not None
            else None
        ),
        old_price=(
            float(
                best_candidate.old_price
            )
            if best_candidate.old_price
            is not None
            else None
        ),
        currency=(
            best_candidate.currency
        ),
        available=(
            best_candidate.available
        ),
        affiliate_url=(
            best_candidate.affiliate_url
        ),
        product_url=(
            best_candidate.product_url
        ),
        offer_id=None,
    )


def create_or_update_offer(
    db: Session,
    product: Product,
    catalog_item: StoreCatalogItem,
) -> Offer:
    offer = db.scalar(
        select(Offer).where(
            Offer.product_id
            == product.id,

            Offer.store_id
            == catalog_item.store_id,
        )
    )

    product_url = (
        catalog_item.product_url
        or catalog_item.affiliate_url
        or ""
    )

    if not offer:
        offer = Offer(
            product_id=product.id,
            store_id=(
                catalog_item.store_id
            ),
            product_url=product_url,
            affiliate_url=(
                catalog_item.affiliate_url
            ),
            current_price=(
                catalog_item.current_price
            ),
            old_price=(
                catalog_item.old_price
            ),
            in_stock=(
                catalog_item.available
            ),
            updated_at=datetime.utcnow(),
        )

        db.add(
            offer
        )

        db.flush()

        return offer

    offer.product_url = (
        product_url
    )

    offer.affiliate_url = (
        catalog_item.affiliate_url
    )

    offer.current_price = (
        catalog_item.current_price
    )

    offer.old_price = (
        catalog_item.old_price
    )

    offer.in_stock = (
        catalog_item.available
    )

    offer.updated_at = (
        datetime.utcnow()
    )

    db.flush()

    return offer


def link_product_to_best_match(
    db: Session,
    product: Product,
    store_slug: str = "golden-apple",
) -> MatchResult:
    result = find_best_match(
        db,
        product,
        store_slug,
    )

    if (
        not result.matched
        or not result.catalog_item_id
    ):
        return result

    catalog_item = db.get(
        StoreCatalogItem,
        result.catalog_item_id,
    )

    if not catalog_item:
        return result

    # Запоминаем, к какому нашему
    # продукту относится строка фида.
    catalog_item.product_id = (
        product.id
    )

    offer = create_or_update_offer(
        db,
        product,
        catalog_item,
    )

    db.commit()

    result.offer_id = (
        offer.id
    )

    return result
