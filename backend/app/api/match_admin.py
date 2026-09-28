import os

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.db.session import SessionLocal
from app.models import Product, TrackedItem, ListType
from app.services.product_matcher import find_best_match


router = APIRouter()


def check_admin_key(
    x_admin_key: str,
):
    expected_key = os.getenv(
        "ADMIN_SYNC_KEY",
        "",
    )

    if not expected_key:
        raise HTTPException(
            status_code=500,
            detail="ADMIN_SYNC_KEY is not configured",
        )

    if x_admin_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )


@router.get(
    "/match/golden-apple/test"
)
def test_golden_apple_match(
    x_admin_key: str = Header(
        default="",
        alias="X-Admin-Key",
    ),
):
    check_admin_key(
        x_admin_key
    )

    db = SessionLocal()

    try:
        tracked_item = db.scalar(
            select(TrackedItem)
            .where(
                TrackedItem.list_type
                == ListType.wishlist
            )
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
        )

        if not tracked_item:
            raise HTTPException(
                status_code=404,
                detail=(
                    "No products found "
                    "in Wishlist"
                ),
            )

        product = tracked_item.product

        result = find_best_match(
            db,
            product,
            "golden-apple",
        )

        return {
            "wishlist_product": {
                "id": product.id,
                "brand": (
                    product.brand.name
                    if product.brand
                    else None
                ),
                "name": product.name,
                "size": product.size,
                "variant": product.variant,
            },
            "golden_apple_match": {
                "matched": result.matched,
                "confidence": (
                    result.confidence
                ),
                "catalog_item_id": (
                    result.catalog_item_id
                ),
                "external_id": (
                    result.external_id
                ),
                "brand": (
                    result.brand
                ),
                "name": (
                    result.name
                ),
                "size": (
                    result.size
                ),
                "variant": (
                    result.variant
                ),
                "current_price": (
                    result.current_price
                ),
                "old_price": (
                    result.old_price
                ),
                "currency": (
                    result.currency
                ),
                "available": (
                    result.available
                ),
                "product_url": (
                    result.product_url
                ),
                "affiliate_url": (
                    result.affiliate_url
                ),
            },
        }

    finally:
        db.close()
