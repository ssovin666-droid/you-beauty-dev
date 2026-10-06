import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ListType(str, enum.Enum):
    wishlist = "wishlist"
    shelf = "shelf"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )

    username: Mapped[str | None] = mapped_column(
        String(255)
    )

    first_name: Mapped[str | None] = mapped_column(
        String(255)
    )

    traffic_source: Mapped[str | None] = mapped_column(
        String(500)
    )

    bot_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
    )

    image_url: Mapped[str | None] = mapped_column(
        Text
    )


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    brand_id: Mapped[int | None] = mapped_column(
        ForeignKey("brands.id")
    )

    name: Mapped[str] = mapped_column(
        String(500),
        index=True,
    )

    variant: Mapped[str | None] = mapped_column(
        String(255)
    )

    size: Mapped[str | None] = mapped_column(
        String(100)
    )

    category: Mapped[str | None] = mapped_column(
        String(255)
    )

    image_url: Mapped[str | None] = mapped_column(
        Text
    )

    canonical_key: Mapped[str] = mapped_column(
        String(700),
        unique=True,
        index=True,
    )

    brand: Mapped[Brand | None] = relationship()


class TrackedItem(Base):
    __tablename__ = "tracked_items"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "product_id",
            name="uq_user_product",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    list_type: Mapped[ListType] = mapped_column(
        Enum(ListType),
        index=True,
    )

    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    # -------------------------
    # PRICE TRACKING MEMORY
    # -------------------------

    last_seen_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    last_seen_old_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    last_seen_has_discount: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    last_price_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    last_notified_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    last_notified_discount_percent: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    product: Mapped[Product] = relationship()


class BrandSubscription(Base):
    __tablename__ = "brand_subscriptions"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "brand_id",
            name="uq_user_brand",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    brand_id: Mapped[int] = mapped_column(
        ForeignKey(
            "brands.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )


class Store(Base):
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
    )

    slug: Mapped[str] = mapped_column(
        String(255),
        unique=True,
    )

    logo_url: Mapped[str | None] = mapped_column(
        Text
    )

    active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    affiliate_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    affiliate_network: Mapped[str | None] = mapped_column(
        String(100)
    )

    deeplink_template: Mapped[str | None] = mapped_column(
        Text
    )


class StoreCatalogItem(Base):
    __tablename__ = "store_catalog_items"

    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "external_id",
            name="uq_store_catalog_external",
        ),
        Index(
            "ix_store_catalog_store_brand",
            "store_id",
            "brand_normalized",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    product_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="SET NULL",
        ),
        index=True,
    )

    external_id: Mapped[str] = mapped_column(
        String(255)
    )

    group_id: Mapped[str | None] = mapped_column(
        String(255)
    )

    brand_name: Mapped[str | None] = mapped_column(
        String(255)
    )

    brand_normalized: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
    )

    name: Mapped[str] = mapped_column(
        String(1000)
    )

    name_normalized: Mapped[str] = mapped_column(
        String(1000)
    )

    type_prefix: Mapped[str | None] = mapped_column(
        String(500)
    )

    model: Mapped[str | None] = mapped_column(
        String(700)
    )

    variant: Mapped[str | None] = mapped_column(
        String(255)
    )

    size: Mapped[str | None] = mapped_column(
        String(100)
    )

    barcode: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
    )

    category_id: Mapped[str | None] = mapped_column(
        String(255),
        index=True,
    )

    image_url: Mapped[str | None] = mapped_column(
        Text
    )

    product_url: Mapped[str | None] = mapped_column(
        Text
    )

    affiliate_url: Mapped[str | None] = mapped_column(
        Text
    )

    current_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2)
    )

    old_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2)
    )

    currency: Mapped[str | None] = mapped_column(
        String(20)
    )

    available: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        index=True,
    )

    raw_params: Mapped[dict | None] = mapped_column(
        JSON
    )

    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    store: Mapped[Store] = relationship()
    product: Mapped[Product | None] = relationship()


class Offer(Base):
    __tablename__ = "offers"

    __table_args__ = (
        UniqueConstraint(
            "product_id",
            "store_id",
            name="uq_product_store",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    product_url: Mapped[str] = mapped_column(
        Text
    )

    affiliate_url: Mapped[str | None] = mapped_column(
        Text
    )

    current_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2)
    )

    old_price: Mapped[float | None] = mapped_column(
        Numeric(12, 2)
    )

    in_stock: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    store: Mapped[Store] = relationship()


class OutboundClick(Base):
    __tablename__ = "outbound_clicks"

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        index=True,
    )

    offer_id: Mapped[int] = mapped_column(
        ForeignKey(
            "offers.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    source: Mapped[str | None] = mapped_column(
        String(100)
    )

    notification_id: Mapped[str | None] = mapped_column(
        String(255)
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )
