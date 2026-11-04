# Отдельный тестовый запуск

Общий исходный код; отдельные сервисы интерфейса, API, процесса бота и PostgreSQL.
Этот документ описывает подготовку; сервисы Railway ещё не созданы и не настроены.

API: рабочий каталог backend, запуск `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
Бот: рабочий каталог backend, запуск `python -m app.bot.main`.
Интерфейс: рабочий каталог frontend, сборка `npm install && npm run build`; каталог результата dist обслуживать как статический сайт.

## Переменные

| Где | Тест | Рабочая среда |
| --- | --- | --- |
| API и бот: APP_ENV | staging | production |
| API и бот: ANALYTICS_ENABLED | false | true |
| API и бот: AMPLITUDE_API_KEY | не задавать | ключ рабочего проекта |
| Сборка интерфейса: VITE_APP_ENV | staging | production |
| Сборка интерфейса: VITE_ANALYTICS_ENABLED | false | true |
| Сборка интерфейса: VITE_AMPLITUDE_API_KEY | не задавать | ключ рабочего проекта |

Новые флаги обязательны: без них аналитика по умолчанию отключена, даже если ключ уже задан.
APP_ENV и VITE_APP_ENV должны быть ровно production, чтобы разрешить отправку.

В тестовых API и боте задать одинаковые DATABASE_URL отдельной базы, BOT_TOKEN нового бота,
BOT_USERNAME нового бота и MINI_APP_URL тестового интерфейса.
PUBLIC_API_URL — адрес тестового API без /api; VITE_API_BASE — его адрес с /api.
VITE_BOT_USERNAME (сборка интерфейса) — username бота без @ для ссылок «поделиться» и карточки сторис: в тесте test_skincare_bot, в production по умолчанию cosmi_bbot.
Проверить также API_BASE_URL, используемый фоновым мониторингом скидок: он должен вести на тестовый API.
Ключ распознавания OPENAI_API_KEY задаётся отдельно при необходимости проверки распознавания.
В BotFather привязать кнопку тестового бота к HTTPS-адресу тестового интерфейса.
Запускать только один polling-процесс на токен. Ограничение доступа по Telegram ID пока не реализовано.

## Фоновые задачи бота

Переменные (необязательные, значения по умолчанию в скобках):
DISCOUNT_STATE_CHECK_SECONDS (300) — проход новых подписок и outbox;
GOLDEN_APPLE_SYNC_SECONDS (10800) — интервал импорта каталога, считается по таблице catalog_sync_runs;
GOLDEN_APPLE_RETRY_SECONDS (1800) — повтор после неудачного импорта;
DISCOUNT_PRODUCT_BATCH_SIZE (200), DISCOUNT_MAX_NEW_PRODUCTS_PER_RUN (1000), DISCOUNT_DELIVERY_BATCH_SIZE (100);
DB_POOL_SIZE (5), DB_MAX_OVERFLOW (10), DB_POOL_TIMEOUT (30), DB_APPLICATION_NAME.
В тесте рекомендуется GOLDEN_APPLE_SYNC_SECONDS=86400.

Таблицы и индексы фоновых задач создаются при старте и API, и бота (app/db/schema.py), миграция аддитивная.
После старта в логах API и бота есть строка DB_CONNECTION с типом адреса базы (railway_private или
railway_public_proxy) — без хоста и пароля. Каждая задача пишет JOB_METRICS. Подробности —
docs/railway-cost-plan.md.

Интеграционные тесты фоновых задач требуют отдельной PostgreSQL (не рабочей):
TEST_DATABASE_URL=postgresql://... python -m pytest tests_pg -q.

## Перед выпуском

- Проверить тестовые сценарии: распаковку, задания, награды, инвентарь, экипировку, ошибки API и повторный вход.
- В тесте проверить отсутствие сетевых запросов к Amplitude; ключи рабочего проекта в тест не копировать.
- Проверить production-переменные для API, бота и сборки интерфейса. Пересобрать интерфейс после изменения VITE_*.
- После выпуска выполнить контрольный сценарий в рабочем боте и проверить события и свойства в Amplitude.
- Сохранить резервную копию рабочей базы перед применением обновления.
- Прогнать python -m pytest tests -q и tests_pg на тестовой PostgreSQL.
- Проверить в логах бота DB_CONNECTION, первый JOB_METRICS catalog_import (status published/not_modified) и
  discount_check; убедиться, что работает ровно один процесс бота на токен.

## Развёрнуто 2026-11-01

- Railway project: you-beauty-test, ID e5a64e66-726e-4fbd-991b-769165d6dba2.
- Ветка всех трёх сервисов приложения: codex/cosmi-star-staging.
- test-api: https://test-api-production-21ba.up.railway.app
- test-web: https://test-web-production-f692.up.railway.app
- test-bot: отдельный процесс `python -m app.bot.main`, бот @test_skincare_bot.
- Postgres: отдельная база этого проекта. Все четыре сервиса получили статус Online.
- BOT_TOKEN хранится в test-api; test-bot использует ссылку `${{test-api.BOT_TOKEN}}`.
- Название окружения Railway production создано по умолчанию, но APP_ENV и VITE_APP_ENV равны staging: аналитика выключена.
- OPENAI_API_KEY пока не добавлен; распознавание фото требует его в test-api.
- После /start бот присылает кнопку «Открыть cosmi», ведущую на тестовый интерфейс.
- Проверено открытие интерфейса вне Telegram. Проверку авторизованного входа и сохранений пользователь выполняет в Telegram.
