import asyncio
from unittest.mock import AsyncMock, patch

from app.bot import inline_sail
from app.keyboards import BTN_SAIL, INLINE_SAIL_QUERY


def test_inline_sail_returns_uncached_personal_result_with_relaunch_button() -> None:
    query = AsyncMock()
    query.query = ""

    with patch("app.bot.sailing_result", return_value="Вы плывете ✅"):
        asyncio.run(inline_sail(query))

    query.answer.assert_awaited_once()
    answer = query.answer.await_args.kwargs
    assert answer["cache_time"] == 0
    assert answer["is_personal"] is True

    result = answer["results"][0]
    assert result.title == BTN_SAIL
    assert result.input_message_content.message_text == "Вы плывете ✅"

    button = result.reply_markup.inline_keyboard[0][0]
    assert button.text == BTN_SAIL
    assert button.switch_inline_query_current_chat == INLINE_SAIL_QUERY


def test_inline_sail_ignores_unrelated_query() -> None:
    query = AsyncMock()
    query.query = "сертификат"

    asyncio.run(inline_sail(query))

    assert query.answer.await_args.kwargs["results"] == []
