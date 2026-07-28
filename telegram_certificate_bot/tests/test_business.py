from datetime import datetime, timezone
from unittest.mock import patch

from app.business import (
    CERTIFICATE_AMOUNTS,
    SAILING_OUTCOMES,
    format_amount,
    generate_public_id,
    normalize_public_id,
    sailing_result,
    truncate_comment,
    utc_time_text,
)


def test_certificate_amounts_are_formatted_as_rubles() -> None:
    assert CERTIFICATE_AMOUNTS == (5_000, 10_000, 30_000, 50_000)
    assert format_amount(5_000) == "5\u202f000 ₽"
    assert format_amount(50_000) == "50\u202f000 ₽"


def test_generate_public_id_uses_four_digit_groups() -> None:
    with patch("app.business.secrets.randbelow", side_effect=[7, 42]):
        assert generate_public_id() == "0007-0042"
    assert normalize_public_id(" 0007-0042 ") == "0007-0042"
    assert normalize_public_id("7-42") is None


def test_comment_truncation_uses_999_characters_and_ellipsis() -> None:
    assert truncate_comment("a" * 999) == "a" * 999
    truncated = truncate_comment("б" * 1000)
    assert truncated == ("б" * 999) + "…"
    assert len(truncated) == 1000
    assert truncate_comment("в" * 1200) == ("в" * 999) + "…"


def test_sailing_probability_branches_can_be_mocked() -> None:
    for expected, _weight in SAILING_OUTCOMES:
        with patch("app.business.random.choices", return_value=[expected]):
            assert sailing_result() == expected


def test_sailing_probabilities_add_up_to_one_hundred_percent() -> None:
    assert sum(weight for _message, weight in SAILING_OUTCOMES) == 100


def test_utc_time_text_is_24_hour_utc() -> None:
    moment = datetime(2026, 7, 27, 23, 5, tzinfo=timezone.utc)
    assert utc_time_text(moment) == "Сей час 23:05\nUTC+0"
