"""Мониторинг скидок по сохранённым товарам.

Три независимых шага (раньше всё делалось одним
полным проходом по всем подпискам каждые 5 минут):

1. initialize_new_subscriptions — первоначальная
   фиксация цены для новых подписок. Только подписки
   без baseline; старые скидки не рассылаются.
2. apply_catalog_version — только после публикации
   новой версии каталога и только по товарам,
   чьи строки каталога изменились в этой версии.
   Каждый product_id обрабатывается один раз,
   результат применяется ко всем его подписчикам.
   Уведомления кладутся в outbox в той же транзакции,
   что и обновление last_seen_*.
3. deliver_notifications — отправка outbox в Telegram.

Все шаги работают ограниченными пакетами.
"""

import asyncio
import html
import os
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
    TelegramRetryAfter,
)
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, joinedload

from app.core.metrics import inc as metric_inc
from app.models import (
    DiscountNotification,
    Offer,
    Product,
    ProductMatchMiss,
    Store,
    StoreCatalogItem,
    TrackedItem,
    User,
)
from app.services.catalog_versions import (
    get_job_state,
    get_published_version,
    set_job_state,
)
from app.services.product_matcher import (
    create_or_update_offer,
    get_store,
    link_product_to_best_match,
)


API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "https://you-beauty-dev-production.up.railway.app/api",
).rstrip("/")


TEMPLATE_COUNT = 3

STORE_SLUG = "golden-apple"

WATERMARK_KEY = "discount_monitor.catalog_version"

# Размер пакета товаров на одну транзакцию.
PRODUCT_BATCH_SIZE = int(
    os.getenv("DISCOUNT_PRODUCT_BATCH_SIZE", "200")
)

# Верхняя граница новых товаров за один 5-минутный
# проход (остаток — в следующем проходе).
MAX_NEW_PRODUCTS_PER_RUN = int(
    os.getenv("DISCOUNT_MAX_NEW_PRODUCTS_PER_RUN", "1000")
)

DELIVERY_BATCH_SIZE = int(
    os.getenv("DISCOUNT_DELIVERY_BATCH_SIZE", "100")
)

MAX_DELIVERY_ATTEMPTS = 5

# Если процесс упал между отправкой в Telegram и
# сохранением результата, через это время строка
# «sending» переводится в «uncertain» и повторно
# НЕ отправляется: дубль скидки хуже пропуска.
SENDING_STALE_AFTER = timedelta(minutes=10)

# Пауза между сообщениями (лимит Telegram ~30/с).
SEND_INTERVAL_SECONDS = 0.05


def _to_float(value):
    if value is None:
        return None

    return float(value)


def _format_price(
    value: float | None,
) -> str:
    if value is None:
        return "—"

    if value.is_integer():
        formatted = f"{int(value):,}".replace(
            ",",
            " ",
        )
    else:
        formatted = (
            f"{value:,.2f}"
            .replace(",", " ")
        )

    return f"{formatted} ₽"


def _discount_percent(
    current_price: float | None,
    old_price: float | None,
) -> int | None:
    if (
        current_price is None
        or old_price is None
        or old_price <= 0
        or current_price >= old_price
    ):
        return None

    return round(
        (
            (
                old_price
                - current_price
            )
            / old_price
        )
        * 100
    )


def _get_offer(
    db: Session,
    product_id: int,
) -> tuple[
    Offer | None,
    Store | None,
]:
    row = db.execute(
        select(
            Offer,
            Store,
        )
        .join(
            Store,
            Store.id
            == Offer.store_id,
        )
        .where(
            Offer.product_id
            == product_id,
            Store.slug
            == "golden-apple",
        )
        .order_by(
            Offer.updated_at.desc()
        )
    ).first()

    if not row:
        return (
            None,
            None,
        )

    offer, store = row

    return (
        offer,
        store,
    )


def _get_list_text(
    tracked_item: TrackedItem,
) -> str:
    list_type = getattr(
        tracked_item.list_type,
        "value",
        tracked_item.list_type,
    )

    if list_type == "wishlist":
        return "Wishlist"

    return "Полку"


def _choose_template_index(
    tracked_item: TrackedItem,
    now: datetime,
) -> int:
    """
    Выбирает один из трёх шаблонов.

    Для одного и того же товара
    один шаблон два раза подряд
    не используется.
    """

    current_key = int(
        now.timestamp() // 60
    )

    template_index = (
        tracked_item.id
        + current_key
    ) % TEMPLATE_COUNT

    if (
        tracked_item.last_notified_at
        is not None
    ):
        previous_key = int(
            tracked_item
            .last_notified_at
            .timestamp()
            // 60
        )

        previous_template_index = (
            tracked_item.id
            + previous_key
        ) % TEMPLATE_COUNT

        if (
            template_index
            == previous_template_index
        ):
            template_index = (
                template_index + 1
            ) % TEMPLATE_COUNT

    return template_index


def _build_message(
    product: Product,
    tracked_item: TrackedItem,
    current_price: float,
    old_price: float | None,
    discount_percent: int | None,
    template_index: int,
) -> tuple[str, str]:
    brand = (
        product.brand.name
        if product.brand
        else None
    )

    title_parts = [
        value
        for value in [
            brand,
            product.name,
        ]
        if value
    ]

    title = html.escape(
        " — ".join(
            title_parts
        )
    )

    details = " · ".join(
        [
            value
            for value in [
                product.variant,
                product.size,
            ]
            if value
        ]
    )

    safe_details = (
        html.escape(details)
        if details
        else None
    )

    current_text = _format_price(
        current_price
    )

    old_text = (
        _format_price(
            old_price
        )
        if old_price is not None
        else None
    )

    list_text = _get_list_text(
        tracked_item
    )

    saving = None

    if old_price is not None:
        saving_value = (
            old_price
            - current_price
        )

        if saving_value > 0:
            saving = _format_price(
                saving_value
            )

    #
    # ШАБЛОН 1
    #
    if template_index == 0:
        lines = [
            "💗 <b>Кажется, пора брать</b>",
            "",
            f"<b>{title}</b>",
        ]

        if safe_details:
            lines.append(
                safe_details
            )

        lines.append("")

        if old_text:
            lines.extend(
                [
                    f"Было <s>{old_text}</s>",
                    (
                        f"Сейчас "
                        f"<b>{current_text}</b>"
                    ),
                ]
            )

        else:
            lines.append(
                f"Сейчас "
                f"<b>{current_text}</b>"
            )

        if discount_percent is not None:
            lines.extend(
                [
                    "",
                    (
                        f"<b>−"
                        f"{discount_percent}%</b>"
                    ),
                ]
            )

        lines.extend(
            [
                "",
                (
                    f"Ты добавляла этот товар "
                    f"в {list_text} — "
                    f"мы заметили, что цена "
                    f"снизилась."
                ),
            ]
        )

        return (
            "\n".join(lines),
            "Забрать со скидкой →",
        )

    #
    # ШАБЛОН 2
    #
    if template_index == 1:
        lines = [
            "✨ <b>Цена стала приятнее</b>",
            "",
            f"<b>{title}</b>",
        ]

        if safe_details:
            lines.append(
                safe_details
            )

        lines.append("")

        if (
            old_text
            and discount_percent
            is not None
        ):
            lines.append(
                (
                    f"<s>{old_text}</s> → "
                    f"<b>{current_text}</b>"
                )
            )

            lines.append(
                (
                    f"Скидка "
                    f"<b>−{discount_percent}%</b>"
                )
            )

        else:
            lines.append(
                (
                    f"Новая цена — "
                    f"<b>{current_text}</b>"
                )
            )

        if saving:
            lines.append(
                (
                    f"Экономия — "
                    f"<b>{saving}</b>"
                )
            )

        lines.extend(
            [
                "",
                (
                    f"Этот товар у тебя "
                    f"в {list_text}. "
                    f"cosmi поймал "
                    f"снижение цены 💕"
                ),
            ]
        )

        return (
            "\n".join(lines),
            "Посмотреть скидку →",
        )

    #
    # ШАБЛОН 3
    #
    lines = [
        "👀 <b>Поймали скидку</b>",
        "",
        f"<b>{title}</b>",
    ]

    if safe_details:
        lines.append(
            safe_details
        )

    lines.append("")

    if old_text:
        lines.append(
            (
                f"Цена опустилась с "
                f"<s>{old_text}</s> "
                f"до <b>{current_text}</b>"
            )
        )

    else:
        lines.append(
            (
                f"Сейчас цена — "
                f"<b>{current_text}</b>"
            )
        )

    if discount_percent is not None:
        lines.append(
            (
                f"Сейчас скидка "
                f"<b>−{discount_percent}%</b>"
            )
        )

    lines.extend(
        [
            "",
            (
                "Если ждала хороший момент — "
                "он может быть сейчас ✨"
            ),
        ]
    )

    return (
        "\n".join(lines),
        "Смотреть в ЗЯ →",
    )



# -------------------------
# ОБЩЕЕ
# -------------------------


def _price_state(
    offer: Offer | None,
) -> tuple[float, float | None, int | None, bool] | None:
    """(current, old, discount_percent, has_discount) или None."""

    if not offer or not offer.in_stock:
        return None

    current_price = _to_float(offer.current_price)
    old_price = _to_float(offer.old_price)

    if current_price is None:
        return None

    discount_percent = _discount_percent(
        current_price,
        old_price,
    )

    return (
        current_price,
        old_price,
        discount_percent,
        discount_percent is not None,
    )


def _available_linked_item(
    db: Session,
    product_id: int,
    store_id: int,
) -> StoreCatalogItem | None:
    return db.scalar(
        select(StoreCatalogItem)
        .where(
            StoreCatalogItem.store_id == store_id,
            StoreCatalogItem.product_id == product_id,
            StoreCatalogItem.available.is_(True),
        )
        .order_by(StoreCatalogItem.synced_at.desc())
        .limit(1)
    )


def _load_product(
    db: Session,
    product_id: int,
) -> Product | None:
    return db.scalar(
        select(Product)
        .where(Product.id == product_id)
        .options(joinedload(Product.brand))
    )


def _refresh_offer(
    db: Session,
    product: Product,
    store: Store,
) -> Offer | None:
    """Актуализирует Offer из уже связанной строки.

    Тяжёлый поиск запускается, только если
    доступной связанной строки нет (с учётом
    отрицательного кэша).
    """

    item = _available_linked_item(
        db,
        product.id,
        store.id,
    )

    if item is not None:
        return create_or_update_offer(
            db,
            product,
            item,
        )

    result = link_product_to_best_match(
        db,
        product,
        store.slug,
    )

    if result.matched and result.offer_id is not None:
        return db.get(Offer, result.offer_id)

    # Связанный товар пропал из каталога:
    # помечаем предложение как отсутствующее.
    offer = db.scalar(
        select(Offer).where(
            Offer.product_id == product.id,
            Offer.store_id == store.id,
        )
    )

    if offer is not None and offer.in_stock:
        offer.in_stock = False
        offer.updated_at = datetime.utcnow()

    return None


def _set_baseline(
    tracked_item: TrackedItem,
    state,
    now: datetime,
) -> None:
    current_price, old_price, _percent, has_discount = state
    tracked_item.last_seen_price = current_price
    tracked_item.last_seen_old_price = old_price
    tracked_item.last_seen_has_discount = has_discount
    tracked_item.last_price_checked_at = now


# -------------------------
# 1. НОВЫЕ ПОДПИСКИ
# -------------------------


def initialize_new_subscriptions(
    db: Session,
    batch_size: int = PRODUCT_BATCH_SIZE,
    max_products: int = MAX_NEW_PRODUCTS_PER_RUN,
) -> dict:
    """Фиксирует стартовую цену подписок без baseline.

    Берутся только подписки, у которых
    last_price_checked_at IS NULL, и только товары:
    - связанные с доступной строкой каталога с ценой
      (дешёвая фиксация), или
    - ещё не связанные и без действующего
      отрицательного результата поиска.
    Товары, для которых поиск уже ничего не нашёл,
    ждут изменения каталога их бренда.
    Уведомления на этом шаге не отправляются.
    """

    stats = {
        "new_products": 0,
        "initialized": 0,
        "unmatched": 0,
    }

    store = get_store(db, STORE_SLUG)

    if store is None:
        return stats

    available_link = (
        select(StoreCatalogItem.id)
        .where(
            StoreCatalogItem.store_id == store.id,
            StoreCatalogItem.product_id == TrackedItem.product_id,
            StoreCatalogItem.available.is_(True),
            StoreCatalogItem.current_price.is_not(None),
        )
        .exists()
    )

    any_link = (
        select(StoreCatalogItem.id)
        .where(
            StoreCatalogItem.store_id == store.id,
            StoreCatalogItem.product_id == TrackedItem.product_id,
        )
        .exists()
    )

    valid_miss = (
        select(ProductMatchMiss.product_id)
        .where(
            ProductMatchMiss.product_id == TrackedItem.product_id,
            ProductMatchMiss.store_id == store.id,
            ProductMatchMiss.stale.is_(False),
        )
        .exists()
    )

    last_product_id = 0

    while stats["new_products"] < max_products:
        limit = min(
            batch_size,
            max_products - stats["new_products"],
        )

        product_ids = list(
            db.scalars(
                select(TrackedItem.product_id)
                .where(
                    TrackedItem.last_price_checked_at.is_(None),
                    TrackedItem.product_id > last_product_id,
                    available_link
                    | (~any_link & ~valid_miss),
                )
                .group_by(TrackedItem.product_id)
                .order_by(TrackedItem.product_id)
                .limit(limit)
            ).all()
        )

        if not product_ids:
            break

        last_product_id = product_ids[-1]

        for product_id in product_ids:
            stats["new_products"] += 1
            metric_inc("unique_products")

            product = _load_product(db, product_id)

            if product is None:
                continue

            offer = _refresh_offer(db, product, store)
            state = _price_state(offer)

            if state is None:
                stats["unmatched"] += 1
                continue

            now = datetime.now(timezone.utc)

            subscribers = db.scalars(
                select(TrackedItem)
                .where(
                    TrackedItem.product_id == product_id,
                    TrackedItem.last_price_checked_at.is_(None),
                )
                .with_for_update(skip_locked=True)
            ).all()

            for tracked_item in subscribers:
                _set_baseline(tracked_item, state, now)
                stats["initialized"] += 1

        db.commit()

    for key, value in stats.items():
        metric_inc(f"init_{key}", value)

    return stats


# -------------------------
# 2. НОВАЯ ВЕРСИЯ КАТАЛОГА
# -------------------------


def _enqueue_notification(
    db: Session,
    tracked_item: TrackedItem,
    user: User,
    product: Product,
    offer: Offer,
    state,
    version: int,
    now: datetime,
) -> bool:
    current_price, old_price, discount_percent, _ = state

    template_index = _choose_template_index(
        tracked_item,
        now,
    )

    notification_id = (
        f"discount-"
        f"{tracked_item.id}-"
        f"{int(now.timestamp())}"
    )

    click_url = (
        f"{API_BASE_URL}"
        f"/out/{offer.id}"
        f"?source=discount"
        f"&user_id={user.id}"
        f"&notification_id="
        f"{notification_id}"
    )

    message, button_text = _build_message(
        product=product,
        tracked_item=tracked_item,
        current_price=current_price,
        old_price=old_price,
        discount_percent=discount_percent,
        template_index=template_index,
    )

    values = {
        "dedupe_key": (
            f"{tracked_item.id}:{version}:{current_price:.2f}"
        ),
        "tracked_item_id": tracked_item.id,
        "user_id": user.id,
        "offer_id": offer.id,
        "catalog_version": version,
        "price": current_price,
        "discount_percent": discount_percent,
        "template_index": template_index,
        "text": message,
        "button_text": button_text,
        "button_url": click_url,
        "status": "pending",
        "attempts": 0,
        "next_attempt_at": now,
        "created_at": now,
    }

    if db.bind.dialect.name == "postgresql":
        inserted = db.execute(
            pg_insert(DiscountNotification)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=["dedupe_key"]
            )
        ).rowcount
        return bool(inserted)

    duplicate = db.scalar(
        select(DiscountNotification.id).where(
            DiscountNotification.dedupe_key
            == values["dedupe_key"]
        )
    )

    if duplicate:
        return False

    db.add(DiscountNotification(**values))
    db.flush()
    return True


def _apply_state_to_subscribers(
    db: Session,
    product: Product,
    offer: Offer,
    state,
    version: int,
    stats: dict,
) -> None:
    current_price, _old, _percent, has_discount = state
    now = datetime.now(timezone.utc)

    rows = db.execute(
        select(TrackedItem, User)
        .join(User, User.id == TrackedItem.user_id)
        .where(TrackedItem.product_id == product.id)
        .order_by(TrackedItem.id)
        .with_for_update(of=TrackedItem)
    ).all()

    for tracked_item, user in rows:
        stats["subscriptions"] += 1

        # Подписка ещё без baseline: только фиксируем
        # цену, старую скидку не рассылаем.
        if tracked_item.last_price_checked_at is None:
            _set_baseline(tracked_item, state, now)
            stats["initialized"] += 1
            continue

        previous_price = _to_float(tracked_item.last_seen_price)
        previous_discount = (
            tracked_item.last_seen_has_discount is True
        )

        discount_just_started = (
            has_discount
            and not previous_discount
        )

        price_dropped_further = (
            has_discount
            and previous_price is not None
            and current_price < previous_price
        )

        if (
            tracked_item.notifications_enabled
            and (
                discount_just_started
                or price_dropped_further
            )
        ):
            if _enqueue_notification(
                db,
                tracked_item,
                user,
                product,
                offer,
                state,
                version,
                now,
            ):
                stats["enqueued"] += 1

        _set_baseline(tracked_item, state, now)


def apply_catalog_version(
    db: Session,
    batch_size: int = PRODUCT_BATCH_SIZE,
) -> dict:
    """Обновляет цены подписок после публикации версии.

    Ничего не делает, если новая версия не
    опубликована. Сбой посередине безопасен:
    водяной знак сдвигается только в конце, а
    повторная обработка уже применённого товара
    сравнивает цену с уже обновлённым last_seen_*
    и второе уведомление не создаёт (плюс
    уникальный dedupe_key в outbox).
    """

    stats = {
        "version": None,
        "products": 0,
        "subscriptions": 0,
        "initialized": 0,
        "enqueued": 0,
        "out_of_stock": 0,
    }

    store = get_store(db, STORE_SLUG)

    if store is None:
        return stats

    target = get_published_version(db, store.id)
    watermark = get_job_state(db, WATERMARK_KEY) or 0

    if target is None or target <= watermark:
        stats["version"] = watermark or None
        return stats

    stats["version"] = target

    tracked_exists = (
        select(TrackedItem.id)
        .where(TrackedItem.product_id == StoreCatalogItem.product_id)
        .exists()
    )

    last_product_id = 0

    while True:
        product_ids = list(
            db.scalars(
                select(StoreCatalogItem.product_id)
                .where(
                    StoreCatalogItem.store_id == store.id,
                    StoreCatalogItem.product_id.is_not(None),
                    StoreCatalogItem.changed_version > watermark,
                    StoreCatalogItem.changed_version <= target,
                    StoreCatalogItem.product_id > last_product_id,
                    tracked_exists,
                )
                .group_by(StoreCatalogItem.product_id)
                .order_by(StoreCatalogItem.product_id)
                .limit(batch_size)
            ).all()
        )

        if not product_ids:
            break

        last_product_id = product_ids[-1]

        for product_id in product_ids:
            stats["products"] += 1
            metric_inc("unique_products")

            product = _load_product(db, product_id)

            if product is None:
                continue

            offer = _refresh_offer(db, product, store)
            state = _price_state(offer)

            if state is None:
                stats["out_of_stock"] += 1
                continue

            _apply_state_to_subscribers(
                db,
                product,
                offer,
                state,
                target,
                stats,
            )

        db.commit()

    set_job_state(db, WATERMARK_KEY, target)
    db.commit()

    for key in ("products", "subscriptions", "initialized", "enqueued", "out_of_stock"):
        metric_inc(f"version_{key}", stats[key])

    return stats


# -------------------------
# 3. ДОСТАВКА
# -------------------------


def recover_stale_sending(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - SENDING_STALE_AFTER

    count = db.execute(
        update(DiscountNotification)
        .where(
            DiscountNotification.status == "sending",
            DiscountNotification.claimed_at < cutoff,
        )
        .values(
            status="uncertain",
            last_error="crashed between send and save",
        )
        .execution_options(synchronize_session=False)
    ).rowcount

    db.commit()
    return count or 0


def claim_notifications(
    db: Session,
    limit: int = DELIVERY_BATCH_SIZE,
) -> list[dict]:
    """Забирает пакет outbox. SKIP LOCKED: два worker'а
    не получат одну и ту же строку."""

    now = datetime.now(timezone.utc)

    query = (
        select(DiscountNotification, User.telegram_user_id)
        .join(User, User.id == DiscountNotification.user_id)
        .where(
            DiscountNotification.status == "pending",
            DiscountNotification.next_attempt_at <= now,
        )
        .order_by(DiscountNotification.id)
        .limit(limit)
    )

    if db.bind.dialect.name == "postgresql":
        query = query.with_for_update(
            of=DiscountNotification,
            skip_locked=True,
        )

    rows = db.execute(query).all()

    claimed = []

    for notification, telegram_user_id in rows:
        notification.status = "sending"
        notification.claimed_at = now
        notification.attempts = (notification.attempts or 0) + 1
        claimed.append(
            {
                "id": notification.id,
                "chat_id": telegram_user_id,
                "text": notification.text,
                "button_text": notification.button_text,
                "button_url": notification.button_url,
                "attempts": notification.attempts,
            }
        )

    db.commit()
    return claimed


def mark_sent(
    db: Session,
    notification_id: int,
    message_id: int | None,
) -> None:
    notification = db.get(DiscountNotification, notification_id)

    if notification is None:
        db.commit()
        return

    now = datetime.now(timezone.utc)
    notification.status = "sent"
    notification.sent_at = now
    notification.telegram_message_id = message_id
    notification.last_error = None

    tracked_item = db.get(TrackedItem, notification.tracked_item_id)

    if tracked_item is not None:
        tracked_item.last_notified_price = notification.price
        tracked_item.last_notified_discount_percent = (
            notification.discount_percent
        )
        tracked_item.last_notified_at = now

    db.commit()


def mark_failed(
    db: Session,
    notification_id: int,
    error: str,
    retry_in: float | None,
    attempts: int,
) -> str:
    notification = db.get(DiscountNotification, notification_id)

    if notification is None:
        db.commit()
        return "missing"

    notification.last_error = error[:255]

    if retry_in is not None and attempts < MAX_DELIVERY_ATTEMPTS:
        notification.status = "pending"
        notification.next_attempt_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=retry_in)
        )
    else:
        notification.status = "failed"

    db.commit()
    return notification.status


def release_claimed(
    db: Session,
    notification_ids: list[int],
) -> None:
    """Возвращает в очередь строки, которые
    забрали, но ещё не пытались отправить."""

    if not notification_ids:
        return

    db.execute(
        update(DiscountNotification)
        .where(
            DiscountNotification.id.in_(notification_ids),
            DiscountNotification.status == "sending",
        )
        .values(
            status="pending",
            attempts=DiscountNotification.attempts - 1,
        )
        .execution_options(synchronize_session=False)
    )
    db.commit()


async def deliver_notifications(
    bot: Bot,
    session_factory,
    limit: int = DELIVERY_BATCH_SIZE,
) -> dict:
    stats = {
        "sent": 0,
        "failed": 0,
        "retry": 0,
        "uncertain_recovered": 0,
    }

    def _recover():
        db = session_factory()
        try:
            return recover_stale_sending(db)
        finally:
            db.close()

    def _claim():
        db = session_factory()
        try:
            return claim_notifications(db, limit)
        finally:
            db.close()

    def _call(fn, *args):
        db = session_factory()
        try:
            return fn(db, *args)
        finally:
            db.close()

    stats["uncertain_recovered"] = await asyncio.to_thread(_recover)

    claimed = await asyncio.to_thread(_claim)
    not_attempted = [item["id"] for item in claimed]

    try:
        await _send_claimed(bot, claimed, not_attempted, stats, _call)
    finally:
        if not_attempted:
            await asyncio.shield(
                asyncio.to_thread(
                    _call,
                    release_claimed,
                    list(not_attempted),
                )
            )

    for key, value in stats.items():
        metric_inc(f"delivery_{key}", value)

    return stats


async def _send_claimed(bot, claimed, not_attempted, stats, _call):
    for item in claimed:
        # С этого момента исход отправки
        # может быть неизвестен.
        not_attempted.remove(item["id"])

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=item["button_text"],
                        url=item["button_url"],
                    )
                ]
            ]
        )

        try:
            message = await bot.send_message(
                chat_id=item["chat_id"],
                text=item["text"],
                parse_mode="HTML",
                reply_markup=keyboard,
                disable_web_page_preview=True,
            )

        except TelegramRetryAfter as exc:
            stats["retry"] += 1
            await asyncio.to_thread(
                _call,
                mark_failed,
                item["id"],
                "retry_after",
                float(exc.retry_after),
                item["attempts"],
            )
            # Telegram просит подождать — не шлём
            # остальным в этом проходе.
            break

        except (
            TelegramForbiddenError,
            TelegramBadRequest,
            TelegramNotFound,
        ) as exc:
            stats["failed"] += 1
            await asyncio.to_thread(
                _call,
                mark_failed,
                item["id"],
                type(exc).__name__,
                None,
                item["attempts"],
            )
            print(
                "DISCOUNT_NOTIFICATION | FAILED "
                f"notification_id={item['id']} "
                f"{type(exc).__name__}"
            )
            continue

        except Exception as exc:
            status = await asyncio.to_thread(
                _call,
                mark_failed,
                item["id"],
                type(exc).__name__,
                60.0 * item["attempts"],
                item["attempts"],
            )
            stats["retry" if status == "pending" else "failed"] += 1
            continue

        await asyncio.to_thread(
            _call,
            mark_sent,
            item["id"],
            getattr(message, "message_id", None),
        )

        stats["sent"] += 1

        print(
            "DISCOUNT_NOTIFICATION | SENT "
            f"notification_id={item['id']}"
        )

        await asyncio.sleep(SEND_INTERVAL_SECONDS)
