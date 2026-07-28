from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot

from .bot import setup_handlers
from .config import Settings
from .db import Database
from .monitoring import notify_admins


logger = logging.getLogger(__name__)


async def backup_loop(
    *,
    db: Database,
    bot: Bot,
    settings: Settings,
) -> None:
    """Create verified backups for as long as the bot is running."""
    while True:
        try:
            backup_path = await db.create_backup(
                settings.backup_dir,
                keep_count=settings.backup_keep_count,
            )
            logger.info("SQLite backup created: %s", backup_path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(
                "Could not create SQLite backup",
                exc_info=(type(exc), exc, exc.__traceback__),
            )
            await notify_admins(
                bot,
                settings,
                context="резервное копирование SQLite",
                exception=exc,
            )
        await asyncio.sleep(settings.backup_interval_hours * 60 * 60)


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings()
    bot = Bot(token=settings.bot_token)
    db = Database(settings.database_path)
    backup_task: asyncio.Task[None] | None = None

    try:
        await db.init()
        if settings.backup_interval_hours > 0:
            backup_task = asyncio.create_task(
                backup_loop(db=db, bot=bot, settings=settings),
                name="sqlite-backup",
            )
        dp = setup_handlers(db=db, settings=settings)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.error(
            "Bot stopped because of an unexpected error",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        await notify_admins(
            bot,
            settings,
            context="запуск или основной процесс бота",
            exception=exc,
        )
        raise
    finally:
        if backup_task:
            backup_task.cancel()
            with suppress(asyncio.CancelledError):
                await backup_task
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
