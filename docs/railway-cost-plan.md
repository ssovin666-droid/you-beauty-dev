# Снижение расходов Railway: изменения, проверка, план инфраструктуры

Статус: код готов в ветке `claude/railway-cost-optimization`, production и Railway не менялись.

## 1. Исходные данные

Подтверждено биллингом (8 окт — 8 ноя): $50,67, прогноз $61,25.

| Сервис | Проект | Итого | Egress | Память |
| --- | --- | --- | --- | --- |
| PostgreSQL | inspiring-achievement | $29,20 | 276,30 ГБ ($13,82) | $14,71 |
| Telegram-бот | faithful-flow | $13,83 | 211,93 ГБ ($10,60) | $3,12 |

Railway тарифицирует исходящий трафик $0,05/ГБ; подключение к базе по публичному URL считается egress,
трафик по приватной сети — нет ([документация](https://docs.railway.com/reference/pricing/understanding-your-bill)).
Приватная сеть работает только внутри одного проекта и окружения
([private networking](https://docs.railway.com/deploy/private-networking)).
Значит, сейчас каждый байт между ботом и базой оплачивается дважды: запросы — как egress бота, ответы — как egress базы.

### Гипотеза, подтверждённая на синтетической нагрузке (не на production)

| Что | Исходный код | Куда идёт трафик |
| --- | --- | --- |
| Проверка скидок каждые 5 мин | для **каждой подписки** `link_product_to_best_match`; несопоставленный товар каждый раз загружает до 5000 **полных** строк каталога (с `raw_params` ≈1,3 КБ и двумя длинными URL) | ответы БД → бот = egress PostgreSQL |
| Импорт каталога каждые 3 ч | весь фид отправляется в БД UPSERT'ом и переписывает все строки, даже без изменений | запросы бот → БД = egress бота |

Реальные размеры фида и число несопоставленных товаров нужно подтвердить логами `JOB_METRICS` после развёртывания.

## 2. Что изменено в коде

| Файл | Изменение |
| --- | --- |
| `backend/app/bot/main.py` | Worker разделён на шаги; расписание импорта хранится в БД (`catalog_sync_runs`), перезапуски не сбивают интервал; повтор после сбоя через `GOLDEN_APPLE_RETRY_SECONDS` (1800); блокировка `discount_monitor`; DB-работа вынесена из event loop в потоки; при старте — `ensure_job_schema` и строка `DB_CONNECTION` |
| `backend/app/services/discount_monitor.py` | 1) `initialize_new_subscriptions` — только подписки без baseline, старая скидка не рассылается; 2) `apply_catalog_version` — только при новой опубликованной версии и только товары, чьи строки изменились, каждый `product_id` один раз на всех подписчиков, пакетами; 3) `deliver_notifications` — outbox с `dedupe_key`, `FOR UPDATE SKIP LOCKED`, обработка 429/403 |
| `backend/app/services/product_matcher.py` | Кандидаты — 7 коротких колонок вместо ORM-объектов, полная строка только для победителя; `ORDER BY id`; лимит 5000 и алгоритм оценки без изменений; отрицательный кэш `product_match_misses` (инвалидируется при изменении товара — отпечаток, или строк каталога его бренда — флаг `stale` ставит импорт); связи по-прежнему переиспользуются |
| `backend/app/services/golden_apple_feed.py` | `If-None-Match`/`If-Modified-Since` + SHA-256 файла → идентичный фид не трогает БД; сравнение с компактными хешами `(external_id, id, content_hash, available)` → отправляются только новые и изменившиеся строки; присутствие в выгрузке отслеживается в памяти прохода и не пишется в строки; исчезнувшие товары, инвалидирование кэша и публикация версии — в одной транзакции; пустой фид не скрывает каталог; блокировка `catalog_import:golden-apple` + `FOR UPDATE` строки магазина |
| `backend/app/models/catalog.py` | `raw_params` — `deferred`; новые колонки `content_hash`, `changed_version`, `match_changed_version`; таблицы `catalog_sync_runs`, `product_match_misses`, `job_state`, `discount_notifications`, `job_runs` |
| `backend/app/db/schema.py` | Аддитивная миграция для API и бота: таблицы, nullable-колонки, индексы `CREATE INDEX CONCURRENTLY IF NOT EXISTS`, advisory lock, `lock_timeout` |
| `backend/app/core/locks.py` | `pg_try_advisory_lock` на отдельном соединении: снимается сам при падении процесса |
| `backend/app/core/metrics.py` | `JOB_METRICS {...}` в лог + `job_runs`: число запусков, SQL-запросов, строк, оценка байт параметров, товаров, кандидатов, вставлено/изменено/пропущено, длительность, RSS |
| `backend/app/db/session.py` | `describe_database_url` (только класс адреса), `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`/`DB_POOL_TIMEOUT` (значения по умолчанию прежние), `application_name` для `pg_stat_activity` |
| `backend/app/api/routes.py` | `/admin/match/debug` читает полные строки только для топ-10; ручной импорт уважает блокировку |
| `backend/tests_pg/`, `backend/scripts/bench_background_jobs.py` | Интеграционные тесты на PostgreSQL и стенд сравнения «до/после» |

Аналитика Amplitude не менялась и не удалялась: пользовательских функций не добавлено, технические метрики
идут только в логи и `job_runs`. В логи не пишутся токены, initData, тексты, URL и строки подключения; из
`PRODUCT_MATCH` убрано название товара.

### Надёжность уведомлений

- Уведомление создаётся в outbox в той же транзакции, что и `last_seen_*`. Повтор той же версии (сбой посередине,
  второй worker) не создаёт дубль: цена уже обновлена, плюс уникальный `dedupe_key = tracked_item:version:price`.
- Отправка: `pending → sending → sent`. Сбой между отправкой в Telegram и сохранением оставляет `sending`; через
  10 минут строка становится `uncertain` и **не отправляется повторно** — выбрано «не больше одного раза»,
  дубль скидки хуже пропуска. Такие случаи видны запросом к `discount_notifications`.
- 429 → повтор через `retry_after`; 403/400/404 → `failed`; прочие ошибки — до 5 попыток с паузой.
  Сетевой тайм-аут может означать доставленное сообщение — редкий дубль в этом случае возможен.

## 3. Результаты проверок

Тесты: `python -m pytest tests -q` (25 прежних) и
`TEST_DATABASE_URL=postgresql://... python -m pytest tests_pg -q` (17 новых, PostgreSQL 16):

| Требование | Тест |
| --- | --- |
| Нет повторного тяжёлого поиска при неизменном каталоге | `test_no_repeated_heavy_search_when_catalog_unchanged` (0 поисков, ≤ 8 SQL за проход; 304 и SHA-256; цена другого или того же бренда кэш не сбрасывает; новый товар бренда — один поиск) |
| Только изменённые строки | `test_import_sends_only_changed_rows` |
| Один товар у нескольких пользователей | `test_one_product_many_subscribers` (1 поиск, 5 уведомлений) |
| Нет старой скидки при первом сохранении | `test_first_save_does_not_send_existing_discount`, `test_first_observation_in_new_version_is_baseline` |
| Появление скидки и дальнейшее снижение | `test_discount_appears_then_drops_further` |
| Исчезновение и возвращение | `test_product_disappears_and_returns`, `test_empty_feed_does_not_hide_catalog` |
| Сбой и повтор импорта | `test_import_failure_publishes_nothing_and_retry_succeeds` |
| Сбой между отправкой и сохранением, сбой посередине шага | `test_crash_between_send_and_save_is_not_resent`, `test_phase_crash_midway_is_idempotent`, `test_rerun_same_version_creates_no_duplicates` |
| Два worker'а одновременно | `test_two_imports_at_once_only_one_runs`, `test_advisory_lock_is_exclusive_and_released_on_disconnect`, `test_two_delivery_workers_send_each_notification_once` |
| Качество сопоставления | `test_match_quality_is_unchanged`: 250 шумных товаров, сравнение с исходным `product_matcher.py` — одинаковые `matched` и `confidence` у всех, тот же товар у 250/250 |
| Инвалидирование при изменении товара | `test_negative_cache_invalidated_when_product_changes` |

Миграция проверена на копии базы со старой схемой (дважды подряд, идемпотентно).

### Одинаковая нагрузка до/после (стенд, точные байты на проводе)

`scripts/bench_background_jobs.py`: 30 000 товаров (средняя строка 1,95 КБ, JSON фида 34 МБ), 300 пользователей,
900 подписок на 400 товаров, 20 % не сопоставляются. Байты считает TCP-прокси между процессом и PostgreSQL.

| Шаг | Исходный: в БД / из БД | Новый: в БД / из БД |
| --- | --- | --- |
| 5-минутный проход, каталог не менялся | 0,57 МБ / **93,4 МБ**, 21,6 с | 3 КБ / 1,9 КБ, 0,02 с |
| Импорт, изменилось 5 % цен, 1 % исчез | **59,3 МБ** / 0,03 МБ, 14,5 с | 3,7 МБ / 1,6 МБ, 2,7 с |
| Проход после такого импорта | 0,57 МБ / 99,9 МБ | 0,15 МБ / 2,8 МБ |
| Импорт идентичного фида | 59,3 МБ / 0,03 МБ | 3,6 КБ / 2,5 КБ |
| Уведомлений после изменения | 22 | 22 |
| Размер `store_catalog_items` после 3 импортов | 151 МБ (переписаны все строки) | 67 МБ |

Это синтетика: абсолютные числа зависят от реального фида и доли несопоставленных товаров. Порядок величины
совпадает с биллингом (исходный 5-минутный проход × 8640 проходов в месяц ≫ 276 ГБ), но экономию нужно
подтвердить замерами ниже. Первый импорт после развёртывания один раз перепишет все строки (хешей ещё нет).

Планы запросов (EXPLAIN ANALYZE на том же стенде): кандидаты по бренду — Index Scan
`ix_store_catalog_store_brand` (0,5 мс); шаг 1 — Index Only Scan `ix_tracked_items_uninitialized`; шаг 2 —
Index Scan `ix_sci_store_changed_version`; инвалидирование кэша — `ix_sci_store_match_version`;
fallback по части бренда (`ILIKE '%…%'`) — Seq Scan (27 мс на 30 тыс.), выполняется только при промахе кэша.
Опционально `CREATE EXTENSION pg_trgm` + GIN-индекс на `brand_normalized` — только после проверки прав и вручную.

## 4. Оставшиеся ограничения

- Реальные Railway-переменные, развёрнутые коммиты и размер фида не проверены (нет доступа; фид из песочницы
  недоступен). Есть ли у advcake `ETag`/`Last-Modified`, покажет поле `not_modified_by` в `JOB_METRICS`.
- Импорт держит одну транзакцию на время разбора фида (минуты). Если строку каталога, которую импорт уже обновил,
  в это время связывает API, запрос подождёт конца импорта.
- Во время импорта бот держит в памяти компактное состояние (~100–150 байт на товар).
- Шаг 2 зависит от версий каталога: если старая версия кода временно вернётся и обновит цены, после повторного
  выката нужно выполнить `UPDATE store_catalog_items SET content_hash = NULL` (следующий импорт перепишет всё один раз).
- Блокировка API-пула (см. `docs/architecture-load-analysis.md`) этой веткой не исправлена — по задаче анализ без
  изменений; исправление — ограничение параллельных запросов ниже размера пула.
- `uncertain`-уведомления не досылаются автоматически.

## 5. План Railway (выполняется вручную, после согласования)

### Целевое состояние

- **production**: один проект, окружение production — сервисы `api`, `bot`, `web`, `Postgres`. API и бот подключаются
  `DATABASE_URL=${{Postgres.DATABASE_URL}}` (приватный `*.railway.internal`), публичный URL базы не используется
  приложением. Процессы остаются раздельными.
- **staging**: отдельное окружение (или текущий проект `you-beauty-test`) со своей базой, своим ботом
  (`@test_skincare_bot`), своими адресами; приватная сеть окружений изолирована. Рекомендуется
  `GOLDEN_APPLE_SYNC_SECONDS=86400` на staging.

### Безопасный порядок

Переносим не базу, а сервисы без состояния — в проект базы `inspiring-achievement`. Действующая база не
копируется и не удаляется.

0. **Подготовка.** Записать текущие значения (без публикации секретов): коммиты, переменные бота и API, домены,
   `MINI_APP_URL`, `API_BASE_URL`, `VITE_API_BASE`. Снять бэкап базы (`pg_dump` или бэкап Railway) — по
   `docs/testing-release.md`. Записать 7 дней Usage по сервисам (раздел 6).
1. **Проверить код на staging.** Развернуть ветку в `you-beauty-test`, убедиться: `DB_CONNECTION host_kind`,
   `JOB_METRICS` для `catalog_import` и `discount_check`, отсутствие Amplitude-запросов (`APP_ENV=staging`).
2. **Выкатить код в текущую production-конфигурацию** (без переноса). Уже это убирает основной объём трафика.
   Первый импорт перепишет все строки один раз. Наблюдать 2–3 суток.
3. **Создать бот в проекте базы.** Новый сервис из того же репозитория/ветки, команда `python -m app.bot.main`,
   переменные как у текущего бота, но `DATABASE_URL=${{Postgres.DATABASE_URL}}`. Не запускать, пока работает
   старый бот (один polling на токен).
4. **Переключение бота (простой ~1 мин).** Остановить старый бот (удалить активный деплой / выключить сервис, не
   удаляя сервис и переменные) → запустить новый. Advisory locks не дадут двум worker'ам дублировать задачи, даже
   если окна пересекутся; Telegram-поллинг двух процессов даст `TelegramConflictError` у одного из них.
5. **Проверка соединений.** В логах нового бота `DB_CONNECTION | {'host_kind': 'railway_private'}`, затем
   `DISCOUNT_WORKER | STARTED`, `JOB_METRICS {"job": "discount_check" ...}`. В БД:
   `SELECT application_name, client_addr, count(*) FROM pg_stat_activity GROUP BY 1,2;` — подключения бота с
   приватного адреса. `/start` в боте отвечает кнопкой.
6. **API.** Если API тоже в другом проекте — аналогично: новый сервис в проекте базы с приватным `DATABASE_URL`.
   Адрес `*.up.railway.app` привязан к сервису, поэтому либо переводить кастомный домен, либо пересобрать фронтенд с
   новым `VITE_API_BASE` и поменять `API_BASE_URL` у бота (ссылки в уведомлениях). Старые ссылки из уже отправленных
   уведомлений ведут на старый адрес — старый API держать до 30 дней или настроить редирект.
7. **Откат.** Остановить новый сервис, запустить старый с прежними переменными (они не менялись). База одна и та же,
   откатывать нечего. Схема аддитивная: старый код с ней работает (см. ограничение про `content_hash`).
8. Через 7 дней стабильной работы удалить старые сервисы (не базу) и закрыть публичный TCP-прокси базы, если им
   никто не пользуется.

### Память PostgreSQL и соединения

Проверить до каких-либо изменений лимитов:

```sql
SHOW shared_buffers; SHOW work_mem; SHOW maintenance_work_mem; SHOW max_connections;
SELECT pg_size_pretty(pg_database_size(current_database()));
SELECT relname, n_live_tup, n_dead_tup, last_autovacuum, pg_size_pretty(pg_total_relation_size(relid))
FROM pg_stat_user_tables ORDER BY pg_total_relation_size(relid) DESC LIMIT 10;
SELECT application_name, state, count(*) FROM pg_stat_activity GROUP BY 1, 2;
```

- Учитываемая память контейнера включает кэш страниц. Исходный импорт каждые 3 часа переписывал весь каталог
  (включая TOAST `raw_params`), удваивал таблицу мёртвыми версиями и прогревал её целиком. После изменений
  записываются только изменения — ожидается меньший рабочий набор, но лимит снижать только по графику памяти за
  7+ дней после выката.
- После первого полного импорта новой версией — `VACUUM (ANALYZE) store_catalog_items;` вне пика.
  `VACUUM FULL` блокирует таблицу — только в окне обслуживания и если `n_dead_tup`/размер это оправдывают.
- Соединения: API 5+10, бот 5+10, плюс 1–2 соединения блокировок на процесс — ≈ 35 < `max_connections`.
  При добавлении реплик API умножать.

## 6. Как измерить экономию

1. **До выката** — 7 суток Railway Usage по сервисам: egress ГБ/сутки и средняя память. Из логов текущего бота:
   число строк `PRODUCT_MATCH` за 5 минут (= поисков за проход) и `GOLDEN_APPLE_SYNC | DONE` (processed).
2. **Одинаковая нагрузка** — `scripts/bench_background_jobs.py` на старом и новом коде (уже выполнено, таблица выше);
   можно повторить с `--items`, близким к `processed` из логов.
3. **После выката** — сводка из базы:

```sql
SELECT job, date_trunc('day', started_at) AS day, count(*) AS runs,
       sum((metrics->>'sql_statements')::int) AS sql,
       sum((metrics->>'rows_sent')::int) AS rows_sent,
       sum((metrics->>'db_rows_compact_loaded')::int) AS compact_rows,
       sum((metrics->>'match_searches')::int) AS searches,
       sum((metrics->>'match_candidates')::int) AS candidates,
       avg(duration_ms)::int AS avg_ms
FROM job_runs GROUP BY 1, 2 ORDER BY 2 DESC, 1;

SELECT status, count(*) FROM catalog_sync_runs GROUP BY 1;
SELECT status, count(*) FROM discount_notifications GROUP BY 1;
```

   Пустые 5-минутные проходы видны только в логах `JOB_METRICS` (в `job_runs` не пишутся).
4. **Сравнение** — суточный egress и память по сервисам за 7 дней до и после, нормированные на число подписок и
   импортов. Отдельно — после шага 2 (код) и после шагов 3–6 (приватная сеть), чтобы разделить эффекты.
   `sql_params_bytes_est` — оценка, а не размер протокола; точный трафик — только метрики Railway.
