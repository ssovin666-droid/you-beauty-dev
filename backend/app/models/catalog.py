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


class ShadeGroup(str, enum.Enum):
    """Эстетика товара для 3D-персонажа.

    bold — яркие, goth — тёмные, nude — нюд,
    pastel — пастель, glow — уход/сияние,
    glitter — блёстки. NULL — не определено.
    """

    bold = "bold"
    goth = "goth"
    nude = "nude"
    pastel = "pastel"
    glow = "glow"
    glitter = "glitter"


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

    # Старое поле оставляем для совместимости
    # с Amplitude и существующей аналитикой.
    # Оно хранит first-touch источник.
    traffic_source: Mapped[str | None] = mapped_column(
        String(500)
    )

    # Первый источник пользователя.
    # После первого заполнения не меняется.
    first_source: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Последний источник запуска бота.
    # Может обновляться при новых /start.
    last_source: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # Первый запуск бота.
    bot_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Последний запуск /start.
    last_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    # Хранится как VARCHAR (не native PG enum),
    # чтобы миграция была одним ALTER TABLE.
    shade_group: Mapped[ShadeGroup | None] = mapped_column(
        Enum(
            ShadeGroup,
            native_enum=False,
            length=20,
            create_constraint=False,
            validate_strings=True,
        ),
        nullable=True,
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

    # Сырые параметры фида нужны только для отладки.
    # deferred: ORM не тянет этот JSON из базы,
    # пока к полю не обратились явно.
    raw_params: Mapped[dict | None] = mapped_column(
        JSON,
        deferred=True,
    )

    # Время последней записи бизнес-полей
    # (а не каждого импорта).
    synced_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
    )

    # 64-битный хеш всех полей из фида.
    # Импорт сравнивает его, чтобы не отправлять
    # в базу неизменившиеся строки.
    content_hash: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    # Версия каталога (catalog_sync_runs.id),
    # в которой строка последний раз изменилась:
    # цена, ссылки, наличие, любые поля фида.
    changed_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # Версия, в которой изменились поля,
    # влияющие на сопоставление (бренд,
    # название, модель, объём, оттенок, наличие).
    # Используется для инвалидирования
    # отрицательного кэша сопоставления.
    match_changed_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
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


# -------------------------
# ФОНОВЫЕ ЗАДАЧИ
# -------------------------


class CatalogSyncRun(Base):
    """Один запуск импорта фида магазина.

    id опубликованного запуска — это версия
    каталога. Версия публикуется только
    вместе с успешным применением изменений
    в одной транзакции.
    """

    __tablename__ = "catalog_sync_runs"

    __table_args__ = (
        Index(
            "ix_catalog_sync_runs_store_status",
            "store_id",
            "status",
            "id",
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
    )

    # running | published | not_modified | failed
    status: Mapped[str] = mapped_column(
        String(20)
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    feed_etag: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    feed_last_modified: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    feed_sha256: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    # Технические метрики запуска (без секретов).
    stats: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )


class ProductMatchMiss(Base):
    """Отрицательный кэш сопоставления.

    Товар уже искали в каталоге магазина
    и уверенного совпадения не нашли.
    Запись перестаёт действовать, если:
    - изменились поля товара (fingerprint);
    - импорт изменил строки каталога
      этого бренда (stale=True).
    """

    __tablename__ = "product_match_misses"

    product_id: Mapped[int] = mapped_column(
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey(
            "stores.id",
            ondelete="CASCADE",
        ),
        primary_key=True,
    )

    product_fingerprint: Mapped[str] = mapped_column(
        String(64)
    )

    brand_normalized: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # Кандидаты найдены по точному бренду
    # (иначе — по частичному совпадению).
    brand_exact: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
    )

    catalog_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    best_score: Mapped[float | None] = mapped_column(
        Numeric(6, 2),
        nullable=True,
    )

    candidate_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    stale: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
    )

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )


class JobState(Base):
    """Водяные знаки фоновых задач.

    Например, последняя версия каталога,
    по которой уже обновлены цены подписок.
    """

    __tablename__ = "job_state"

    key: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
    )

    int_value: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )


class DiscountNotification(Base):
    """Outbox уведомлений о скидке.

    Строка создаётся в той же транзакции,
    что и обновление last_seen_* подписки,
    поэтому повторная обработка той же версии
    каталога не создаёт второе уведомление.
    dedupe_key уникален.
    """

    __tablename__ = "discount_notifications"

    __table_args__ = (
        Index(
            "ix_discount_notifications_due",
            "status",
            "next_attempt_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    dedupe_key: Mapped[str] = mapped_column(
        String(255),
        unique=True,
    )

    tracked_item_id: Mapped[int] = mapped_column(
        ForeignKey(
            "tracked_items.id",
            ondelete="CASCADE",
        ),
        index=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
    )

    offer_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "offers.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    catalog_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    price: Mapped[float | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    discount_percent: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    template_index: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    text: Mapped[str] = mapped_column(
        Text
    )

    button_text: Mapped[str] = mapped_column(
        String(100)
    )

    button_url: Mapped[str] = mapped_column(
        Text
    )

    # pending | sending | sent | failed | uncertain
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
    )

    attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
    )

    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    telegram_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )


class JobRun(Base):
    """Сводка одного запуска фоновой задачи.

    Нужна, чтобы сравнивать нагрузку
    до и после изменений. Только числа:
    без токенов, текстов и ссылок.
    """

    __tablename__ = "job_runs"

    __table_args__ = (
        Index(
            "ix_job_runs_job_started",
            "job",
            "started_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True
    )

    job: Mapped[str] = mapped_column(
        String(64)
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True)
    )

    duration_ms: Mapped[int] = mapped_column(
        Integer
    )

    ok: Mapped[bool] = mapped_column(
        Boolean
    )

    metrics: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )
