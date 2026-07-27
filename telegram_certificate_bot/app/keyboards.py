from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


BTN_MENU_1 = "menu_item_1"
BTN_MENU_2 = "menu_item_2"
BTN_CERTIFICATE = "Сертификат"
BTN_ADMIN = "Админка"
BTN_BACK = "Назад"
BTN_CANCEL = "Отмена"
BTN_SKIP = "Пропустить"
BTN_SAVE_COMMENT = "Сохранить комментарий"
BTN_EDIT_COMMENT = "Изменить комментарий"
BTN_PAY = "Оплатить"
BTN_FIND_CERTIFICATE = "Найти сертификат"
BTN_RECENT_ACTIVE = "Последние активные"
BTN_REDEEM = "Погасить сертификат"
BTN_CONFIRM_REDEEM = "Да, погасить"

AMOUNT_LABELS = {
    "5 000 ₽": 500_000,
    "10 000 ₽": 1_000_000,
    "20 000 ₽": 2_000_000,
}


def _keyboard(rows: list[list[str]], placeholder: str | None = None) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
        input_field_placeholder=placeholder,
    )


def main_menu(*, is_admin: bool) -> ReplyKeyboardMarkup:
    rows = [
        [BTN_MENU_1, BTN_MENU_2],
        [BTN_CERTIFICATE],
    ]
    if is_admin:
        rows.append([BTN_ADMIN])
    return _keyboard(rows, "Выберите раздел")


AMOUNT_KEYBOARD = _keyboard(
    [["5 000 ₽", "10 000 ₽"], ["20 000 ₽"], [BTN_CANCEL]],
    "Выберите номинал",
)

COMMENT_ENTRY_KEYBOARD = _keyboard(
    [[BTN_SKIP], [BTN_CANCEL]],
    "Введите комментарий",
)

COMMENT_CONFIRM_KEYBOARD = _keyboard(
    [[BTN_SAVE_COMMENT], [BTN_EDIT_COMMENT, BTN_SKIP], [BTN_CANCEL]],
    "Подтвердите комментарий",
)

PAYMENT_KEYBOARD = _keyboard(
    [[BTN_PAY], [BTN_EDIT_COMMENT, BTN_CANCEL]],
    "Подтвердите выпуск сертификата",
)

ADMIN_MENU_KEYBOARD = _keyboard(
    [[BTN_FIND_CERTIFICATE], [BTN_RECENT_ACTIVE], [BTN_BACK]],
    "Выберите действие",
)

ADMIN_SEARCH_KEYBOARD = _keyboard([[BTN_BACK]], "Введите ID сертификата")

ADMIN_CERTIFICATE_ACTIVE_KEYBOARD = _keyboard(
    [[BTN_REDEEM], [BTN_FIND_CERTIFICATE], [BTN_BACK]],
    "Действия с сертификатом",
)

ADMIN_CERTIFICATE_REDEEMED_KEYBOARD = _keyboard(
    [[BTN_FIND_CERTIFICATE], [BTN_BACK]],
    "Сертификат уже погашен",
)

ADMIN_REDEEM_CONFIRM_KEYBOARD = _keyboard(
    [[BTN_CONFIRM_REDEEM], [BTN_CANCEL]],
    "Подтвердите погашение",
)
