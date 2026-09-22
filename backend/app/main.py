import asyncio
from io import BytesIO

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from app.core.config import get_settings
from app.services.recognition import recognize_product_image

settings = get_settings()
router = Router()


@router.message(CommandStart())
async def start(message: Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть You Beauty",
                    web_app=WebAppInfo(url=settings.mini_app_url),
                )
            ]
        ]
    )

    await message.answer(
        "Пришли мне фото косметики — я попробую определить продукт.\n\n"
        "Или открой You Beauty.",
        reply_markup=kb,
    )


@router.message(F.photo)
async def recognize_photo(message: Message, bot: Bot):
    status_message = await message.answer(
        "Распознаю продукт..."
    )

    try:
        photo = message.photo[-1]

        telegram_file = await bot.get_file(
            photo.file_id
        )

        buffer = BytesIO()

        await bot.download_file(
            telegram_file.file_path,
            destination=buffer,
        )

        image_bytes = buffer.getvalue()

        result = await recognize_product_image(
            image_bytes=image_bytes,
            filename="telegram_photo.jpg",
        )

        brand = result.brand or "Не удалось определить"
        product_name = result.product_name or "Не удалось определить"
        variant = result.variant or "—"
        size = result.size or "—"
        category = result.category or "—"

        confidence_percent = round(
            result.confidence * 100
        )

        text = (
            "Похоже, я нашла продукт:\n\n"
            f"Бренд: {brand}\n"
            f"Название: {product_name}\n"
            f"Вариант / оттенок: {variant}\n"
            f"Объём / размер: {size}\n"
            f"Категория: {category}\n\n"
            f"Уверенность: {confidence_percent}%"
        )

        await status_message.edit_text(text)

    except Exception as exc:
        print(
            "RECOGNITION ERROR:",
            repr(exc),
        )

        await status_message.edit_text(
            "Не получилось распознать продукт. "
            "Попробуй прислать более чёткое фото упаковки."
        )


async def main():
    if not settings.bot_token:
        raise SystemExit(
            "BOT_TOKEN is not set"
        )

    bot = Bot(settings.bot_token)

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    dp = Dispatcher()
    dp.include_router(router)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
