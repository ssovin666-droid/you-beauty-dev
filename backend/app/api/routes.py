import hashlib
import re
import unicodedata
from dataclasses import asdict

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import (
    Brand,
    ListType,
    Offer,
    OutboundClick,
    Product,
    TrackedItem,
    User,
)
from app.schemas.catalog import (
    ProductOut,
    TrackProductIn,
    TrackRecognizedProductIn,
)
from app.services.recognition import (
    recognize_product_image,
)
from app.services.telegram_auth import (
    get_current_user,
)


router = APIRouter()


def normalize_text(
    value: str | None,
) -> str:
    if not value:
        return ""

    return " ".join(
        value.strip().casefold().split()
    )


def make_slug(
    value: str,
) -> str:
    normalized = unicodedata.normalize(
        "NFKD",
        value,
    )

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
        "telegram_user_id": (
            current_user.telegram_user_id
        ),
        "username": current_user.username,
        "first_name": current_user.first_name,
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

    rows = db.scalars(
        stmt
    ).all()

    return [
        {
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
            "product": (
                ProductOut.model_validate(
                    row.product
                )
            ),
        }
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

    product = db.get(
        Product,
        payload.product_id,
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

        return {
            "ok": True,
            "tracked_item_id": existing.id,
            "product_id": product.id,
            "list_type": list_type.value,
            "moved": True,
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

    return {
        "ok": True,
        "tracked_item_id": row.id,
        "product_id": product.id,
        "list_type": list_type.value,
        "moved": False,
    }


@router.post("/tracked/recognized")
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
            detail="product_name is required",
        )

    brand = None
    brand_name = None

    if payload.brand:
        brand_name = payload.brand.strip()

        if brand_name:
            brand = db.scalar(
                select(Brand).where(
                    func.lower(Brand.name)
                    == brand_name.lower()
                )
            )

            if not brand:
                base_slug = make_slug(
                    brand_name
                )

                slug = base_slug

                existing_slug = db.scalar(
                    select(Brand).where(
                        Brand.slug == slug
                    )
                )

                if existing_slug:
                    suffix = hashlib.sha256(
                        brand_name.encode(
                            "utf-8"
                        )
                    ).hexdigest()[:8]

                    slug = (
                        f"{base_slug}-{suffix}"
                    )

                brand = Brand(
                    name=brand_name,
                    slug=slug,
                )

                db.add(brand)
                db.flush()

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
            canonical_key=canonical_key,
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
        if (
            existing.list_type
            != list_type
        ):
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

    db.refresh(product)
    db.refresh(tracked_item)

    product = db.scalar(
        select(Product)
        .where(
            Product.id == product.id
        )
        .options(
            joinedload(Product.brand)
        )
    )

    return {
        "ok": True,
        "tracked_item_id": (
            tracked_item.id
        ),
        "product_id": product.id,
        "list_type": list_type.value,
        "moved": moved,
        "product": (
            ProductOut.model_validate(
                product
            )
        ),
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


@router.get("/out/{offer_id}")
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

    click = OutboundClick(
        user_id=user_id,
        offer_id=offer.id,
        source=source,
        notification_id=(
            notification_id
        ),
    )

    db.add(click)
    db.commit()

    target = (
        offer.affiliate_url
        or offer.product_url
    )

    return RedirectResponse(
        target,
        status_code=307,
    )
