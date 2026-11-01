"""Геймификация: 3D-персонаж cosmi.

Вся выдача наград живёт здесь и выполняется
только на сервере. Идемпотентность — через
RewardEvent(user_id, reward_key) с UniqueConstraint:
вторая попытка выдать ту же награду падает
на IntegrityError внутри SAVEPOINT и откатывается.
"""

from __future__ import annotations

from app.core.amplitude import track_event

import random
import secrets
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Archetype,
    Item,
    ItemRarity,
    ItemSlot,
    ItemSource,
    ListType,
    Product,
    RewardEvent,
    RewardKind,
    ShadeGroup,
    TrackedItem,
    User,
    UserCharacter,
    UserItem,
)


# -------------------------
# CONFIG
# -------------------------

UNLOCK_SHELF_TARGET = 10
FIRST_ITEM_WISHLIST_TARGET = 5
FIRST_ITEM_CODE = "clip"

# Seed формы: положительный int32.
SHAPE_SEED_MAX = 2**31 - 1

# «больше 3 из 10» → доля лидера должна быть > 30%.
CHAMELEON_MAX_SHARE = 0.3

# Порядок для стабильного разрешения ничьих.
SHADE_ORDER: tuple[ShadeGroup, ...] = (
    ShadeGroup.bold,
    ShadeGroup.goth,
    ShadeGroup.nude,
    ShadeGroup.pastel,
    ShadeGroup.glow,
    ShadeGroup.glitter,
)

RARITY_WEIGHTS: dict[ItemRarity, int] = {
    ItemRarity.common: 70,
    ItemRarity.rare: 22,
    ItemRarity.epic: 7,
    ItemRarity.secret: 1,
}

SLOT_ORDER: tuple[ItemSlot, ...] = (
    ItemSlot.head,
    ItemSlot.eyes,
    ItemSlot.ray,
    ItemSlot.aura,
)

# Каталог предметов. asset_key → 3D-модель
# в frontend/src/lib/character/scene.ts.
ITEM_CATALOG: tuple[dict, ...] = (
    {"code": "clip", "name": "Заколка-краб", "slot": ItemSlot.head, "rarity": ItemRarity.common},
    {"code": "bow", "name": "Бантик", "slot": ItemSlot.head, "rarity": ItemRarity.common},
    {"code": "beanie", "name": "Шапочка", "slot": ItemSlot.head, "rarity": ItemRarity.rare},
    {"code": "crown", "name": "Корона", "slot": ItemSlot.head, "rarity": ItemRarity.secret},
    {"code": "glasses", "name": "Очки", "slot": ItemSlot.eyes, "rarity": ItemRarity.rare},
    {"code": "heart_glasses", "name": "Очки-сердечки", "slot": ItemSlot.eyes, "rarity": ItemRarity.epic},
    {"code": "bracelet", "name": "Браслет из бусин", "slot": ItemSlot.ray, "rarity": ItemRarity.common},
    {"code": "ring", "name": "Золотое колечко", "slot": ItemSlot.ray, "rarity": ItemRarity.rare},
    {"code": "halo", "name": "Нимб", "slot": ItemSlot.aura, "rarity": ItemRarity.epic},
    {"code": "dust", "name": "Звёздная пыль", "slot": ItemSlot.aura, "rarity": ItemRarity.secret},
)


def new_shape_seed() -> int:
    return secrets.randbelow(SHAPE_SEED_MAX) + 1


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -------------------------
# ARCHETYPE
# -------------------------

@dataclass(frozen=True)
class ArchetypeResult:
    archetype: Archetype
    accent: Archetype | None
    counts: dict[str, int]
    classified: int


def compute_archetype(
    shade_groups: Iterable[ShadeGroup | str | None],
) -> ArchetypeResult:
    """Тип = самый частый shade_group, акцент = второй.

    Товары без shade_group не учитываются.
    Если доля лидера ≤ 30% (≤ 3 из 10) — chameleon.
    Ничьи решаются фиксированным порядком SHADE_ORDER.
    """

    counter: Counter[ShadeGroup] = Counter()

    for raw in shade_groups:
        if raw is None:
            continue
        try:
            counter[ShadeGroup(raw)] += 1
        except ValueError:
            continue

    counts = {group.value: counter.get(group, 0) for group in SHADE_ORDER}
    total = sum(counter.values())

    if total == 0:
        return ArchetypeResult(Archetype.chameleon, None, counts, 0)

    ranked = sorted(
        SHADE_ORDER,
        key=lambda group: (-counter.get(group, 0), SHADE_ORDER.index(group)),
    )
    top = ranked[0]
    second = ranked[1]

    top_archetype = Archetype(top.value)
    second_archetype = (
        Archetype(second.value) if counter.get(second, 0) > 0 else None
    )

    if counter[top] / total <= CHAMELEON_MAX_SHARE:
        return ArchetypeResult(Archetype.chameleon, top_archetype, counts, total)

    return ArchetypeResult(
        top_archetype,
        second_archetype or top_archetype,
        counts,
        total,
    )


# -------------------------
# CATALOG
# -------------------------

def seed_items(db: Session) -> None:
    existing = {item.code: item for item in db.scalars(select(Item)).all()}

    for spec in ITEM_CATALOG:
        item = existing.get(spec["code"])
        if item is None:
            db.add(
                Item(
                    code=spec["code"],
                    name=spec["name"],
                    slot=spec["slot"],
                    rarity=spec["rarity"],
                    asset_key=spec["code"],
                )
            )
        else:
            item.name = spec["name"]
            item.slot = spec["slot"]
            item.rarity = spec["rarity"]

    db.commit()


# -------------------------
# QUERIES
# -------------------------

def get_or_create_character(db: Session, user_id: int) -> UserCharacter:
    character = db.scalar(
        select(UserCharacter).where(UserCharacter.user_id == user_id)
    )
    if character:
        return character

    character = UserCharacter(
        user_id=user_id,
        archetype=Archetype.chameleon,
        evolution=0,
    )

    try:
        with db.begin_nested():
            db.add(character)
    except IntegrityError:
        character = db.scalar(
            select(UserCharacter).where(UserCharacter.user_id == user_id)
        )

    return character


def shelf_shade_groups(db: Session, user_id: int) -> list[ShadeGroup | None]:
    return list(
        db.scalars(
            select(Product.shade_group)
            .join(TrackedItem, TrackedItem.product_id == Product.id)
            .where(
                TrackedItem.user_id == user_id,
                TrackedItem.list_type == ListType.shelf,
            )
        ).all()
    )


def wishlist_count_since(db: Session, user_id: int, since: datetime) -> int:
    return int(
        db.scalar(
            select(func.count(TrackedItem.id)).where(
                TrackedItem.user_id == user_id,
                TrackedItem.list_type == ListType.wishlist,
                TrackedItem.created_at >= _naive_utc(since),
            )
        )
        or 0
    )


def _naive_utc(value: datetime) -> datetime:
    # TrackedItem.created_at пишется через datetime.utcnow (naive),
    # сравниваем в той же системе координат.
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def owned_item_ids(db: Session, user_id: int) -> set[int]:
    return set(
        db.scalars(select(UserItem.item_id).where(UserItem.user_id == user_id)).all()
    )


# -------------------------
# GRANTING
# -------------------------

def _try_grant(
    db: Session,
    *,
    user_id: int,
    reward_key: str,
    kind: RewardKind,
    item: Item | None = None,
    item_source: ItemSource | None = None,
    source: str | None = None,
    rolled_rarity: ItemRarity | None = None,
    character: UserCharacter | None = None,
) -> RewardEvent | None:
    """Одна награда = одна SAVEPOINT-транзакция.

    Возвращает RewardEvent или None, если награда
    с таким reward_key уже была выдана.
    """

    try:
        with db.begin_nested():
            event = RewardEvent(
                user_id=user_id,
                reward_key=reward_key,
                kind=kind,
                item_id=item.id if item else None,
                source=source,
                rolled_rarity=rolled_rarity.value if rolled_rarity else None,
            )
            db.add(event)
            # Дубликат упадёт здесь, до побочных эффектов.
            db.flush()

            if kind == RewardKind.item and item is not None:
                db.add(
                    UserItem(
                        user_id=user_id,
                        item_id=item.id,
                        source=item_source or ItemSource.purchase,
                        obtained_at=utcnow(),
                        equipped=False,
                    )
                )
                db.flush()

            if kind == RewardKind.evolution and character is not None:
                character.evolution = (character.evolution or 0) + 1
                db.flush()

            if kind == RewardKind.unlock and character is not None:
                character.unlocked_at = character.unlocked_at or utcnow()
                if character.shape_seed is None:
                    character.shape_seed = new_shape_seed()
                db.flush()

        return event

    except IntegrityError:
        return None


def evaluate_character(db: Session, user: User) -> UserCharacter:
    """Пересчитывает тип и выдаёт награды за пороги.

    Вызывается из GET /character, поэтому должна
    быть идемпотентной и дешёвой.
    """

    character = get_or_create_character(db, user.id)

    groups = shelf_shade_groups(db, user.id)
    result = compute_archetype(groups)
    character.archetype = result.archetype
    character.accent = result.accent

    if character.unlocked_at is None and len(groups) >= UNLOCK_SHELF_TARGET:
        _try_grant(
            db,
            user_id=user.id,
            reward_key="unlock",
            kind=RewardKind.unlock,
            source="shelf",
            character=character,
        )
        db.refresh(character)

    # Открытые до появления случайных форм получают seed один раз.
    if character.unlocked_at is not None and character.shape_seed is None:
        character.shape_seed = new_shape_seed()

    if character.unlocked_at is not None:
        wishlist_after = wishlist_count_since(db, user.id, character.unlocked_at)

        if wishlist_after >= FIRST_ITEM_WISHLIST_TARGET:
            item = _first_quest_item(db, user.id)

            if item is not None:
                _try_grant(
                    db,
                    user_id=user.id,
                    reward_key="quest:first_item",
                    kind=RewardKind.item,
                    item=item,
                    item_source=ItemSource.wishlist_quest,
                    source=ItemSource.wishlist_quest.value,
                )
            else:
                # Всё уже собрано покупками — квест закрываем эволюцией.
                _try_grant(
                    db,
                    user_id=user.id,
                    reward_key="quest:first_item",
                    kind=RewardKind.evolution,
                    source=ItemSource.wishlist_quest.value,
                    character=character,
                )

    db.commit()
    db.refresh(character)
    return character


def _first_quest_item(db: Session, user_id: int) -> Item | None:
    """Заколка; если она уже выпала с покупки — первый
    неполученный предмет, от обычных к редким."""

    owned = owned_item_ids(db, user_id)
    preferred = db.scalar(select(Item).where(Item.code == FIRST_ITEM_CODE))
    if preferred is not None and preferred.id not in owned:
        return preferred

    rarity_rank = {rarity: index for index, rarity in enumerate(RARITY_WEIGHTS)}
    rest = sorted(
        (item for item in db.scalars(select(Item)).all() if item.id not in owned),
        key=lambda item: (rarity_rank[item.rarity], item.id),
    )
    return rest[0] if rest else None


def roll_rarity(rng: random.Random | None = None) -> ItemRarity:
    rng = rng or random.Random()
    rarities = list(RARITY_WEIGHTS)
    weights = [RARITY_WEIGHTS[r] for r in rarities]
    return rng.choices(rarities, weights=weights, k=1)[0]


@dataclass
class PurchaseRewardResult:
    created: bool
    event: RewardEvent


def grant_purchase_reward(
    db: Session,
    user_id: int,
    order_id: str,
    rng: random.Random | None = None,
) -> PurchaseRewardResult:
    """Награда за подтверждённую покупку.

    Вызывается из postback партнёрки (в будущем)
    и из админки. Клики /out наград не дают.

    Выпадает редкость по весам RARITY_WEIGHTS,
    затем случайный ещё не полученный предмет этой
    редкости. Если таких нет — эволюция персонажа.
    Повторный вызов с тем же order_id ничего не выдаёт.
    """

    order_key = f"purchase:{str(order_id).strip()}"
    if order_key == "purchase:":
        raise ValueError("order_id is required")

    existing = db.scalar(
        select(RewardEvent).where(
            RewardEvent.user_id == user_id,
            RewardEvent.reward_key == order_key,
        )
    )
    if existing:
        return PurchaseRewardResult(created=False, event=existing)

    rng = rng or random.Random()
    character = get_or_create_character(db, user_id)
    rarity = roll_rarity(rng)

    owned = owned_item_ids(db, user_id)
    candidates = [
        item
        for item in db.scalars(
            select(Item).where(Item.rarity == rarity).order_by(Item.id)
        ).all()
        if item.id not in owned
    ]

    if candidates:
        event = _try_grant(
            db,
            user_id=user_id,
            reward_key=order_key,
            kind=RewardKind.item,
            item=rng.choice(candidates),
            item_source=ItemSource.purchase,
            source="purchase",
            rolled_rarity=rarity,
        )
    else:
        event = _try_grant(
            db,
            user_id=user_id,
            reward_key=order_key,
            kind=RewardKind.evolution,
            source="purchase",
            rolled_rarity=rarity,
            character=character,
        )

    db.commit()

    if event is None:
        # Параллельный вызов успел раньше.
        event = db.scalar(
            select(RewardEvent).where(
                RewardEvent.user_id == user_id,
                RewardEvent.reward_key == order_key,
            )
        )
        return PurchaseRewardResult(created=False, event=event)

    db.refresh(event)
    return PurchaseRewardResult(created=True, event=event)


# -------------------------
# ACTIONS
# -------------------------

class CharacterError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def unbox_character(db: Session, user: User) -> UserCharacter:
    character = evaluate_character(db, user)

    if character.unlocked_at is None:
        raise CharacterError(409, "Character is still locked")

    if character.unboxed_at is None:
        character.unboxed_at = utcnow()
        db.commit()
        db.refresh(character)
        track_event(user.telegram_user_id, "character_unboxed", {
            "archetype": character.archetype.value,
        })
        track_event(user.telegram_user_id, "quest_completed", {"quest": "unlock"})

    return character


def mark_shared(db: Session, user: User) -> UserCharacter:
    character = get_or_create_character(db, user.id)
    if character.shared_at is None:
        character.shared_at = utcnow()
    db.commit()
    db.refresh(character)
    return character


def equip_item(db: Session, user: User, item_code: str, equip: bool) -> None:
    row = db.scalar(
        select(UserItem)
        .join(Item, Item.id == UserItem.item_id)
        .where(UserItem.user_id == user.id, Item.code == item_code)
        .options(joinedload(UserItem.item))
    )

    if row is None:
        raise CharacterError(404, "Item is not in inventory")

    if equip:
        same_slot = db.scalars(
            select(UserItem)
            .join(Item, Item.id == UserItem.item_id)
            .where(
                UserItem.user_id == user.id,
                Item.slot == row.item.slot,
                UserItem.equipped.is_(True),
                UserItem.id != row.id,
            )
        ).all()
        for other in same_slot:
            other.equipped = False

    row.equipped = equip
    db.commit()


def ack_rewards(db: Session, user: User, reward_ids: list[int]) -> int:
    if not reward_ids:
        return 0

    rows = db.scalars(
        select(RewardEvent).where(
            RewardEvent.user_id == user.id,
            RewardEvent.id.in_(reward_ids),
            RewardEvent.seen_at.is_(None),
        )
    ).all()

    now = utcnow()
    for row in rows:
        row.seen_at = now
    db.commit()
    return len(rows)


# -------------------------
# SERIALIZATION
# -------------------------

def _item_payload(item: Item) -> dict:
    return {
        "code": item.code,
        "name": item.name,
        "slot": item.slot.value,
        "rarity": item.rarity.value,
        "asset_key": item.asset_key,
    }


def _current_quest(
    *,
    unlocked: bool,
    shelf_count: int,
    wishlist_after_unlock: int,
    first_item_done: bool,
) -> dict:
    if not unlocked:
        return {
            "code": "unlock",
            "progress": min(shelf_count, UNLOCK_SHELF_TARGET),
            "target": UNLOCK_SHELF_TARGET,
            "completed": False,
            "reward": "character",
        }

    if not first_item_done:
        return {
            "code": "first_item",
            "progress": min(wishlist_after_unlock, FIRST_ITEM_WISHLIST_TARGET),
            "target": FIRST_ITEM_WISHLIST_TARGET,
            "completed": False,
            "reward": "item",
        }

    # Постоянное «задание»: покупки через cosmi.
    return {
        "code": "purchase",
        "progress": 0,
        "target": 1,
        "completed": False,
        "reward": "item_or_evolution",
    }


def serialize_character(db: Session, user: User, character: UserCharacter) -> dict:
    groups = shelf_shade_groups(db, user.id)
    result = compute_archetype(groups)
    shelf_count = len(groups)
    unlocked = character.unlocked_at is not None

    wishlist_after = (
        wishlist_count_since(db, user.id, character.unlocked_at) if unlocked else 0
    )

    user_items = {
        row.item_id: row
        for row in db.scalars(
            select(UserItem).where(UserItem.user_id == user.id)
        ).all()
    }

    items = db.scalars(select(Item).order_by(Item.id)).all()

    inventory = []
    equipped: dict[str, str | None] = {slot.value: None for slot in SLOT_ORDER}

    for item in sorted(items, key=lambda it: (SLOT_ORDER.index(it.slot), it.id)):
        owned_row = user_items.get(item.id)
        if owned_row and owned_row.equipped:
            equipped[item.slot.value] = item.code

        inventory.append(
            {
                **_item_payload(item),
                "owned": owned_row is not None,
                "equipped": bool(owned_row and owned_row.equipped),
                "obtained_at": owned_row.obtained_at.isoformat() if owned_row else None,
            }
        )

    first_item_done = (
        db.scalar(
            select(RewardEvent.id).where(
                RewardEvent.user_id == user.id,
                RewardEvent.reward_key == "quest:first_item",
            )
        )
        is not None
    )

    pending = db.scalars(
        select(RewardEvent)
        .where(
            RewardEvent.user_id == user.id,
            RewardEvent.seen_at.is_(None),
            RewardEvent.kind.in_([RewardKind.item, RewardKind.evolution]),
        )
        .options(joinedload(RewardEvent.item))
        .order_by(RewardEvent.id)
    ).all()

    if not unlocked:
        status = "locked"
    elif character.unboxed_at is None:
        status = "ready_to_unbox"
    else:
        status = "active"

    return {
        "status": status,
        "archetype": result.archetype.value,
        "accent": result.accent.value if result.accent else None,
        "evolution": character.evolution or 0,
        "shape_seed": character.shape_seed,
        "progress": {
            "shelf_count": shelf_count,
            "shelf_target": UNLOCK_SHELF_TARGET,
            "classified_count": result.classified,
        },
        "distribution": result.counts,
        "unlocked_at": character.unlocked_at.isoformat() if character.unlocked_at else None,
        "unboxed_at": character.unboxed_at.isoformat() if character.unboxed_at else None,
        "shared_at": character.shared_at.isoformat() if character.shared_at else None,
        "quest": _current_quest(
            unlocked=unlocked,
            shelf_count=shelf_count,
            wishlist_after_unlock=wishlist_after,
            first_item_done=first_item_done,
        ),
        "inventory": inventory,
        "equipped": equipped,
        "pending_rewards": [
            {
                "id": event.id,
                "kind": event.kind.value,
                "source": event.source,
                "item": _item_payload(event.item) if event.item else None,
                "rolled_rarity": event.rolled_rarity,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }
            for event in pending
        ],
        "rarity_odds": {r.value: w for r, w in RARITY_WEIGHTS.items()},
    }
