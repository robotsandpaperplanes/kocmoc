from app.keyboards import (
    AMOUNT_KEYBOARD,
    AMOUNT_LABELS,
    BTN_BACK,
    payment_keyboard,
)


def keyboard_rows(keyboard) -> list[list[str]]:
    return [
        [button.text for button in row]
        for row in keyboard.keyboard
    ]


def test_certificate_amount_keyboard_uses_ruble_denominations() -> None:
    labels = {
        "5\u202f000 ₽": 5_000,
        "10\u202f000 ₽": 10_000,
        "30\u202f000 ₽": 30_000,
        "50\u202f000 ₽": 50_000,
    }
    assert AMOUNT_LABELS == labels
    assert keyboard_rows(AMOUNT_KEYBOARD) == [
        ["5\u202f000 ₽", "10\u202f000 ₽"],
        ["30\u202f000 ₽", "50\u202f000 ₽"],
        [BTN_BACK],
    ]


def test_payment_button_uses_selected_ruble_amount() -> None:
    assert keyboard_rows(payment_keyboard(30_000)) == [
        ["Оплатить 30\u202f000 ₽"],
        [BTN_BACK],
    ]
