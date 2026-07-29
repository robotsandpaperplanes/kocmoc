import pytest

from app.config import Settings


@pytest.mark.parametrize(
    ("raw_ids", "expected"),
    [
        ("101,202", {101, 202}),
        ("101 202", {101, 202}),
        ("101;202", {101, 202}),
        ("101&202", {101, 202}),
        ("101,\n202  303", {101, 202, 303}),
    ],
)
def test_admin_ids_accept_common_separators(
    raw_ids: str,
    expected: set[int],
) -> None:
    settings = Settings(
        BOT_TOKEN="123:very-secret-token",
        ADMIN_TELEGRAM_IDS=raw_ids,
    )

    assert settings.admin_telegram_ids == expected


def test_admin_ids_reject_non_numeric_values() -> None:
    settings = Settings(
        BOT_TOKEN="123:very-secret-token",
        ADMIN_TELEGRAM_IDS="101 not-an-id",
    )

    with pytest.raises(ValueError, match="ADMIN_TELEGRAM_IDS"):
        _ = settings.admin_telegram_ids
