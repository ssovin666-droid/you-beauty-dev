import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Offer,
    Product,
    Store,
    StoreCatalogItem,
)


# Внутри одного и того же бренда нам не нужен порог 90%.
# 76% достаточно для автоматического связывания,
# но ниже мы дополнительно проверяем размер/вариант.
AUTO_MATCH_THRESHOLD = 76.0

MAX_CANDIDATES = 5000


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

    value = value.replace(
        "&",
        " and ",
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

    value = re.sub(
        r"\s+",
        "",
        value,
    )

    return value


def tokenize(
    value: str | None,
) -> set[str]:
    value = normalize_text(
        value
    )

    if not value:
        return set()

    ignored = {
        "the",
        "for",
        "with",
        "and",
        "для",
        "с",
        "и",
        "of",
    }

    return {
        token
        for token in value.split()
        if len(token) > 1
        and token not in ignored
    }


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


def token_overlap_score(
    a: str,
    b: str,
) -> float:
    a_tokens = tokenize(a)
    b_tokens = tokenize(b)

    if not a_tokens or not b_tokens:
        return 0.0

    common = (
        a_tokens
        & b_tokens
    )

    # Нам важнее, чтобы слова из распознанного
    # названия присутствовали в названии магазина.
    denominator = min(
        len(a_tokens),
        len(b_tokens),
    )

    if denominator == 0:
        return 0.0

    return (
        len(common)
        / denominator
        * 100
    )


def remove_brand_from_name(
    name: str | None,
    brand: str | None,
) -> str:
    name_normalized = (
        normalize_text(name)
    )

    brand_tokens = tokenize(
        brand
    )

    if not brand_tokens:
        return name_normalized

    remaining = [
        token
        for token
        in name_normalized.split()
        if token
        not in brand_tokens
    ]

    return " ".join(
        remaining
    )


def size_score(
    product_size: str | None,
    candidate_size: str | None,
) -> float | None:
    left = normalize_size(
        product_size
    )

    right = normalize_size(
        candidate_size
    )

    if not left or not right:
        return None

    if left == right:
        return 100.0

    return sequence_score(
        left,
        right,
    )


def variant_score(
    product_variant: str | None,
    candidate_variant: str | None,
) -> float | None:
    left = normalize_text(
        product_variant
    )

    right = normalize_text(
        candidate_variant
    )

    if not left or not right:
        return None

    if left == right:
        return 100.0

    return max(
        sequence_score(
            left,
            right,
        ),
        token_overlap_score(
            left,
            right,
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

    name_sequence = (
        sequence_score(
            product_name,
            candidate_name,
        )
    )

    token_overlap = (
        token_overlap_score(
            product_name,
            candidate_name,
        )
    )

    # Для названий косметики совпадение ключевых слов
    # часто важнее полного порядка слов.
    name_score = max(
        name_sequence,
        token_overlap,
    )

    score = (
        name_score * 0.78
    )

    used_weight = 0.78

    s_score = size_score(
        product.size,
        candidate.size,
    )

    if s_score is not None:
        score += (
            s_score * 0.14
        )

        used_weight += 0.14

        # Если объём явно отличается,
        # сильно штрафуем совпадение.
        if s_score < 60:
            score -= 18

    v_score = variant_score(
        product.variant,
        candidate.variant,
    )

    if v_score is not None:
        score += (
            v_score * 0.08
        )

        used_weight += 0.08

        if v_score < 45:
            score -= 10

    # Если размер/вариант отсутствуют,
    # оставшийся вес отдаём названию.
    if used_weight < 1:
        score += (
            name_score
            * (1 - used_weight)
        )

    return round(
        max(
            0,
            min(
                score,
                100,
            ),
        ),
        2,
    )


def get_store(
    db: Session,
    store_slug: str,
) -> Store | None:
    return db.scalar(
        select(Store)
        .where(
            Store.slug
            == store_slug
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

    #
    # Сначала пробуем точное совпадение бренда.
    #
    stmt = (
        select(
            StoreCatalogItem
        )
        .where(
            StoreCatalogItem.store_id
            == store.id,

            StoreCatalogItem.available.is_(
                True
            ),

            StoreCatalogItem.brand_normalized
            == brand_normalized,
        )
        .limit(
            MAX_CANDIDATES
        )
    )

    candidates = list(
        db.scalars(
            stmt
        ).all()
    )

    if candidates:
        return candidates

    #
    # Fallback:
    # если AI написал бренд чуть иначе,
    # ищем по названию бренда из фида.
    #
    brand_words = [
        word
        for word
        in brand_normalized.split()
        if len(word) >= 3
    ]

    if not brand_words:
        return []

    conditions = []

    for word in brand_words:
        conditions.append(
            StoreCatalogItem.brand_normalized.ilike(
                f"%{word}%"
            )
        )

    stmt = (
        select(
            StoreCatalogItem
        )
        .where(
            StoreCatalogItem.store_id
            == store.id,

            StoreCatalogItem.available.is_(
                True
            ),

            or_(
                *conditions
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
            best_candidate = (
                candidate
            )

    if not best_candidate:
        return empty_result(
            store
        )

    matched = (
        best_score
        >= AUTO_MATCH_THRESHOLD
    )

    return MatchResult(
        matched=matched,
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
        select(Offer)
        .where(
            Offer.product_id
            == product.id,

            Offer.store_id
            == catalog_item.store_id,
        )
    )

    #
    # В приоритете обычная ссылка на товар,
    # но если её нет — используем affiliate URL.
    #
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
            product_url=(
                product_url
            ),
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
            updated_at=(
                datetime.utcnow()
            ),
        )

        db.add(
            offer
        )

    else:
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

    print(
        "PRODUCT_MATCH | "
        f"product_id={product.id} "
        f"name={product.name!r} "
        f"matched={result.matched} "
        f"confidence={result.confidence} "
        f"catalog_item_id="
        f"{result.catalog_item_id}"
    )

    if (
        not result.matched
        or result.catalog_item_id
        is None
    ):
        return result

    catalog_item = db.get(
        StoreCatalogItem,
        result.catalog_item_id,
    )

    if not catalog_item:
        return result

    #
    # Навсегда связываем строку Golden Apple
    # с нашим Product.
    #
    catalog_item.product_id = (
        product.id
    )

    #
    # И сразу создаём Offer:
    # цена + старая цена + ссылка + наличие.
    #
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
