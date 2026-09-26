from dataclasses import asdict

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
)
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import (
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
)
from app.services.recognition import (
    recognize_product_image,
)
from app.services.telegram_auth import (
    get_current_user,
)


router = APIRouter()


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
            "tracked_item_id": (
                existing.id
            ),
            "list_type": (
                existing.list_type.value
            ),
            "moved": True,
        }

    row = TrackedItem(
        user_id=current_user.id,
        product_id=payload.product_id,
        list_type=list_type,
        notifications_enabled=True,
    )

    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "tracked_item_id": row.id,
        "list_type": row.list_type.value,
        "moved": False,
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
