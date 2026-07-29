import asyncio
from pathlib import Path
from unittest.mock import AsyncMock

from app.config import Settings
from app.monitoring import notify_admins


def test_admin_alerts_are_sent_and_bot_token_is_redacted() -> None:
    async def run() -> None:
        bot = AsyncMock()
        settings = Settings(
            BOT_TOKEN="123:very-secret-token",
            DATABASE_PATH=Path("./test.sqlite3"),
            ADMIN_TELEGRAM_IDS="101,202",
        )

        await notify_admins(
            bot,
            settings,
            context="тестовая операция",
            exception=RuntimeError(
                "Failure contains 123:very-secret-token"
            ),
        )

        assert bot.send_message.await_count == 2
        recipients = {
            call.args[0]
            for call in bot.send_message.await_args_list
        }
        assert recipients == {101, 202}
        for call in bot.send_message.await_args_list:
            alert = call.args[1]
            assert "тестовая операция" in alert
            assert "[BOT_TOKEN]" in alert
            assert settings.bot_token not in alert

    asyncio.run(run())
