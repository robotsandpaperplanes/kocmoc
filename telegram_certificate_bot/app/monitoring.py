from __future__ import annotations

import logging

from aiogram import Bot
from .config import Settings


logger = logging.getLogger(__name__)
MAX_ALERT_LENGTH = 3500


async def notify_admins(
    bot: Bot,
    settings: Settings,
    *,
    context: str,
    exception: BaseException,
) -> None:
    """Send a short operational alert without exposing the bot token."""
    if not settings.notify_admins_on_error:
        return

    details = str(exception).replace(settings.bot_token, "[BOT_TOKEN]")
    alert = (
        "⚠️ Ошибка Telegram-бота\n\n"
        f"Операция: {context}\n"
        f"Тип: {type(exception).__name__}\n"
        f"Описание: {details or 'без описания'}"
    )[:MAX_ALERT_LENGTH]

    for telegram_id in settings.admin_telegram_ids:
        try:
            await bot.send_message(telegram_id, alert)
        except Exception:
            logger.warning(
                "Could not send an error alert to administrator %s",
                telegram_id,
                exc_info=True,
            )
