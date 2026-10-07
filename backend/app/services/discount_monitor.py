import html
import os
from datetime import datetime, timezone

from aiogram import Bot
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Offer,
    Product,
    Store,
    StoreCatalogItem,
    TrackedItem,
    User,
)
from app.services.product_matcher import (
    link_product_to_best_match,
)


API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "https://you-beauty-dev-production.up.railway.app/api",
).rstrip("/")


TEMPLATE_COUNT = 3


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
                    f"You Beauty поймал "
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


async def check_discount_notifications(
    bot: Bot,
    db: Session,
) -> dict:
    checked = 0
    initialized = 0
    sent = 0
    skipped = 0
    failed = 0

    rows = db.execute(
        select(
            TrackedItem,
            User,
        )
        .join(
            User,
            User.id
            == TrackedItem.user_id,
        )
        .options(
            joinedload(
                TrackedItem.product
            ).joinedload(
                Product.brand
            )
        )
        .order_by(
            TrackedItem.id.asc()
        )
    ).all()

    for tracked_item, user in rows:
        checked += 1

        try:
            product = (
                tracked_item.product
            )

            if not product:
                skipped += 1
                continue

            #
            # Обновляем Offer свежими
            # данными из каталога ЗЯ.
            #
            match_result = (
                link_product_to_best_match(
                    db,
                    product,
                    "golden-apple",
                )
            )

            if (
                not match_result.matched
                or match_result.offer_id
                is None
            ):
                skipped += 1
                continue

            (
                offer,
                _store,
            ) = _get_offer(
                db,
                product.id,
            )

            if (
                not offer
                or not offer.in_stock
            ):
                skipped += 1
                continue

            current_price = _to_float(
                offer.current_price
            )

            old_price = _to_float(
                offer.old_price
            )

            if current_price is None:
                skipped += 1
                continue

            discount_percent = (
                _discount_percent(
                    current_price,
                    old_price,
                )
            )

            has_discount = (
                discount_percent
                is not None
            )

            now = datetime.now(
                timezone.utc
            )

            #
            # Первый проход:
            # только запоминаем текущую цену.
            # Старые скидки не рассылаем.
            #
            if (
                tracked_item
                .last_price_checked_at
                is None
            ):
                tracked_item.last_seen_price = (
                    current_price
                )

                tracked_item.last_seen_old_price = (
                    old_price
                )

                tracked_item.last_seen_has_discount = (
                    has_discount
                )

                tracked_item.last_price_checked_at = (
                    now
                )

                db.commit()

                initialized += 1
                continue

            previous_price = _to_float(
                tracked_item
                .last_seen_price
            )

            previous_discount = (
                tracked_item
                .last_seen_has_discount
                is True
            )

            #
            # Скидка появилась.
            #
            discount_just_started = (
                has_discount
                and not previous_discount
            )

            #
            # Скидка уже была,
            # но цена стала ещё ниже.
            #
            price_dropped_further = (
                has_discount
                and previous_price
                is not None
                and current_price
                < previous_price
            )

            should_notify = (
                tracked_item
                .notifications_enabled
                and (
                    discount_just_started
                    or price_dropped_further
                )
            )

            if should_notify:
                template_index = (
                    _choose_template_index(
                        tracked_item,
                        now,
                    )
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

                (
                    message,
                    button_text,
                ) = _build_message(
                    product=product,
                    tracked_item=tracked_item,
                    current_price=(
                        current_price
                    ),
                    old_price=old_price,
                    discount_percent=(
                        discount_percent
                    ),
                    template_index=(
                        template_index
                    ),
                )

                keyboard = (
                    InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=button_text,
                                    url=click_url,
                                )
                            ]
                        ]
                    )
                )

                try:
                    await bot.send_message(
                        chat_id=(
                            user.telegram_user_id
                        ),
                        text=message,
                        parse_mode="HTML",
                        reply_markup=keyboard,
                        disable_web_page_preview=True,
                    )

                except Exception as exc:
                    failed += 1

                    print(
                        "DISCOUNT_NOTIFICATION | "
                        f"FAILED "
                        f"tracked_item_id="
                        f"{tracked_item.id} "
                        f"telegram_user_id="
                        f"{user.telegram_user_id} "
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    )

                    db.rollback()
                    continue

                tracked_item.last_notified_price = (
                    current_price
                )

                tracked_item.last_notified_discount_percent = (
                    discount_percent
                )

                tracked_item.last_notified_at = (
                    now
                )

                sent += 1

                print(
                    "DISCOUNT_NOTIFICATION | "
                    f"SENT "
                    f"tracked_item_id="
                    f"{tracked_item.id} "
                    f"telegram_user_id="
                    f"{user.telegram_user_id} "
                    f"price={current_price} "
                    f"discount="
                    f"{discount_percent} "
                    f"template="
                    f"{template_index + 1}"
                )

            #
            # Запоминаем состояние,
            # чтобы на следующей проверке
            # понимать, изменилась ли цена.
            #
            tracked_item.last_seen_price = (
                current_price
            )

            tracked_item.last_seen_old_price = (
                old_price
            )

            tracked_item.last_seen_has_discount = (
                has_discount
            )

            tracked_item.last_price_checked_at = (
                now
            )

            db.commit()

        except Exception as exc:
            failed += 1
            db.rollback()

            print(
                "DISCOUNT_MONITOR | "
                f"FAILED "
                f"tracked_item_id="
                f"{tracked_item.id} "
                f"{type(exc).__name__}: "
                f"{exc}"
            )

    result = {
        "checked": checked,
        "initialized": initialized,
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
    }

    print(
        "DISCOUNT_MONITOR | "
        f"DONE {result}"
    )

    return result
