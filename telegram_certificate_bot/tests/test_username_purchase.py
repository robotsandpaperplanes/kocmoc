from app.keyboards import (
    BTN_BUY_USERNAME,
    BTN_HOME,
    BTN_NO,
    BTN_YES,
    HOME_KEYBOARD,
    MAIN_MENU_KEYBOARD,
    USERNAME_PURCHASE_KEYBOARD,
)


def keyboard_rows(keyboard) -> list[list[str]]:
    return [
        [button.text for button in row]
        for row in keyboard.keyboard
    ]


def test_username_purchase_button_is_in_main_menu() -> None:
    assert [BTN_BUY_USERNAME] in keyboard_rows(MAIN_MENU_KEYBOARD)


def test_username_purchase_keyboard_has_answers_and_home() -> None:
    assert keyboard_rows(USERNAME_PURCHASE_KEYBOARD) == [
        [BTN_YES, BTN_NO],
        [BTN_HOME],
    ]
    assert keyboard_rows(HOME_KEYBOARD) == [[BTN_HOME]]
