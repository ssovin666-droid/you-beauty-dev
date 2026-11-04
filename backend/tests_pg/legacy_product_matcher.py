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
        r"[^\w\s.+%-]+",
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


def canonical_unit(
    unit: str,
) -> str:
    unit = (
        unit.casefold()
        .replace(".", "")
        .strip()
    )

    if unit in {
        "ml",
        "мл",
        "milliliter",
        "milliliters",
    }:
        return "ml"

    if unit in {
        "g",
        "gr",
        "гр",
        "г",
        "gram",
        "grams",
    }:
        return "g"

    if unit in {
        "pcs",
        "pc",
        "шт",
        "pads",
        "pad",
        "pieces",
        "piece",
    }:
        return "pcs"

    return unit


def normalize_number(
    value: str,
) -> str:
    value = (
        value
        .replace(",", ".")
        .strip()
    )

    try:
        number = float(value)

        if number.is_integer():
            return str(
                int(number)
            )

        return (
            f"{number:.3f}"
            .rstrip("0")
            .rstrip(".")
        )

    except ValueError:
        return value


def extract_measurements(
    value: str | None,
) -> set[tuple[str, str]]:
    if not value:
        return set()

    value = normalize_text(
        value
    )

    pattern = re.compile(
        r"(\d+(?:[.,]\d+)?)\s*"
        r"(ml|мл|g|gr|гр|г|"
        r"pcs|pc|шт|pads?|pieces?)\b",
        flags=re.IGNORECASE,
    )

    result: set[
        tuple[str, str]
    ] = set()

    for number, unit in pattern.findall(
        value
    ):
        result.add(
            (
                normalize_number(
                    number
                ),
                canonical_unit(
                    unit
                ),
            )
        )

    return result


def size_comparison(
    left: str | None,
    right: str | None,
) -> tuple[
    float | None,
    bool,
]:
    left_values = (
        extract_measurements(
            left
        )
    )

    right_values = (
        extract_measurements(
            right
        )
    )

    if (
        not left_values
        or not right_values
    ):
        return None, False

    if (
        left_values
        & right_values
    ):
        return 100.0, False

    left_units = {
        unit
        for _, unit
        in left_values
    }

    right_units = {
        unit
        for _, unit
        in right_values
    }

    comparable_units = (
        left_units
        & right_units
    )

    if comparable_units:
        return 0.0, True

    return None, False


def remove_measurements(
    value: str | None,
) -> str:
    value = normalize_text(
        value
    )

    value = re.sub(
        r"\b\d+(?:[.,]\d+)?\s*"
        r"(ml|мл|g|gr|гр|г|"
        r"pcs|pc|шт|pads?|pieces?)\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def tokenize(
    value: str | None,
) -> list[str]:
    normalized = normalize_text(
        value
    )

    if not normalized:
        return []

    ignored = {
        "the",
        "for",
        "with",
        "and",
        "of",
        "для",
        "и",
        "с",
    }

    return [
        token
        for token
        in normalized.split()
        if (
            len(token) > 1
            and token not in ignored
        )
    ]


def remove_brand_from_name(
    name: str | None,
    brand: str | None,
) -> str:
    name_value = (
        remove_measurements(
            name
        )
    )

    brand_tokens = set(
        tokenize(
            brand
        )
    )

    if not brand_tokens:
        return name_value

    remaining = [
        token
        for token
        in name_value.split()
        if token
        not in brand_tokens
    ]

    return " ".join(
        remaining
    ).strip()


def sequence_score(
    left: str,
    right: str,
) -> float:
    if not left or not right:
        return 0.0

    return (
        SequenceMatcher(
            None,
            left,
            right,
        ).ratio()
        * 100
    )


def name_score(
    left: str,
    right: str,
) -> float:
    left = normalize_text(
        left
    )

    right = normalize_text(
        right
    )

    if not left or not right:
        return 0.0

    if left == right:
        return 100.0

    left_tokens = set(
        tokenize(
            left
        )
    )

    right_tokens = set(
        tokenize(
            right
        )
    )

    if (
        not left_tokens
        or not right_tokens
    ):
        return sequence_score(
            left,
            right,
        )

    common = (
        left_tokens
        & right_tokens
    )

    query_coverage = (
        len(common)
        / len(left_tokens)
    )

    candidate_coverage = (
        len(common)
        / len(right_tokens)
    )

    union = (
        left_tokens
        | right_tokens
    )

    jaccard = (
        len(common)
        / len(union)
        if union
        else 0.0
    )

    ordered_score = (
        sequence_score(
            " ".join(
                sorted(
                    left_tokens
                )
            ),
            " ".join(
                sorted(
                    right_tokens
                )
            ),
        )
        / 100
    )

    coverage_score = (
        query_coverage * 0.55
        + candidate_coverage * 0.25
        + jaccard * 0.10
        + ordered_score * 0.10
    )

    return round(
        min(
            coverage_score
            * 100,
            100.0,
        ),
        2,
    )


def category_evidence(
    product: Product,
    candidate: StoreCatalogItem,
) -> float:
    category_tokens = set(
        tokenize(
            product.category
        )
    )

    if not category_tokens:
        return 0.0

    candidate_text = " ".join(
        [
            candidate.name or "",
            candidate.model or "",
            candidate.type_prefix
            or "",
        ]
    )

    candidate_tokens = set(
        tokenize(
            candidate_text
        )
    )

    if not candidate_tokens:
        return 0.0

    common = (
        category_tokens
        & candidate_tokens
    )

    return (
        len(common)
        / len(category_tokens)
        * 100
    )


def variant_evidence(
    product: Product,
    candidate: StoreCatalogItem,
) -> float | None:
    if (
        not product.variant
        or not candidate.variant
    ):
        return None

    left = normalize_text(
        product.variant
    )

    right = normalize_text(
        candidate.variant
    )

    if left == right:
        return 100.0

    return name_score(
        left,
        right,
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

    n_score = name_score(
        product_name,
        candidate_name,
    )

    s_score, size_conflict = (
        size_comparison(
            product.size,
            candidate.size,
        )
    )

    v_score = (
        variant_evidence(
            product,
            candidate,
        )
    )

    c_score = (
        category_evidence(
            product,
            candidate,
        )
    )

    score = (
        n_score * 0.78
    )

    remaining = 0.22

    if s_score is not None:
        score += (
            s_score * 0.17
        )

        remaining -= 0.17

    if v_score is not None:
        score += (
            v_score * 0.05
        )

        remaining -= 0.05

    if remaining > 0:
        category_weight = min(
            remaining,
            0.07,
        )

        score += (
            c_score
            * category_weight
        )

        remaining -= (
            category_weight
        )

    if remaining > 0:
        score += (
            n_score
            * remaining
        )

    if size_conflict:
        score -= 25

    return round(
        max(
            0.0,
            min(
                score,
                100.0,
            ),
        ),
        2,
    )


def is_confident_match(
    product: Product,
    candidate: StoreCatalogItem,
    score: float,
) -> bool:
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

    product_tokens = set(
        tokenize(
            product_name
        )
    )

    candidate_tokens = set(
        tokenize(
            candidate_name
        )
    )

    s_score, size_conflict = (
        size_comparison(
            product.size,
            candidate.size,
        )
    )

    if size_conflict:
        return False

    # Полностью одинаковое основное название.
    if (
        product_name
        and product_name
        == candidate_name
    ):
        return True

    # Один вариант названия является
    # расширенной версией другого.
    subset_match = (
        bool(product_tokens)
        and bool(candidate_tokens)
        and (
            product_tokens
            <= candidate_tokens
            or candidate_tokens
            <= product_tokens
        )
    )

    # Если совпадает название и объём,
    # это очень сильный сигнал.
    if (
        subset_match
        and s_score == 100.0
        and score >= 68
    ):
        return True

    # Более длинные названия безопаснее
    # связывать по сильному совпадению.
    shortest_name_length = min(
        len(product_tokens),
        len(candidate_tokens),
    )

    if (
        shortest_name_length >= 3
        and score >= 78
    ):
        return True

    # Очень высокий общий score.
    if score >= 88:
        return True

    # Короткие названия вроде
    # "Mellow Gel" требуют ещё
    # одного подтверждающего признака.
    if (
        subset_match
        and shortest_name_length <= 2
        and category_evidence(
            product,
            candidate,
        ) >= 40
        and score >= 70
    ):
        return True

    return False


def get_store(
    db: Session,
    store_slug: str,
) -> Store | None:
    return db.scalar(
        select(Store).where(
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

    exact_candidates = list(
        db.scalars(
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
        ).all()
    )

    if exact_candidates:
        return exact_candidates

    brand_words = [
        word
        for word
        in brand_normalized.split()
        if len(word) >= 3
    ]

    if not brand_words:
        return []

    conditions = [
        StoreCatalogItem.brand_normalized.ilike(
            f"%{word}%"
        )
        for word
        in brand_words
    ]

    return list(
        db.scalars(
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


def result_from_candidate(
    store: Store,
    candidate: StoreCatalogItem,
    confidence: float,
    matched: bool,
) -> MatchResult:
    return MatchResult(
        matched=matched,
        confidence=confidence,
        catalog_item_id=(
            candidate.id
        ),
        external_id=(
            candidate.external_id
        ),
        store_id=(
            store.id
        ),
        store=(
            store.name
        ),
        brand=(
            candidate.brand_name
        ),
        name=(
            candidate.name
        ),
        size=(
            candidate.size
        ),
        variant=(
            candidate.variant
        ),
        current_price=(
            float(
                candidate.current_price
            )
            if candidate.current_price
            is not None
            else None
        ),
        old_price=(
            float(
                candidate.old_price
            )
            if candidate.old_price
            is not None
            else None
        ),
        currency=(
            candidate.currency
        ),
        available=(
            candidate.available
        ),
        affiliate_url=(
            candidate.affiliate_url
        ),
        product_url=(
            candidate.product_url
        ),
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

    # Если мы уже когда-то подтвердили
    # связь, повторно угадывать не надо.
    linked = db.scalar(
        select(
            StoreCatalogItem
        )
        .where(
            StoreCatalogItem.store_id
            == store.id,
            StoreCatalogItem.product_id
            == product.id,
            StoreCatalogItem.available.is_(
                True
            ),
        )
        .order_by(
            StoreCatalogItem.synced_at.desc()
        )
        .limit(1)
    )

    if linked:
        return result_from_candidate(
            store,
            linked,
            100.0,
            True,
        )

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
        is_confident_match(
            product,
            best_candidate,
            best_score,
        )
    )

    return result_from_candidate(
        store,
        best_candidate,
        best_score,
        matched,
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
            product_id=(
                product.id
            ),
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
