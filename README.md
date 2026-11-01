# You Beauty — Telegram Mini App

Новая кодовая база основного продукта. Тестовый beauty bot сюда не переносится.

## Архитектура первой версии

- `frontend/` — React + TypeScript Telegram Mini App.
- `backend/` — FastAPI API + PostgreSQL + Telegram bot.
- AI-распознавание изолировано в `backend/app/services/recognition.py` и подключается отдельным этапом.
- Партнёрная логика отделена от обычных URL магазина: `Offer.product_url` + `Offer.affiliate_url`.
- Все клики по кнопке покупки идут через `/api/out/{offer_id}`, чтобы мы могли измерять коммерческую воронку.
- Ссылки из уведомлений, Wishlist и Полки передают в `/api/out/{offer_id}` внутренний `user_id`. При переходе API получает из БД `telegram_user_id` и добавляет его в `sub1` партнёрной ссылки (например, `sub1=123456789`). Существующий `sub1` заменяется, остальные параметры сохраняются. Общие ссылки в каталоге не изменяются. Старые ссылки без известного пользователя продолжают работать без персонализации.

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

## Геймификация: персонаж Cosmi Star

3D-звёздочка на главной, тип и цвет которой зависят от оттенков товаров на Полке.
Визуальный референс — `frontend/design-reference/character/`.

**Данные (backend)**

- `Product.shade_group`: `bold | goth | nude | pastel | glow | glitter | null`. Новые товары получают его из `/recognize` (модель возвращает поле `shade_group`). Существующие товары остаются `null`, их правят через админку.
- `UserCharacter`, `Item`, `UserItem`, `RewardEvent` (+ `ShareCard` для PNG сторис) — `app/models/character.py`. Каталог предметов сидится при старте (`ITEM_CATALOG` в `app/services/character.py`).
- Форма звезды уникальна для пользователя: при открытии (10 товаров на Полке) сервер один раз выдаёт случайный `UserCharacter.shape_seed`, дальше он не меняется. Клиент строит из него форму детерминированно (`frontend/src/lib/character/shape.ts`: число лучей 5–8, длины, наклоны). Не меняйте генератор — у всех поменяются формы.
- Тип: самый частый `shade_group` на Полке, акцент — второй. Если доля лидера ≤ 30% («не больше 3 из 10»), тип — `chameleon`. Товары без `shade_group` не учитываются, ничьи решаются фиксированным порядком `bold → goth → nude → pastel → glow → glitter`.
- Награды выдаются только на сервере. Повторная выдача невозможна: `RewardEvent` уникален по `(user_id, reward_key)`.
  - `unlock` — 10 товаров на Полке;
  - `quest:first_item` — 5 товаров, добавленных в Wishlist после открытия персонажа → «Заколка» (если она уже есть — первый неполученный предмет);
  - `purchase:<order_id>` — подтверждённая покупка: редкость по весам 70/22/7/1 → случайный неполученный предмет этой редкости, иначе эволюция (`UserCharacter.evolution += 1`). Клики `/out` наград не дают.

**API**

- `GET /api/character` — статус (`locked | ready_to_unbox | active`), прогресс, тип/акцент, распределение полки, инвентарь, надетые предметы, текущее задание, непоказанные награды.
- `POST /api/character/unbox`, `POST /api/character/equip` `{item_code, equip}`, `POST /api/character/rewards/ack` `{reward_ids}`, `POST /api/character/shared`.
- `POST /api/character/share-card` (multipart PNG ≤ 4 МБ) → `{url}`; картинка отдаётся публично по `GET /api/share-cards/{token}.png`.
- Админка (`X-Admin-Key`):
  - `GET /api/admin/products/shade-groups?missing_only=true` — товары без оттенка;
  - `PATCH /api/admin/products/{id}/shade-group` `{"shade_group": "goth"}`;
  - `POST /api/admin/character/purchase-reward` `{"order_id": "...", "user_id": 1}` или `{"telegram_user_id": ...}` — ручное подтверждение покупки. Будущий postback партнёрки должен вызывать `grant_purchase_reward(db, user_id, order_id)`.

**Переменные окружения**

- backend `PUBLIC_API_URL` — публичный https-адрес API без `/api` (для ссылок на карточки сторис). Если не задан, адрес берётся из запроса с учётом `X-Forwarded-Proto`.
- frontend `VITE_BOT_USERNAME` — username бота для карточки и ссылок «поделиться» (по умолчанию `cosmi_bbot`).

**Frontend**

- Шрифты подключены из npm (`@fontsource`): весь текст — Manrope, логотип «cosmi» (всегда с маленькой буквы) — Unbounded SemiBold 600, 20px, трекинг −0.03em (`.logo`).

- `src/lib/character/scene.ts` — three.js-сцена без React (порт референса), `components/character/CosmiStar.tsx` — React-обёртка, грузит three.js отдельным чанком.
- Рендер останавливается, когда персонаж вне экрана, вкладка скрыта или мини-апп свёрнут. `devicePixelRatio` ограничен значением 2. На устройствах без WebGL, со слабым железом, при потере контекста или медленных кадрах показывается статичная SVG-картинка.
- Тема — по `Telegram.WebApp.colorScheme`, safe area — `env(safe-area-inset-*)` и `safeAreaInset` из Telegram.
- События Amplitude: `character_progress_viewed`, `character_unboxed`, `character_shared`, `character_tapped`, `item_received`, `quest_completed`, `inventory_opened`.

## Следующий milestone

1. Telegram Mini App authentication (`initData`) и создание пользователя в БД.
2. Реальное добавление товара в Wishlist/Полку.
3. Upload фото → OpenAI Vision → structured recognition result.
4. Экран подтверждения товара.
5. Админка для Product / Store / Offer / affiliate URL.
6. Интеграция Admitad deeplink / SubID / postback.
