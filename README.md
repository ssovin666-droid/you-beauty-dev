# You Beauty — Telegram Mini App

Новая кодовая база основного продукта. Тестовый beauty bot сюда не переносится.

## Архитектура первой версии

- `frontend/` — React + TypeScript Telegram Mini App.
- `backend/` — FastAPI API + PostgreSQL + Telegram bot.
- AI-распознавание изолировано в `backend/app/services/recognition.py` и подключается отдельным этапом.
- Партнёрная логика отделена от обычных URL магазина: `Offer.product_url` + `Offer.affiliate_url`.
- Все клики по кнопке покупки идут через `/api/out/{offer_id}`, чтобы мы могли измерять коммерческую воронку.

## Уже заложенные сущности

- User
- Brand
- Product (конкретный SKU: размер/вариант — отдельный товар)
- Wishlist / Полка через TrackedItem
- Подписка на бренд
- Store
- Offer: цена и ссылка конкретного магазина
- OutboundClick: наши переходы в магазин

## Визуальная система

- K-beauty tech × editorial luxury
- Inter-подобный sans для заголовков/цен/CTA
- IBM Plex Mono-подобный mono для микротекста/метаданных
- молочная база, powder blue, dusty rose

## Локальный запуск backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env
# заполнить DATABASE_URL
uvicorn app.main:app --reload
```

Бот отдельно:

```bash
python -m app.bot.main
```

## Локальный запуск frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

## Следующий milestone

1. Telegram Mini App authentication (`initData`) и создание пользователя в БД.
2. Реальное добавление товара в Wishlist/Полку.
3. Upload фото → OpenAI Vision → structured recognition result.
4. Экран подтверждения товара.
5. Админка для Product / Store / Offer / affiliate URL.
6. Интеграция Admitad deeplink / SubID / postback.
