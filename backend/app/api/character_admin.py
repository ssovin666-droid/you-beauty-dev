"""Админ-эндпоинты геймификации (X-Admin-Key).

- shade_group товаров: список и ручное редактирование;
- ручная выдача награды за подтверждённую покупку
  (пока нет postback партнёрки).
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.match_admin import check_admin_key
from app.db.session import get_db
from app.models import Product, ShadeGroup, User
from app.services.character import grant_purchase_reward


router = APIRouter()


def require_admin(
    x_admin_key: str = Header(default="", alias="X-Admin-Key"),
) -> None:
    check_admin_key(x_admin_key)


class ShadeGroupIn(BaseModel):
    shade_group: ShadeGroup | None


class PurchaseRewardIn(BaseModel):
    order_id: str = Field(min_length=1, max_length=200)
    user_id: int | None = None
    telegram_user_id: int | None = None


def _product_row(product: Product) -> dict:
    return {
        "id": product.id,
        "brand": product.brand.name if product.brand else None,
        "name": product.name,
        "variant": product.variant,
        "category": product.category,
        "shade_group": product.shade_group.value if product.shade_group else None,
    }


@router.get("/products/shade-groups", dependencies=[Depends(require_admin)])
def list_product_shade_groups(
    missing_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    stmt = select(Product).options(joinedload(Product.brand)).order_by(Product.id.desc())
    if missing_only:
        stmt = stmt.where(Product.shade_group.is_(None))

    rows = db.scalars(stmt.offset(max(0, offset)).limit(max(1, min(limit, 200)))).all()
    return {
        "ok": True,
        "allowed": [group.value for group in ShadeGroup],
        "items": [_product_row(row) for row in rows],
    }


@router.patch("/products/{product_id}/shade-group", dependencies=[Depends(require_admin)])
def update_product_shade_group(
    product_id: int,
    payload: ShadeGroupIn,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    product.shade_group = payload.shade_group
    db.commit()
    db.refresh(product)
    return {"ok": True, "product": _product_row(product)}


@router.post("/character/purchase-reward", dependencies=[Depends(require_admin)])
def admin_grant_purchase_reward(
    payload: PurchaseRewardIn,
    db: Session = Depends(get_db),
):
    user = None
    if payload.user_id is not None:
        user = db.get(User, payload.user_id)
    elif payload.telegram_user_id is not None:
        user = db.scalar(
            select(User).where(User.telegram_user_id == payload.telegram_user_id)
        )

    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    result = grant_purchase_reward(db, user.id, payload.order_id)
    event = result.event

    return {
        "ok": True,
        "created": result.created,
        "reward": {
            "id": event.id,
            "kind": event.kind.value,
            "rolled_rarity": event.rolled_rarity,
            "item_code": event.item.code if event.item else None,
        },
    }
