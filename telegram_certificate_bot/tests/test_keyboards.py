from aiogram.types import ReplyKeyboardMarkup

from app.keyboards import (
    ADMIN_CERTIFICATE_ACTIVE_KEYBOARD,
    AMOUNT_KEYBOARD,
    BTN_ADMIN,
    BTN_CERTIFICATE,
    BTN_MENU_1,
    BTN_MENU_2,
    BTN_PAY,
    BTN_REDEEM,
    COMMENT_ENTRY_KEYBOARD,
    PAYMENT_KEYBOARD,
    main_menu,
)


def keyboard_texts(keyboard: ReplyKeyboardMarkup) -> set[str]:
    return {button.text for row in keyboard.keyboard for button in row}


def test_main_menu_uses_reply_keyboard_and_hides_admin_for_customers() -> None:
    customer_menu = main_menu(is_admin=False)
    admin_menu = main_menu(is_admin=True)

    assert isinstance(customer_menu, ReplyKeyboardMarkup)
    assert keyboard_texts(customer_menu) == {BTN_MENU_1, BTN_MENU_2, BTN_CERTIFICATE}
    assert BTN_ADMIN not in keyboard_texts(customer_menu)
    assert BTN_ADMIN in keyboard_texts(admin_menu)


def test_each_step_replaces_previous_buttons() -> None:
    assert keyboard_texts(AMOUNT_KEYBOARD).isdisjoint(
        {BTN_MENU_1, BTN_MENU_2, BTN_CERTIFICATE}
    )
    assert BTN_PAY not in keyboard_texts(COMMENT_ENTRY_KEYBOARD)
    assert BTN_PAY in keyboard_texts(PAYMENT_KEYBOARD)
    assert BTN_CERTIFICATE not in keyboard_texts(PAYMENT_KEYBOARD)
    assert BTN_REDEEM in keyboard_texts(ADMIN_CERTIFICATE_ACTIVE_KEYBOARD)
