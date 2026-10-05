import hashlib
import os
import re
import unicodedata
from dataclasses import asdict

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.amplitude import track_event
from app.db.session import get_db
from app.models import (
    Brand,
    BrandSubscription,
    ListType,
    Offer,
    OutboundClick,
    Product,
    Store,
    StoreCatalogItem,
    TrackedItem,
    User,
)
from app.schemas.catalog import (
    BrandOut,
    FollowBrandIn,
    ProductOut,
    TrackProductIn,
    TrackRecognizedProductIn,
)
from app.services.golden_apple_feed import sync_golden_apple_feed
from app.services.product_matcher import (
    calculate_match_score,
    get_candidates,
    get_store,
    link_product_to_best_match,
)
from app.services.recognition import recognize_product_image
from app.services.telegram_auth import get_current_user


router = APIRouter()


def normalize_text(value: str | None) -> str:
    if not value:
        return ""

    return " ".join(value.strip().casefold().split())


def make_slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)

    ascii_value = normalized.encode(
        "ascii",
        "ignore",
    ).decode("ascii")

    slug = re.sub(
        r"[^a-zA-Z0-9]+",
        "-",
        ascii_value,
    ).strip("-").lower()

    if slug:
        return slug

    digest = hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()[:12]

    return f"brand-{digest}"


def make_canonical_key(
    brand: str | None,
    product_name: str,
    variant: str | None,
    size: str | None,
) -> str:
    raw = "|".join(
        [
            normalize_text(brand),
            normalize_text(product_name),
            normalize_text(variant),
            normalize_text(size),
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def get_or_create_brand(
    db: Session,
    brand_name: str,
) -> Brand:
    clean_name = brand_name.strip()

    brand = db.scalar(
        select(Brand).where(
            func.lower(Brand.name)
            == clean_name.lower()
        )
    )

    if brand:
        return brand

    base_slug = make_slug(clean_name)
    slug = base_slug

    existing_slug = db.scalar(
        select(Brand).where(
            Brand.slug == slug
        )
    )

    if existing_slug:
        suffix = hashlib.sha256(
            clean_name.encode("utf-8")
        ).hexdigest()[:8]

        slug = f"{base_slug}-{suffix}"

    brand = Brand(
        name=clean_name,
        slug=slug,
    )

    db.add(brand)
    db.flush()

    return brand


def get_offer_payload(
    db: Session,
    product_id: int,
):
    row = db.execute(
        select(
            Offer,
            Store,
        )
        .join(
            Store,
            Store.id == Offer.store_id,
        )
        .where(
            Offer.product_id == product_id,
            Store.slug == "golden-apple",
        )
        .order_by(
            Offer.updated_at.desc()
        )
    ).first()

    if not row:
        return None

    offer, store = row

    currency = db.scalar(
        select(StoreCatalogItem.currency)
        .where(
            StoreCatalogItem.product_id
            == product_id,
            StoreCatalogItem.store_id
            == offer.store_id,
        )
        .order_by(
            StoreCatalogItem.synced_at.desc()
        )
        .limit(1)
    )

    current_price = (
        float(offer.current_price)
        if offer.current_price is not None
        else None
    )

    old_price = (
        float(offer.old_price)
        if offer.old_price is not None
        else None
    )

    has_discount = (
        current_price is not None
        and old_price is not None
        and old_price > current_price
        and old_price > 0
    )

    discount_percent = None

    if has_discount:
        discount_percent = round(
            (
                (
                    old_price
                    - current_price
                )
                / old_price
            )
            * 100
        )

    return {
        "id": offer.id,
        "store": {
            "id": store.id,
            "name": store.name,
            "slug": store.slug,
        },
        "current_price": current_price,
        "old_price": old_price,
        "currency": currency,
        "has_discount": has_discount,
        "discount_percent": discount_percent,
        "in_stock": offer.in_stock,
        "product_url": offer.product_url,
        "affiliate_url": offer.affiliate_url,
    }


def ensure_product_offer(
    db: Session,
    product: Product,
    force: bool = False,
):
    existing_offer = db.scalar(
        select(Offer.id)
        .where(
            Offer.product_id
            == product.id
        )
        .limit(1)
    )

    if existing_offer and not force:
        return

    try:
        result = link_product_to_best_match(
            db,
            product,
            "golden-apple",
        )

        print(
            "PRODUCT_MATCH | "
            f"product_id={product.id} "
            f"matched={result.matched} "
            f"confidence={result.confidence} "
            f"offer_id={result.offer_id} "
            f"url={result.product_url}"
        )

    except Exception as exc:
        db.rollback()

        print(
            "PRODUCT_MATCH | "
            f"FAILED product_id={product.id} | "
            f"{type(exc).__name__}: {exc}"
        )


def serialize_tracked_item(
    db: Session,
    row: TrackedItem,
):
    return {
        "id": row.id,
        "list_type": (
            row.list_type.value
            if isinstance(
                row.list_type,
                ListType,
            )
            else row.list_type
        ),
        "notifications_enabled": (
            row.notifications_enabled
        ),
        "product": ProductOut.model_validate(
            row.product
        ),
        "offer": get_offer_payload(
            db,
            row.product_id,
        ),
    }


@router.get("/health")
def health():
    return {
        "ok": True,
        "service": "you-beauty-api",
    }


@router.get("/me")
def me(
    current_user: User = Depends(
        get_current_user
    ),
):
    return {
        "id": current_user.id,
        "telegram_user_id":
            current_user.telegram_user_id,
        "username":
            current_user.username,
        "first_name":
            current_user.first_name,
    }


@router.get(
    "/products",
    response_model=list[ProductOut],
)
def products(
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(Product)
        .options(
            joinedload(Product.brand)
        )
        .limit(100)
    ).all()

    return list(rows)


@router.get("/tracked")
def tracked(
    list_type: str | None = None,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    stmt = (
        select(TrackedItem)
        .where(
            TrackedItem.user_id
            == current_user.id
        )
        .options(
            joinedload(
                TrackedItem.product
            ).joinedload(
                Product.brand
            )
        )
    )

    if list_type:
        try:
            parsed_list_type = ListType(
                list_type
            )

        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=(
                    "list_type must be "
                    "wishlist or shelf"
                ),
            )

        stmt = stmt.where(
            TrackedItem.list_type
            == parsed_list_type
        )

    rows = list(
        db.scalars(stmt).all()
    )

    for row in rows:
        ensure_product_offer(
            db,
            row.product,
        )

    return [
        serialize_tracked_item(
            db,
            row,
        )
        for row in rows
    ]


@router.post("/tracked")
def add_tracked(
    payload: TrackProductIn,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    try:
        list_type = ListType(
            payload.list_type
        )

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "list_type must be "
                "wishlist or shelf"
            ),
        )

    product = db.scalar(
        select(Product)
        .where(
            Product.id
            == payload.product_id
        )
        .options(
            joinedload(Product.brand)
        )
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    existing = db.scalar(
        select(TrackedItem).where(
            TrackedItem.user_id
            == current_user.id,
            TrackedItem.product_id
            == payload.product_id,
        )
    )

    if existing:
        existing.list_type = list_type
        existing.notifications_enabled = True

        db.commit()
        db.refresh(existing)

        ensure_product_offer(
            db,
            product,
        )

        return {
            "ok": True,
            "tracked_item_id":
                existing.id,
            "product_id":
                product.id,
            "list_type":
                list_type.value,
            "moved":
                True,
            "offer":
                get_offer_payload(
                    db,
                    product.id,
                ),
        }

    row = TrackedItem(
        user_id=current_user.id,
        product_id=product.id,
        list_type=list_type,
        notifications_enabled=True,
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    ensure_product_offer(
        db,
        product,
    )

    return {
        "ok": True,
        "tracked_item_id":
            row.id,
        "product_id":
            product.id,
        "list_type":
            list_type.value,
        "moved":
            False,
        "offer":
            get_offer_payload(
                db,
                product.id,
            ),
    }


@router.post(
    "/tracked/recognized"
)
def add_recognized_product(
    payload: TrackRecognizedProductIn,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    try:
        list_type = ListType(
            payload.list_type
        )

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=(
                "list_type must be "
                "wishlist or shelf"
            ),
        )

    product_name = (
        payload.product_name.strip()
    )

    if not product_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "product_name is required"
            ),
        )

    brand = None
    brand_name = None

    if payload.brand:
        brand_name = (
            payload.brand.strip()
        )

        if brand_name:
            brand = get_or_create_brand(
                db,
                brand_name,
            )

    canonical_key = make_canonical_key(
        brand_name,
        product_name,
        payload.variant,
        payload.size,
    )

    product = db.scalar(
        select(Product)
        .where(
            Product.canonical_key
            == canonical_key
        )
        .options(
            joinedload(Product.brand)
        )
    )

    if not product:
        product = Product(
            brand_id=(
                brand.id
                if brand
                else None
            ),
            name=product_name,
            variant=(
                payload.variant.strip()
                if payload.variant
                else None
            ),
            size=(
                payload.size.strip()
                if payload.size
                else None
            ),
            category=(
                payload.category.strip()
                if payload.category
                else None
            ),
            canonical_key=
                canonical_key,
        )

        db.add(product)
        db.flush()

    existing = db.scalar(
        select(TrackedItem).where(
            TrackedItem.user_id
            == current_user.id,
            TrackedItem.product_id
            == product.id,
        )
    )

    moved = False

    if existing:
        if existing.list_type != list_type:
            moved = True

        existing.list_type = list_type
        existing.notifications_enabled = True

        tracked_item = existing

    else:
        tracked_item = TrackedItem(
            user_id=current_user.id,
            product_id=product.id,
            list_type=list_type,
            notifications_enabled=True,
        )

        db.add(tracked_item)

    db.commit()

    product = db.scalar(
        select(Product)
        .where(
            Product.id
            == product.id
        )
        .options(
            joinedload(Product.brand)
        )
    )

    db.refresh(tracked_item)

    ensure_product_offer(
        db,
        product,
        force=True,
    )

    return {
        "ok": True,
        "tracked_item_id":
            tracked_item.id,
        "product_id":
            product.id,
        "list_type":
            list_type.value,
        "moved":
            moved,
        "product":
            ProductOut.model_validate(
                product
            ),
        "offer":
            get_offer_payload(
                db,
                product.id,
            ),
    }


# НОВОЕ:
# удаляет товар только из Wishlist / Полки
# текущего Telegram-пользователя.
@router.delete(
    "/tracked/{tracked_item_id}"
)
def delete_tracked_item(
    tracked_item_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    tracked_item = db.scalar(
        select(TrackedItem).where(
            TrackedItem.id
            == tracked_item_id,
            TrackedItem.user_id
            == current_user.id,
        )
    )

    if not tracked_item:
        raise HTTPException(
            status_code=404,
            detail="Tracked item not found",
        )

    db.delete(tracked_item)
    db.commit()

    return {
        "ok": True,
        "tracked_item_id":
            tracked_item_id,
    }


@router.get(
    "/brand-subscriptions"
)
def brand_subscriptions(
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(
            BrandSubscription,
            Brand,
        )
        .join(
            Brand,
            Brand.id
            == BrandSubscription.brand_id,
        )
        .where(
            BrandSubscription.user_id
            == current_user.id,
            BrandSubscription.enabled.is_(
                True
            ),
        )
        .order_by(
            Brand.name.asc()
        )
    ).all()

    return [
        {
            "id":
                subscription.id,
            "enabled":
                subscription.enabled,
            "brand":
                BrandOut.model_validate(
                    brand
                ),
        }
        for subscription, brand
        in rows
    ]


@router.post(
    "/brand-subscriptions"
)
def follow_brand(
    payload: FollowBrandIn,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    clean_name = (
        payload.name.strip()
    )

    if not clean_name:
        raise HTTPException(
            status_code=400,
            detail=(
                "Brand name is required"
            ),
        )

    brand = get_or_create_brand(
        db,
        clean_name,
    )

    subscription = db.scalar(
        select(
            BrandSubscription
        ).where(
            BrandSubscription.user_id
            == current_user.id,
            BrandSubscription.brand_id
            == brand.id,
        )
    )

    if subscription:
        subscription.enabled = True

    else:
        subscription = (
            BrandSubscription(
                user_id=current_user.id,
                brand_id=brand.id,
                enabled=True,
            )
        )

        db.add(subscription)

    db.commit()
    db.refresh(subscription)

    return {
        "ok": True,
        "subscription_id":
            subscription.id,
        "brand":
            BrandOut.model_validate(
                brand
            ),
    }


@router.delete(
    "/brand-subscriptions/{brand_id}"
)
def unfollow_brand(
    brand_id: int,
    current_user: User = Depends(
        get_current_user
    ),
    db: Session = Depends(get_db),
):
    subscription = db.scalar(
        select(
            BrandSubscription
        ).where(
            BrandSubscription.user_id
            == current_user.id,
            BrandSubscription.brand_id
            == brand_id,
        )
    )

    if not subscription:
        raise HTTPException(
            status_code=404,
            detail=(
                "Brand subscription "
                "not found"
            ),
        )

    db.delete(subscription)
    db.commit()

    return {
        "ok": True,
    }


@router.post("/recognize")
async def recognize(
    file: UploadFile,
):
    content = await file.read()

    if not content:
        raise HTTPException(
            status_code=400,
            detail="Empty image",
        )

    try:
        result = (
            await recognize_product_image(
                image_bytes=content,
                filename=file.filename,
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    return {
        "status": "ok",
        "result": asdict(result),
    }


@router.get(
    "/out/{offer_id}"
)
def outbound(
    offer_id: int,
    user_id: int | None = None,
    source: str | None = None,
    notification_id: str | None = None,
    db: Session = Depends(get_db),
):
    offer = db.get(
        Offer,
        offer_id,
    )

    if not offer:
        raise HTTPException(
            status_code=404,
            detail="Offer not found",
        )

    target = (
        offer.affiliate_url
        or offer.product_url
    )

    if not target:
        raise HTTPException(
            status_code=404,
            detail="Offer URL not found",
        )

    click_user = None

    if user_id is not None:
        click_user = db.get(
            User,
            user_id,
        )

    click = OutboundClick(
        user_id=(
            click_user.id
            if click_user
            else None
        ),
        offer_id=offer.id,
        source=source,
        notification_id=notification_id,
    )

    db.add(click)
    db.commit()

    if (
        source == "discount"
        and click_user is not None
    ):
        try:
            track_event(
                click_user.telegram_user_id,
                "Opened Partner Site After Discount",
                {
                    "offer_id": offer.id,
                    "store_id": offer.store_id,
                },
            )

        except Exception as exc:
            print(
                "AMPLITUDE_PARTNER_CLICK_ERROR:",
                repr(exc),
            )

    return RedirectResponse(
        target,
        status_code=307,
    )


@router.post(
    "/admin/sync/golden-apple"
)
def start_golden_apple_sync(
    background_tasks: BackgroundTasks,
    x_admin_key: str = Header(
        default="",
        alias="X-Admin-Key",
    ),
):
    expected_key = os.getenv(
        "ADMIN_SYNC_KEY",
        "",
    )

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "ADMIN_SYNC_KEY "
                "is not configured"
            ),
        )

    if x_admin_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )

    background_tasks.add_task(
        sync_golden_apple_feed
    )

    return {
        "ok": True,
        "status": "started",
        "message":
            "Golden Apple sync started",
    }


@router.get(
    "/admin/match/debug"
)
def debug_product_matching(
    limit: int = 10,
    x_admin_key: str = Header(
        default="",
        alias="X-Admin-Key",
    ),
    db: Session = Depends(get_db),
):
    expected_key = os.getenv(
        "ADMIN_SYNC_KEY",
        "",
    )

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "ADMIN_SYNC_KEY "
                "is not configured"
            ),
        )

    if x_admin_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )

    limit = max(
        1,
        min(
            limit,
            30,
        ),
    )

    tracked_rows = list(
        db.scalars(
            select(TrackedItem)
            .options(
                joinedload(
                    TrackedItem.product
                ).joinedload(
                    Product.brand
                )
            )
            .order_by(
                TrackedItem.id.desc()
            )
            .limit(limit)
        ).all()
    )

    store = get_store(
        db,
        "golden-apple",
    )

    if not store:
        raise HTTPException(
            status_code=404,
            detail=(
                "Golden Apple store "
                "not found"
            ),
        )

    diagnostics = []

    for tracked_item in tracked_rows:
        product = tracked_item.product

        candidates = get_candidates(
            db,
            product,
            store,
        )

        scored_candidates = []

        for candidate in candidates:
            score = calculate_match_score(
                product,
                candidate,
            )

            scored_candidates.append(
                {
                    "score":
                        score,
                    "catalog_item_id":
                        candidate.id,
                    "external_id":
                        candidate.external_id,
                    "brand":
                        candidate.brand_name,
                    "name":
                        candidate.name,
                    "model":
                        candidate.model,
                    "size":
                        candidate.size,
                    "variant":
                        candidate.variant,
                    "current_price": (
                        float(
                            candidate.current_price
                        )
                        if candidate.current_price
                        is not None
                        else None
                    ),
                    "old_price": (
                        float(
                            candidate.old_price
                        )
                        if candidate.old_price
                        is not None
                        else None
                    ),
                    "currency":
                        candidate.currency,
                    "product_url":
                        candidate.product_url,
                    "affiliate_url":
                        candidate.affiliate_url,
                }
            )

        scored_candidates.sort(
            key=lambda item:
                item["score"],
            reverse=True,
        )

        diagnostics.append(
            {
                "tracked_item_id":
                    tracked_item.id,
                "product_id":
                    product.id,
                "list_type": (
                    tracked_item.list_type.value
                    if isinstance(
                        tracked_item.list_type,
                        ListType,
                    )
                    else tracked_item.list_type
                ),
                "recognized": {
                    "brand": (
                        product.brand.name
                        if product.brand
                        else None
                    ),
                    "name":
                        product.name,
                    "size":
                        product.size,
                    "variant":
                        product.variant,
                    "category":
                        product.category,
                },
                "candidate_count":
                    len(candidates),
                "top_candidates":
                    scored_candidates[:10],
            }
        )

    return {
        "ok": True,
        "store": {
            "id":
                store.id,
            "name":
                store.name,
            "slug":
                store.slug,
        },
        "items":
            diagnostics,
    }
