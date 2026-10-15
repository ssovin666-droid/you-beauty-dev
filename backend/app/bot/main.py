import asyncio
import os
import time
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, Router
from aiogram.filters.command import CommandObject, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy import select

from app.core.amplitude import (
    flush_amplitude,
    set_user_property_once,
    track_event,
)
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.catalog import User
from app.services.discount_monitor import (
    check_discount_notifications,
)
from app.services.golden_apple_feed import (
    sync_golden_apple_feed,
)


settings = get_settings()
router = Router()


# Как часто проверять новые сохранённые товары.
# Здесь полный каталог не скачивается.
DISCOUNT_STATE_CHECK_SECONDS = max(
    60,
    int(
        os.getenv(
            "DISCOUNT_STATE_CHECK_SECONDS",
            "300",
        )
    ),
)


# Как часто полностью обновлять
# каталог Golden Apple.
# По умолчанию — раз в 3 часа.
GOLDEN_APPLE_SYNC_SECONDS = max(
    900,
    int(
        os.getenv(
            "GOLDEN_APPLE_SYNC_SECONDS",
            "10800",
        )
    ),
)


def save_bot_start(
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    traffic_source: str | None,
) -> tuple[
    bool,
    str | None,
]:
    """
    Сохраняет запуск бота.

    Логика источников:

    traffic_source:
    старое совместимое поле.
    Хранит first-touch источник.

    first_source:
    первый источник пользователя.
    Никогда не перезаписывается.

    last_source:
    источник последнего /start.
    Обновляется каждый раз.

    bot_started_at:
    первый запуск бота.

    last_started_at:
    последний запуск /start.

    Возвращает:
    - был ли это первый запуск;
    - сохранённый first-touch источник.
    """

    db = SessionLocal()

    try:
        now = datetime.now(
            timezone.utc
        )

        source = (
            traffic_source.strip()[:500]
            if traffic_source
            and traffic_source.strip()
            else "direct"
        )

        user = db.scalar(
            select(User).where(
                User.telegram_user_id
                == telegram_user_id
            )
        )

        if user is None:
            user = User(
                telegram_user_id=(
                    telegram_user_id
                ),
                username=username,
                first_name=first_name,
            )

            db.add(user)
            db.flush()

        else:
            user.username = username
            user.first_name = first_name

        is_first_start = (
            user.bot_started_at is None
        )

        # -------------------------
        # FIRST START
        # -------------------------

        if is_first_start:
            user.bot_started_at = now

        # -------------------------
        # FIRST-TOUCH SOURCE
        # -------------------------
        #
        # first_source и traffic_source
        # заполняем только если они
        # ещё пустые.
        #
        # Это специально НЕ зависит
        # от bot_started_at:
        # старый пользователь мог
        # существовать в базе,
        # но не иметь источника.
        # -------------------------

        if user.first_source is None:
            user.first_source = source

        if user.traffic_source is None:
            user.traffic_source = (
                user.first_source
                or source
            )

        # -------------------------
        # LAST-TOUCH
        # -------------------------
        #
        # Обновляется на каждом /start.
        # -------------------------

        user.last_source = source
        user.last_started_at = now

        saved_first_source = (
            user.first_source
            or user.traffic_source
        )

        db.commit()

        print(
            "BOT_START | "
            f"telegram_user_id="
            f"{telegram_user_id} "
            f"first_start="
            f"{is_first_start} "
            f"first_source="
            f"{saved_first_source} "
            f"last_source="
            f"{source}"
        )

        return (
            is_first_start,
            saved_first_source,
        )

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


@router.message(CommandStart())
async def start(
    message: Message,
    command: CommandObject,
):
    telegram_user = message.from_user

    if telegram_user is None:
        return

    traffic_source = (
        command.args
        if command.args
        else "direct"
    )

    first_start = False
    saved_traffic_source = None

    try:
        (
            first_start,
            saved_traffic_source,
        ) = await asyncio.to_thread(
            save_bot_start,
            telegram_user.id,
            telegram_user.username,
            telegram_user.first_name,
            traffic_source,
        )

    except Exception as exc:
        print(
            "BOT_START_DB_ERROR:",
            repr(exc),
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть Cosmi",
                    web_app=WebAppInfo(
                        url=settings.mini_app_url
                    ),
                )
            ]
        ]
    )

    await message.answer(
        (
            "Добавляй косметику по фото, "
            "следи за скидками и покупай выгоднее."
        ),
        reply_markup=kb,
    )

    try:
        # set_user_property_once
        # сам отвечает за то,
        # чтобы first-touch property
        # не перезаписывалась.
        #
        # Вызываем не только при
        # first_start, потому что
        # пользователь мог существовать
        # раньше без traffic_source.
        if saved_traffic_source:
            set_user_property_once(
                telegram_user.id,
                "traffic_source",
                saved_traffic_source,
            )

        track_event(
            telegram_user.id,
            "Started Bot",
        )

    except Exception as exc:
        print(
            "AMPLITUDE_STARTED_BOT_ERROR:",
            repr(exc),
        )


async def run_discount_check(
    bot: Bot,
    sync_catalog: bool = False,
):
    """
    Один проход проверки скидок.

    Если sync_catalog=True:
    сначала скачиваем свежий каталог
    Golden Apple.

    Затем проверяем товары пользователей
    и при необходимости отправляем
    личные Telegram-сообщения.
    """

    if sync_catalog:
        print(
            "GOLDEN_APPLE_SYNC | START"
        )

        try:
            await asyncio.to_thread(
                sync_golden_apple_feed
            )

            print(
                "GOLDEN_APPLE_SYNC | DONE"
            )

        except Exception as exc:
            # Ошибка обновления каталога
            # не должна останавливать бота.
            print(
                "GOLDEN_APPLE_SYNC | FAILED:",
                repr(exc),
            )

    db = SessionLocal()

    try:
        result = (
            await check_discount_notifications(
                bot,
                db,
            )
        )

        print(
            "DISCOUNT_CHECK |",
            result,
        )

    except Exception as exc:
        db.rollback()

        print(
            "DISCOUNT_CHECK_ERROR:",
            repr(exc),
        )

    finally:
        db.close()


async def discount_worker(
    bot: Bot,
):
    """
    Постоянный фоновый worker.

    1. Каждые несколько минут
       фиксирует состояние новых товаров.

    2. Раз в несколько часов
       обновляет каталог Golden Apple.

    3. После обновления каталога
       проверяет новые скидки.

    Worker последовательный:
    две проверки одновременно
    не запускаются.
    """

    # Даём боту спокойно запуститься.
    await asyncio.sleep(15)

    print(
        "DISCOUNT_WORKER | STARTED | "
        f"state_check="
        f"{DISCOUNT_STATE_CHECK_SECONDS}s | "
        f"catalog_sync="
        f"{GOLDEN_APPLE_SYNC_SECONDS}s"
    )

    # При первом старте НЕ обновляем
    # весь каталог.
    # Сначала просто фиксируем
    # текущие цены как базовое состояние.
    await run_discount_check(
        bot,
        sync_catalog=False,
    )

    next_catalog_sync = (
        time.monotonic()
        + GOLDEN_APPLE_SYNC_SECONDS
    )

    while True:
        try:
            await asyncio.sleep(
                DISCOUNT_STATE_CHECK_SECONDS
            )

            now = time.monotonic()

            should_sync_catalog = (
                now >= next_catalog_sync
            )

            await run_discount_check(
                bot,
                sync_catalog=(
                    should_sync_catalog
                ),
            )

            if should_sync_catalog:
                next_catalog_sync = (
                    time.monotonic()
                    + GOLDEN_APPLE_SYNC_SECONDS
                )

        except asyncio.CancelledError:
            print(
                "DISCOUNT_WORKER | STOPPED"
            )
            raise

        except Exception as exc:
            # Даже неожиданная ошибка
            # не должна убивать worker.
            print(
                "DISCOUNT_WORKER_ERROR:",
                repr(exc),
            )

            await asyncio.sleep(60)


async def main():
    if not settings.bot_token:
        raise SystemExit(
            "BOT_TOKEN is not set"
        )

    bot = Bot(
        settings.bot_token
    )

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    dp = Dispatcher()
    dp.include_router(router)

    discount_task = asyncio.create_task(
        discount_worker(bot)
    )

    try:
        await dp.start_polling(bot)

    finally:
        discount_task.cancel()

        try:
            await discount_task
        except asyncio.CancelledError:
            pass

        try:
            flush_amplitude()

        except Exception as exc:
            print(
                "AMPLITUDE_FLUSH_ERROR:",
                repr(exc),
            )

        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
