import asyncio
import os
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
from app.core.locks import advisory_lock
from app.core.metrics import JobMetrics, persist_job_run
from app.db.schema import ensure_job_indexes, ensure_job_schema
from app.db.session import (
    SessionLocal,
    database_url,
    describe_database_url,
    engine,
)
from app.models.catalog import CatalogSyncRun, User
from app.services.discount_monitor import (
    apply_catalog_version,
    deliver_notifications,
    initialize_new_subscriptions,
)
from app.services.golden_apple_feed import (
    sync_golden_apple_feed,
)


settings = get_settings()
router = Router()


DISCOUNT_LOCK_NAME = "discount_monitor"


# Как часто проверять новые подписки и outbox.
# Здесь каталог не скачивается и подписки
# целиком не сканируются.
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


# Повтор после неудачного импорта.
GOLDEN_APPLE_RETRY_SECONDS = max(
    300,
    int(
        os.getenv(
            "GOLDEN_APPLE_RETRY_SECONDS",
            "1800",
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
                    text="Открыть cosmi",
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


def _run_sync_phases() -> dict:
    """Шаги 1 и 2 в отдельном потоке (не блокируют polling)."""

    db = SessionLocal()
    try:
        init_stats = initialize_new_subscriptions(db)
        version_stats = apply_catalog_version(db)
        return {
            "init": init_stats,
            "version": version_stats,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def run_discount_check(
    bot: Bot,
) -> dict | None:
    """Один проход мониторинга скидок.

    Под межпроцессной блокировкой: при пересечении
    старого и нового развёртываний второй процесс
    пропускает проход. В обычном состоянии (нет новых
    подписок, нет новой версии каталога, пустой outbox)
    это несколько коротких запросов.
    """

    metrics = JobMetrics("discount_check")

    with metrics:
        with advisory_lock(engine, DISCOUNT_LOCK_NAME) as acquired:
            if not acquired:
                metrics.set("status", "skipped_locked")
                return None

            try:
                phases = await asyncio.to_thread(
                    _run_sync_phases
                )
                delivery = await deliver_notifications(
                    bot,
                    SessionLocal,
                )
            except Exception as exc:
                metrics.ok = False
                print(
                    "DISCOUNT_CHECK_ERROR:",
                    type(exc).__name__,
                    str(exc)[:200],
                )
                return None

            metrics.set("status", "ok")

            result = {
                **phases,
                "delivery": delivery,
            }

            print("DISCOUNT_CHECK |", result)

    # Пишем в job_runs только проходы с работой,
    # чтобы пустые 5-минутные проходы не росли
    # таблицей (они всё равно видны в JOB_METRICS).
    if (
        metrics.get("unique_products")
        or metrics.get("delivery_sent")
        or metrics.get("delivery_failed")
    ):
        await asyncio.to_thread(
            persist_job_run,
            SessionLocal,
            metrics,
        )

    return result


def catalog_import_due() -> bool:
    """Расписание импорта хранится в базе.

    Перезапуски и новые развёртывания не сбивают
    интервал и не запускают лишний импорт.
    """

    db = SessionLocal()
    try:
        last = db.execute(
            select(
                CatalogSyncRun.status,
                CatalogSyncRun.started_at,
            )
            .order_by(CatalogSyncRun.id.desc())
            .limit(1)
        ).first()
    finally:
        db.close()

    if last is None:
        return True

    status, started_at = last

    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)

    age = (
        datetime.now(timezone.utc) - started_at
    ).total_seconds()

    if status == "failed":
        return age >= GOLDEN_APPLE_RETRY_SECONDS

    if status == "running":
        # Запуск, оставшийся от упавшего процесса.
        return age >= GOLDEN_APPLE_SYNC_SECONDS

    return age >= GOLDEN_APPLE_SYNC_SECONDS


async def run_catalog_import_if_due() -> bool:
    """Возвращает True, если опубликована новая версия."""

    try:
        due = await asyncio.to_thread(catalog_import_due)
    except Exception as exc:
        print(
            "GOLDEN_APPLE_SYNC | SCHEDULE CHECK FAILED:",
            type(exc).__name__,
        )
        return False

    if not due:
        return False

    try:
        result = await asyncio.to_thread(
            sync_golden_apple_feed
        )
    except Exception as exc:
        # Ошибка импорта не должна останавливать бота.
        print(
            "GOLDEN_APPLE_SYNC | FAILED:",
            type(exc).__name__,
        )
        return False

    return bool(
        result
        and result.get("status") == "published"
    )


async def discount_worker(
    bot: Bot,
):
    """Постоянный фоновый worker.

    Каждые DISCOUNT_STATE_CHECK_SECONDS:
    1. фиксирует цену новых подписок;
    2. если опубликована новая версия каталога —
       обновляет цены изменившихся товаров
       и ставит уведомления в outbox;
    3. отправляет outbox.

    Раз в GOLDEN_APPLE_SYNC_SECONDS (по базе)
    импортирует каталог; после публикации версии
    сразу выполняет проход мониторинга.
    """

    # Даём боту спокойно запуститься.
    await asyncio.sleep(15)

    # Индексы — оптимизация, строятся в фоне
    # и не задерживают ни бота, ни API.
    await asyncio.to_thread(
        ensure_job_indexes,
        engine,
    )

    print(
        "DISCOUNT_WORKER | STARTED | "
        f"state_check="
        f"{DISCOUNT_STATE_CHECK_SECONDS}s | "
        f"catalog_sync="
        f"{GOLDEN_APPLE_SYNC_SECONDS}s | "
        f"catalog_retry="
        f"{GOLDEN_APPLE_RETRY_SECONDS}s"
    )

    while True:
        try:
            await run_discount_check(bot)

            if await run_catalog_import_if_due():
                await run_discount_check(bot)

            await asyncio.sleep(
                DISCOUNT_STATE_CHECK_SECONDS
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
                type(exc).__name__,
            )

            await asyncio.sleep(60)


async def main():
    if not settings.bot_token:
        raise SystemExit(
            "BOT_TOKEN is not set"
        )

    print(
        "DB_CONNECTION |",
        describe_database_url(database_url),
    )

    # Таблицы фоновых задач: бот может
    # стартовать раньше нового API.
    print("STARTUP | job schema", flush=True)
    await asyncio.to_thread(
        ensure_job_schema,
        engine,
    )
    print("STARTUP | ready", flush=True)

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
