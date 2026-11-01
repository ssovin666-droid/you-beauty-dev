import enum
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


def _str_enum(enum_cls: type[enum.Enum], length: int = 30) -> Enum:
    # VARCHAR вместо native PG enum: новые значения
    # можно добавлять без миграции типа.
    return Enum(
        enum_cls,
        native_enum=False,
        length=length,
        create_constraint=False,
        validate_strings=True,
    )


class Archetype(str, enum.Enum):
    bold = "bold"
    goth = "goth"
    nude = "nude"
    pastel = "pastel"
    glow = "glow"
    glitter = "glitter"
    chameleon = "chameleon"


class ItemSlot(str, enum.Enum):
    head = "head"
    eyes = "eyes"
    ray = "ray"
    aura = "aura"


class ItemRarity(str, enum.Enum):
    common = "common"
    rare = "rare"
    epic = "epic"
    secret = "secret"


class ItemSource(str, enum.Enum):
    wishlist_quest = "wishlist_quest"
    purchase = "purchase"
    streak = "streak"


class RewardKind(str, enum.Enum):
    unlock = "unlock"
    item = "item"
    evolution = "evolution"


class UserCharacter(Base):
    __tablename__ = "user_characters"

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )

    # Тип и акцент пересчитываются из полки
    # при каждом GET /character.
    archetype: Mapped[Archetype] = mapped_column(
        _str_enum(Archetype),
        default=Archetype.chameleon,
    )

    accent: Mapped[Archetype | None] = mapped_column(
        _str_enum(Archetype),
        nullable=True,
    )

    # Уровень эволюции: растёт за покупки,
    # когда предмет не выпал.
    evolution: Mapped[int] = mapped_column(Integer, default=0)

    # Seed уникальной формы звезды (число лучей, длины, наклоны).
    # Выдаётся один раз при открытии и больше не меняется:
    # клиент строит форму детерминированно из seed
    # (frontend/src/lib/character/shape.ts).
    shape_seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    unlocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    unboxed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)

    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    slot: Mapped[ItemSlot] = mapped_column(_str_enum(ItemSlot, 20))
    rarity: Mapped[ItemRarity] = mapped_column(_str_enum(ItemRarity, 20))

    # Ключ 3D-ассета на клиенте (см. frontend/src/lib/character/items.ts).
    asset_key: Mapped[str] = mapped_column(String(64))


class UserItem(Base):
    __tablename__ = "user_items"

    __table_args__ = (
        UniqueConstraint("user_id", "item_id", name="uq_user_item"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[ItemSource] = mapped_column(_str_enum(ItemSource, 30))
    obtained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    equipped: Mapped[bool] = mapped_column(default=False)

    item: Mapped[Item] = relationship()


class RewardEvent(Base):
    """Лог выданных наград.

    reward_key уникален в пределах пользователя:
    unlock, quest:first_item, purchase:<order_id>.
    Повторная выдача упирается в UniqueConstraint.
    """

    __tablename__ = "reward_events"

    __table_args__ = (
        UniqueConstraint("user_id", "reward_key", name="uq_user_reward_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    reward_key: Mapped[str] = mapped_column(String(255))
    kind: Mapped[RewardKind] = mapped_column(_str_enum(RewardKind, 20))
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("items.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Покупочные награды: какая редкость выпала на кубике.
    rolled_rarity: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
    # Клиент показал мини-анбоксинг → seen_at.
    seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    item: Mapped[Item | None] = relationship()


class ShareCard(Base):
    """PNG-карточка для сторис.

    Хранится в Postgres: диск на Railway эфемерный.
    Отдаётся публично по случайному токену.
    """

    __tablename__ = "share_cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow
    )
