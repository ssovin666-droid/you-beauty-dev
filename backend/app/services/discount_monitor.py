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


def _to_float(value):
    if value is None:
        return None

    return float(value)


def _format_price(
    value: float | None,
    currency: str | None,
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

    if currency == "RUB":
        return f"{formatted} ₽"

    if currency:
        return f"{formatted} {currency}"

    return formatted


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
    str | None,
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
            None,
        )

    offer, store = row

    currency = db.scalar(
        select(
            StoreCatalogItem.currency
        )
        .where(
            StoreCatalogItem.product_id
            == product_id,
            StoreCatalogItem.store_id
            == store.id,
        )
        .order_by(
            StoreCatalogItem.synced_at.desc()
        )
        .limit(1)
    )

    return (
        offer,
        store,
        currency,
    )


def _build_message(
    product: Product,
    current_price: float,
    old_price: float | None,
    discount_percent: int | None,
) -> str:
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

    title = " — ".join(
        title_parts
    )

    safe_title = html.escape(
        title
    )

    current_text = _format_price(
        current_price,
        "RUB",
    )

    old_text = (
        _format_price(
            old_price,
            "RUB",
        )
        if old_price is not None
        else None
    )

    lines = [
        "✨ <b>Цена снизилась</b>",
        "",
        f"<b>{safe_title}</b>",
    ]

    if (
        product.variant
        or product.size
    ):
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

        lines.append(
            html.escape(details)
        )

    lines.append("")

    if (
        old_text
        and discount_percent
        is not None
    ):
        lines.append(
            f"<s>{old_text}</s> → "
            f"<b>{current_text}</b>"
        )

        lines.append(
            f"Скидка −{discount_percent}%"
        )

    else:
        lines.append(
            f"Новая цена: "
            f"<b>{current_text}</b>"
        )

    lines.extend(
        [
            "",
            "You Beauty следит за ценой "
            "и сообщает, когда становится выгоднее 💗",
        ]
    )

    return "\n".join(lines)


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

            # Берём свежую цену из каталога
            # Golden Apple и обновляем Offer.
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
                currency,
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

            # Первый проход:
            # только запоминаем состояние.
            # Старые скидки массово
            # пользователям не рассылаем.
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

            discount_just_started = (
                has_discount
                and not previous_discount
            )

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

                keyboard = (
                    InlineKeyboardMarkup(
                        inline_keyboard=[
                            [
                                InlineKeyboardButton(
                                    text=(
                                        "Посмотреть "
                                        "в Золотом Яблоке →"
                                    ),
                                    url=click_url,
                                )
                            ]
                        ]
                    )
                )

                message = _build_message(
                    product=product,
                    current_price=(
                        current_price
                    ),
                    old_price=old_price,
                    discount_percent=(
                        discount_percent
                    ),
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

                    # Не обновляем состояние:
                    # при следующем запуске
                    # попробуем отправить ещё раз.
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
                    f"{discount_percent}"
                )

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
