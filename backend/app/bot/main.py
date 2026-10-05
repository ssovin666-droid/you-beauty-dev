import asyncio
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


settings = get_settings()
router = Router()


def save_bot_start(
    telegram_user_id: int,
    username: str | None,
    first_name: str | None,
    traffic_source: str | None,
) -> tuple[bool, str | None]:
    """
    Сохраняет запуск бота.

    Возвращает:
    - был ли это первый зафиксированный /start;
    - сохранённый first-touch traffic_source.
    """

    db = SessionLocal()

    try:
        user = db.scalar(
            select(User).where(
                User.telegram_user_id
                == telegram_user_id
            )
        )

        if user is None:
            user = User(
                telegram_user_id=telegram_user_id,
                username=username,
                first_name=first_name,
            )

            db.add(user)
            db.flush()

        else:
            # Эти данные можно безопасно актуализировать.
            # Они не относятся к рекламной атрибуции.
            user.username = username
            user.first_name = first_name

        is_first_start = (
            user.bot_started_at is None
        )

        if is_first_start:
            user.bot_started_at = (
                datetime.now(timezone.utc)
            )

            # traffic_source — строго first-touch.
            # Если первый /start был без параметра,
            # оставляем NULL навсегда.
            if (
                traffic_source
                and user.traffic_source is None
            ):
                user.traffic_source = (
                    traffic_source[:500]
                )

        saved_traffic_source = (
            user.traffic_source
        )

        db.commit()

        return (
            is_first_start,
            saved_traffic_source,
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

    # Raw Telegram /start parameter.
    # Например:
    # /start instagram_october
    # command.args == "instagram_october"
    traffic_source = (
        command.args
        if command.args
        else None
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
        # Ошибка аналитики/БД не должна ломать
        # сам Telegram UX.
        print(
            "BOT_START_DB_ERROR:",
            repr(exc),
        )

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть You Beauty",
                    web_app=WebAppInfo(
                        url=settings.mini_app_url
                    ),
                )
            ]
        ]
    )

    # Сначала успешно отвечаем пользователю.
    await message.answer(
        (
            "Добавляй косметику по фото, "
            "следи за скидками и покупай выгоднее."
        ),
        reply_markup=kb,
    )

    # Только после успешной обработки /start
    # отправляем продуктовую аналитику.
    try:
        if (
            first_start
            and saved_traffic_source
        ):
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
        # Amplitude никогда не должен
        # ломать работу бота.
        print(
            "AMPLITUDE_STARTED_BOT_ERROR:",
            repr(exc),
        )


async def main():
    if not settings.bot_token:
        raise SystemExit(
            "BOT_TOKEN is not set"
        )

    bot = Bot(
        settings.bot_token
    )

    # Удаляем старый webhook,
    # чтобы бот работал через polling.
    await bot.delete_webhook(
        drop_pending_updates=True
    )

    dp = Dispatcher()
    dp.include_router(router)

    try:
        await dp.start_polling(bot)

    finally:
        try:
            flush_amplitude()
        except Exception as exc:
            print(
                "AMPLITUDE_FLUSH_ERROR:",
                repr(exc),
            )


if __name__ == "__main__":
    asyncio.run(main())
