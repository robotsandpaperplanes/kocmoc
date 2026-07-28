"""Bothost-compatible entry point for the Telegram bot."""

import asyncio

from telegram_certificate_bot.app.main import main


if __name__ == "__main__":
    asyncio.run(main())
