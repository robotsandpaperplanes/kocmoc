from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from .bot import setup_handlers
from .config import Settings
from .db import Database


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = Settings()
    db = Database(settings.database_path)
    await db.init()

    bot = Bot(token=settings.bot_token)
    dp = setup_handlers(db=db, settings=settings)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
