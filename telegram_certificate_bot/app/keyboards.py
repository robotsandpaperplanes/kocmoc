from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


BTN_TIME = "🕰️ Который час?"
BTN_SAIL = "⚓️ Плыть"
BTN_CERTIFICATE = "🎁 Сертификат"
BTN_MY_CERTIFICATES = "📦 Мои сертификаты"
BTN_BUY_CERTIFICATE = "🎁 Купить сертификат"
BTN_BACK = "⬅️ Назад"
BTN_HOME = "⬅️ В начало"
BTN_SKIP_COMMENT = "🙊 Без комментариев"

BTN_FIND_CERTIFICATE = "🔎 Найти сертификат"
BTN_ACTIVE_CERTIFICATES = "📦 Активные сертификаты"
BTN_REDEEMED_CERTIFICATES = "✅ Погашенные сертификаты"
BTN_REDEEM = "✅ Погасить сертификат"
BTN_CONFIRM_REDEEM = "✅ Да, погасить"
BTN_CANCEL = "❌ Отмена"

AMOUNT_LABELS = {
    "5 🍅": 5,
    "10 🍅": 10,
    "15 🍅": 15,
    "20 🍅": 20,
}


def _keyboard(
    rows: list[list[str]],
    placeholder: str | None = None,
) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
        input_field_placeholder=placeholder,
    )


MAIN_MENU_KEYBOARD = _keyboard(
    [
        [BTN_TIME, BTN_SAIL],
        [BTN_CERTIFICATE, BTN_MY_CERTIFICATES],
    ],
    "Выберите раздел",
)

BACK_KEYBOARD = _keyboard([[BTN_BACK]])

AMOUNT_KEYBOARD = _keyboard(
    [
        ["5 🍅", "10 🍅"],
        ["15 🍅", "20 🍅"],
        [BTN_BACK],
    ],
    "Выберите номинал",
)

COMMENT_KEYBOARD = _keyboard(
    [[BTN_SKIP_COMMENT], [BTN_BACK]],
    "Введите комментарий",
)


def payment_keyboard(amount: int) -> ReplyKeyboardMarkup:
    return _keyboard(
        [[f"Оплатить {amount} 🍅"], [BTN_BACK]],
        "Подтвердите тестовую оплату",
    )


HOME_KEYBOARD = _keyboard([[BTN_HOME]])

MY_CERTIFICATES_KEYBOARD = _keyboard(
    [[BTN_BUY_CERTIFICATE], [BTN_HOME]],
)

CERTIFICATE_CARD_KEYBOARD = _keyboard(
    [[BTN_MY_CERTIFICATES], [BTN_HOME]],
)

ADMIN_MENU_KEYBOARD = _keyboard(
    [
        [BTN_FIND_CERTIFICATE],
        [BTN_ACTIVE_CERTIFICATES],
        [BTN_REDEEMED_CERTIFICATES],
        [BTN_HOME],
    ],
    "Выберите действие",
)

ADMIN_SEARCH_KEYBOARD = _keyboard([[BTN_BACK]], "Введите xxxx-xxxx")

ADMIN_CERTIFICATE_ACTIVE_KEYBOARD = _keyboard(
    [[BTN_REDEEM], [BTN_BACK]],
)

ADMIN_CERTIFICATE_REDEEMED_KEYBOARD = _keyboard([[BTN_BACK]])

ADMIN_REDEEM_CONFIRM_KEYBOARD = _keyboard(
    [[BTN_CONFIRM_REDEEM], [BTN_CANCEL]],
)


def certificate_list_inline(
    certificates: list[tuple[str, int]],
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{public_id} — {amount} 🍅",
                    callback_data=f"certificate:{public_id}",
                )
            ]
            for public_id, amount in certificates
        ]
    )
