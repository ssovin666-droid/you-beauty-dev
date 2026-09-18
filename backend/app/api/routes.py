from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import ListType, Offer, OutboundClick, Product, TrackedItem
from app.schemas.catalog import ProductOut, TrackProductIn

router = APIRouter()


@router.get("/health")
def health():
    return {"ok": True, "service": "you-beauty-api"}


@router.get("/products", response_model=list[ProductOut])
def products(db: Session = Depends(get_db)):
    rows = db.scalars(select(Product).options(joinedload(Product.brand)).limit(100)).all()
    return list(rows)


@router.get("/tracked")
def tracked(list_type: str | None = None, user_id: int = 1, db: Session = Depends(get_db)):
    stmt = (
        select(TrackedItem)
        .where(TrackedItem.user_id == user_id)
        .options(joinedload(TrackedItem.product).joinedload(Product.brand))
    )
    if list_type:
        stmt = stmt.where(TrackedItem.list_type == list_type)
    rows = db.scalars(stmt).all()
    return [
        {
            "id": row.id,
            "list_type": row.list_type,
            "notifications_enabled": row.notifications_enabled,
            "product": ProductOut.model_validate(row.product),
        }
        for row in rows
    ]


@router.post("/tracked")
def add_tracked(payload: TrackProductIn, user_id: int = 1, db: Session = Depends(get_db)):
    if payload.list_type not in {"wishlist", "shelf"}:
        raise HTTPException(status_code=400, detail="list_type must be wishlist or shelf")
    product = db.get(Product, payload.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    existing = db.scalar(
        select(TrackedItem).where(
            TrackedItem.user_id == user_id,
            TrackedItem.product_id == payload.product_id,
        )
    )
    if existing:
        existing.list_type = ListType(payload.list_type)
        existing.notifications_enabled = True
        db.commit()
        return {"ok": True, "tracked_item_id": existing.id, "moved": True}

    row = TrackedItem(user_id=user_id, product_id=payload.product_id, list_type=ListType(payload.list_type))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"ok": True, "tracked_item_id": row.id, "moved": False}


@router.post("/recognize")
async def recognize(file: UploadFile):
    # Endpoint contract is ready; provider integration is the next milestone.
    content = await file.read()
    return {
        "status": "provider_pending",
        "filename": file.filename,
        "bytes": len(content),
        "message": "AI recognition provider is not connected yet",
    }


@router.get("/out/{offer_id}")
def outbound(
    offer_id: int,
    user_id: int | None = None,
    source: str | None = None,
    notification_id: str | None = None,
    db: Session = Depends(get_db),
):
    offer = db.get(Offer, offer_id)
    if not offer:
        raise HTTPException(status_code=404, detail="Offer not found")

    click = OutboundClick(
        user_id=user_id,
        offer_id=offer.id,
        source=source,
        notification_id=notification_id,
    )
    db.add(click)
    db.commit()

    target = offer.affiliate_url or offer.product_url
    return RedirectResponse(target, status_code=307)
