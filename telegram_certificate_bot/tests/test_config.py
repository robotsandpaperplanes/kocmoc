import pytest

from app.config import Settings


def make_settings(admin_ids: str = "") -> Settings:
    return Settings(
        BOT_TOKEN="123456789:valid-test-token",
        ADMIN_TELEGRAM_IDS=admin_ids,
        _env_file=None,
    )


def test_admin_ids_are_parsed_from_comma_separated_value() -> None:
    settings = make_settings("123, 456,123")

    assert settings.admin_telegram_ids == {123, 456}
    assert settings.is_admin(123) is True
    assert settings.is_admin(999) is False


def test_invalid_admin_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="ADMIN_TELEGRAM_IDS"):
        make_settings("123,not-a-number")
