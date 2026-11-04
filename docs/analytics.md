# Аналитика Cosmi Star

События присутствуют в общем коде, но отправляются только в явно включённой production-среде.
Настройки: testing-release.md. Идентификатор пользователя — Telegram ID.

| Событие | Момент и свойства |
| --- | --- |
| character_progress_viewed | Первый показ блока за его монтирование: status, shelf_count, shelf_target, archetype, quest |
| character_unbox_clicked | Нажатие кнопки или капсулы: source=button/capsule |
| character_unbox_started | Старт открытия капсулы в полноэкранной распаковке (оверлей может открыться автоматически, но капсулу открывает пользователь): archetype, trigger=tap/button/skip |
| character_unboxed | Сервер впервые сохранил unboxed_at: archetype |
| character_unbox_failed | Запрос распаковки завершился ошибкой |
| item_received | Клиент показал ранее выданную награду: reward_id, kind, rarity, item_code, source. Это показ награды, а не момент выдачи в БД |
| quest_completed | unlock — после сохранения распаковки на сервере; first_item — при показе награды wishlist_quest с reward_id |
| inventory_opened | Открытие инвентаря: owned |
| item_equipped / item_unequipped | Успешный ответ API: item_code |
| item_equip_failed | Ошибка API: item_code, equip |
| character_help_opened | Открытие инструкции |
| character_quest_clicked | Переход по заданию: quest |
| character_share_opened | Открытие панели «Поделиться» на главной |
| character_shared | Существующее событие сценария SharePanel; не считать доказательством публикации истории |
| character_tapped | Нажатие на персонажа, ограничено разом в секунду: archetype |

Для событий с reward_id клиент задаёт стабильный insert_id (имя события + ID награды),
чтобы Amplitude мог устранить повторную доставку в пределах своего окна дедупликации.
Это не гарантия exactly-once. Доставка событий best effort; серверного outbox пока нет.
Для подсчёта выданных наград независимо от открытия приложения нужна отдельная серверная аналитика выдачи.

Основная воронка: character_progress_viewed → character_unbox_started → character_unboxed → inventory_opened → item_equipped.
character_unbox_clicked — отдельный путь, поскольку распаковка может запускаться автоматически.

## Технические метрики фоновых задач

Не относятся к Amplitude и не отправляются туда ни в одной среде. Импорт каталога, проверка скидок и доставка
уведомлений пишут числовые счётчики в лог (строка JOB_METRICS) и в таблицу job_runs: число SQL-запросов и строк,
уникальных товаров, кандидатов, вставленных/изменённых/пропущенных строк, длительность, память процесса.
Токены, initData, тексты уведомлений, URL и строки подключения в них не попадают. Существующие события не менялись.
