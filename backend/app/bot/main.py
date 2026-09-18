import asyncio

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo

from app.core.config import get_settings

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
        "Добавляй косметику по фото, следи за скидками и покупай выгоднее.",
        reply_markup=kb,
    )


async def main():
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set")
    bot = Bot(settings.bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
