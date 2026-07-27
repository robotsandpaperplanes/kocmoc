from __future__ import annotations

import logging
from datetime import datetime
from html import escape

from aiogram import Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .business import (
    normalize_public_id,
    sailing_result,
    truncate_comment,
    utc_time_text,
)
from .config import Settings
from .db import Database
from .keyboards import (
    ADMIN_CERTIFICATE_ACTIVE_KEYBOARD,
    ADMIN_CERTIFICATE_REDEEMED_KEYBOARD,
    ADMIN_MENU_KEYBOARD,
    ADMIN_REDEEM_CONFIRM_KEYBOARD,
    ADMIN_SEARCH_KEYBOARD,
    AMOUNT_KEYBOARD,
    AMOUNT_LABELS,
    BACK_KEYBOARD,
    BTN_ACTIVE_CERTIFICATES,
    BTN_BACK,
    BTN_BUY_CERTIFICATE,
    BTN_BUY_USERNAME,
    BTN_CANCEL,
    BTN_CERTIFICATE,
    BTN_CONFIRM_REDEEM,
    BTN_FIND_CERTIFICATE,
    BTN_HOME,
    BTN_MY_CERTIFICATES,
    BTN_NO,
    BTN_REDEEM,
    BTN_REDEEMED_CERTIFICATES,
    BTN_SAIL,
    BTN_SKIP_COMMENT,
    BTN_TIME,
    BTN_YES,
    CERTIFICATE_CARD_KEYBOARD,
    COMMENT_KEYBOARD,
    HOME_KEYBOARD,
    MAIN_MENU_KEYBOARD,
    MY_CERTIFICATES_KEYBOARD,
    USERNAME_PURCHASE_KEYBOARD,
    certificate_list_inline,
    payment_keyboard,
)
from .models import Certificate, CertificateStatus
from .states import AdminFlow, CertificateFlow, UsernamePurchaseFlow


logger = logging.getLogger(__name__)
router = Router()

WELCOME_TEXT = (
    "Я верю, что многие из вас...\n\n"
    "Выбирайте, куда отправимся дальше."
)
ALLOWED_AMOUNTS = set(AMOUNT_LABELS.values())
STATUS_LABELS = {
    CertificateStatus.ACTIVE: "Активен",
    CertificateStatus.REDEEMED: "Погашен",
    CertificateStatus.CANCELLED: "Отменён",
    CertificateStatus.EXPIRED: "Истёк",
}


def setup_handlers(*, db: Database, settings: Settings) -> Dispatcher:
    dp = Dispatcher()
    dp["db"] = db
    dp["settings"] = settings
    dp.include_router(router)
    return dp


def telegram_username(message: Message) -> str | None:
    return message.from_user.username if message.from_user else None


def format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    return timestamp.strftime("%d.%m.%Y, %H:%M UTC")


def certificate_card_text(
    certificate: Certificate,
    *,
    admin: bool = False,
) -> str:
    lines = [
        f"Сертификат <code>{certificate.public_id}</code>",
        "",
        f"Номинал: <b>{certificate.amount} 🍅</b>",
        f"Статус: <b>{STATUS_LABELS[certificate.status]}</b>",
        f"Дата покупки: {format_timestamp(certificate.created_at)}",
    ]
    if certificate.comment:
        lines.extend(
            [
                "",
                "Комментарий:",
                escape(truncate_comment(certificate.comment)),
            ]
        )
    if certificate.status == CertificateStatus.REDEEMED:
        lines.extend(
            [
                "",
                f"Дата погашения: {format_timestamp(certificate.redeemed_at)}",
            ]
        )
        if admin and certificate.redeemed_by_telegram_id is not None:
            lines.append(
                "Погасил администратор: "
                f"<code>{certificate.redeemed_by_telegram_id}</code>"
            )
            if certificate.redeemed_by_username:
                lines.append(
                    f"Username администратора: @{escape(certificate.redeemed_by_username)}"
                )
    if admin:
        lines.extend(
            [
                "",
                "Покупатель:",
                f"Telegram ID: <code>{certificate.buyer_telegram_id}</code>",
                (
                    f"Username: @{escape(certificate.buyer_username)}"
                    if certificate.buyer_username
                    else "Username: —"
                ),
            ]
        )
    return "\n".join(lines)


def issued_certificate_text(certificate: Certificate) -> str:
    lines = [
        "Поехали!",
        "Крышей? Или в Космос? Сам реши или подари другу.",
        "",
        f"Это сообщение — сертификат номиналом {certificate.amount} 🍅.",
        "",
        "ID сертификата:",
        f"<code>{certificate.public_id}</code>",
    ]
    if certificate.comment:
        lines.extend(
            [
                "",
                "Комментарий:",
                escape(truncate_comment(certificate.comment)),
            ]
        )
    return "\n".join(lines)


async def show_main_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(WELCOME_TEXT, reply_markup=MAIN_MENU_KEYBOARD)


async def show_amount_step(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CertificateFlow.choosing_amount)
    await message.answer(
        "Выберите номинал сертификата:",
        reply_markup=AMOUNT_KEYBOARD,
    )


async def show_payment_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = data.get("amount")
    if amount not in ALLOWED_AMOUNTS:
        await show_amount_step(message, state)
        return

    comment = data.get("comment")
    comment_line = (
        f"\n\nКомментарий:\n{escape(truncate_comment(comment))}"
        if comment
        else ""
    )
    await state.set_state(CertificateFlow.waiting_for_payment)
    await message.answer(
        f"Сертификат номиналом <b>{amount} 🍅</b> готов к тестовой оплате."
        f"{comment_line}\n\n"
        "Сейчас деньги не списываются: кнопка сразу создаст сертификат.",
        parse_mode=ParseMode.HTML,
        reply_markup=payment_keyboard(amount),
    )


async def show_my_certificates(
    message: Message,
    state: FSMContext,
    db: Database,
) -> None:
    await state.clear()
    certificates = await db.list_certificates_for_buyer(message.from_user.id)
    if not certificates:
        await message.answer(
            "У тебя пока нет сертификата. 😡 Ты можешь приобрести его "
            "для себя или для друга прямо сейчас.",
            reply_markup=MY_CERTIFICATES_KEYBOARD,
        )
        return

    rows = ["<b>Твои сертификаты</b>", ""]
    for certificate in certificates:
        suffix = (
            ""
            if certificate.status == CertificateStatus.ACTIVE
            else f" — {STATUS_LABELS[certificate.status].lower()}"
        )
        rows.append(
            f"<code>{certificate.public_id}</code> — {certificate.amount} 🍅{suffix}"
        )

    await message.answer(
        "\n".join(rows),
        parse_mode=ParseMode.HTML,
        reply_markup=certificate_list_inline(
            [(certificate.public_id, certificate.amount) for certificate in certificates]
        ),
    )
    await message.answer(
        "Нажми на ID выше, чтобы открыть карточку сертификата.",
        reply_markup=MY_CERTIFICATES_KEYBOARD,
    )


async def show_admin_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "<b>Администрирование сертификатов</b>\n\n"
        "Здесь можно найти сертификат по ID и погасить его.",
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_MENU_KEYBOARD,
    )


async def show_admin_certificate(
    message: Message,
    state: FSMContext,
    certificate: Certificate,
) -> None:
    await state.set_state(AdminFlow.viewing_certificate)
    await state.update_data(admin_public_id=certificate.public_id)
    keyboard = (
        ADMIN_CERTIFICATE_ACTIVE_KEYBOARD
        if certificate.status == CertificateStatus.ACTIVE
        else ADMIN_CERTIFICATE_REDEEMED_KEYBOARD
    )
    await message.answer(
        certificate_card_text(certificate, admin=True),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


def is_admin(message: Message, settings: Settings) -> bool:
    return bool(
        message.from_user
        and settings.is_admin(message.from_user.id)
    )


async def reject_admin_access(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(
        "У вас нет доступа к администрированию.",
        reply_markup=MAIN_MENU_KEYBOARD,
    )


@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
    command: CommandObject,
    db: Database,
    settings: Settings,
) -> None:
    await state.clear()
    payload = (command.args or "").strip()
    if payload.startswith("cert_"):
        certificate = await db.get_certificate_by_token(
            payload.removeprefix("cert_")
        )
        if not certificate:
            await message.answer(
                "Сертификат не найден или ссылка недействительна.",
                reply_markup=MAIN_MENU_KEYBOARD,
            )
            return
        if is_admin(message, settings):
            await show_admin_certificate(message, state, certificate)
        else:
            await message.answer(
                certificate_card_text(certificate),
                parse_mode=ParseMode.HTML,
                reply_markup=CERTIFICATE_CARD_KEYBOARD,
            )
        return

    await show_main_menu(message, state)


@router.message(Command("myid"))
async def my_id(message: Message) -> None:
    await message.answer(
        f"Ваш Telegram ID: <code>{message.from_user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("admin"))
async def admin_command(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    await show_admin_menu(message, state)


@router.message(F.text == BTN_HOME)
async def home(message: Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(F.text == BTN_TIME)
async def current_time(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(utc_time_text(), reply_markup=BACK_KEYBOARD)


@router.message(F.text == BTN_SAIL)
async def sail(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(sailing_result(), reply_markup=BACK_KEYBOARD)


@router.message(F.text == BTN_BUY_USERNAME)
async def username_purchase_start(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await state.set_state(UsernamePurchaseFlow.choosing_answer)
    await message.answer(
        "Хотите приобрести юзернейм @kocmoc через платформу Fragments?",
        reply_markup=USERNAME_PURCHASE_KEYBOARD,
    )


@router.message(UsernamePurchaseFlow.choosing_answer, F.text == BTN_YES)
async def username_purchase_yes(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer(
        "Пошёл на хуй",
        reply_markup=HOME_KEYBOARD,
    )


@router.message(UsernamePurchaseFlow.choosing_answer, F.text == BTN_NO)
async def username_purchase_no(
    message: Message,
    state: FSMContext,
) -> None:
    await state.clear()
    await message.answer("🤝", reply_markup=HOME_KEYBOARD)


@router.message(F.text.in_({BTN_CERTIFICATE, BTN_BUY_CERTIFICATE}))
async def certificate_start(message: Message, state: FSMContext) -> None:
    await show_amount_step(message, state)


@router.message(F.text == BTN_MY_CERTIFICATES)
async def my_certificates(
    message: Message,
    state: FSMContext,
    db: Database,
) -> None:
    await show_my_certificates(message, state, db)


@router.callback_query(F.data.startswith("certificate:"))
async def certificate_callback(
    callback: CallbackQuery,
    db: Database,
    settings: Settings,
) -> None:
    public_id = callback.data.removeprefix("certificate:")
    certificate = await db.get_certificate_by_public_id(public_id)
    if not certificate:
        await callback.answer("Сертификат не найден.", show_alert=True)
        return
    if (
        certificate.buyer_telegram_id != callback.from_user.id
        and not settings.is_admin(callback.from_user.id)
    ):
        await callback.answer("Этот сертификат вам недоступен.", show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await callback.message.answer(
            certificate_card_text(
                certificate,
                admin=settings.is_admin(callback.from_user.id),
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=CERTIFICATE_CARD_KEYBOARD,
        )


@router.message(CertificateFlow.choosing_amount, F.text.in_(set(AMOUNT_LABELS)))
async def choose_amount(message: Message, state: FSMContext) -> None:
    amount = AMOUNT_LABELS[message.text]
    await state.update_data(amount=amount, comment=None)
    await state.set_state(CertificateFlow.waiting_for_comment)
    await message.answer(
        "Вы можете оставить комментарий для студии или для получателя сертификата.",
        reply_markup=COMMENT_KEYBOARD,
    )


@router.message(CertificateFlow.choosing_amount, F.text == BTN_BACK)
async def amount_back(message: Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(
    CertificateFlow.waiting_for_comment,
    F.text == BTN_SKIP_COMMENT,
)
async def skip_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=None)
    await show_payment_step(message, state)


@router.message(CertificateFlow.waiting_for_comment, F.text == BTN_BACK)
@router.message(CertificateFlow.waiting_for_payment, F.text == BTN_BACK)
async def purchase_back_to_amount(
    message: Message,
    state: FSMContext,
) -> None:
    await show_amount_step(message, state)


@router.message(CertificateFlow.waiting_for_comment, F.text)
async def receive_comment(message: Message, state: FSMContext) -> None:
    comment = message.text.strip()
    if not comment:
        await message.answer(
            "Комментарий пуст. Введите текст или выберите «🙊 Без комментариев».",
            reply_markup=COMMENT_KEYBOARD,
        )
        return
    await state.update_data(comment=comment)
    await show_payment_step(message, state)


@router.message(
    CertificateFlow.waiting_for_payment,
    F.text.startswith("Оплатить "),
)
async def test_payment(
    message: Message,
    state: FSMContext,
    db: Database,
) -> None:
    data = await state.get_data()
    amount = data.get("amount")
    comment = data.get("comment")
    expected_button = f"Оплатить {amount} 🍅"
    if amount not in ALLOWED_AMOUNTS or message.text != expected_button:
        await show_amount_step(message, state)
        return

    # Clear first: a repeated tap no longer matches this FSM state.
    await state.clear()
    try:
        certificate = await db.issue_test_certificate(
            telegram_user_id=message.from_user.id,
            buyer_username=telegram_username(message),
            chat_id=message.chat.id,
            amount=amount,
            comment=comment,
        )
    except Exception:
        logger.exception("Could not issue test certificate")
        await message.answer(
            "Не удалось создать сертификат. Попробуйте ещё раз.",
            reply_markup=MAIN_MENU_KEYBOARD,
        )
        return

    await message.answer(
        issued_certificate_text(certificate),
        parse_mode=ParseMode.HTML,
        reply_markup=HOME_KEYBOARD,
    )


@router.message(F.text == BTN_FIND_CERTIFICATE)
async def admin_find_certificate(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    await state.set_state(AdminFlow.waiting_for_certificate_id)
    await message.answer(
        "Введите ID сертификата в формате <code>xxxx-xxxx</code>.",
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_SEARCH_KEYBOARD,
    )


@router.message(
    F.text.in_({BTN_ACTIVE_CERTIFICATES, BTN_REDEEMED_CERTIFICATES})
)
async def admin_certificate_list(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    await state.clear()
    status = (
        CertificateStatus.ACTIVE
        if message.text == BTN_ACTIVE_CERTIFICATES
        else CertificateStatus.REDEEMED
    )
    certificates = await db.list_certificates_by_status(status, limit=20)
    if not certificates:
        await message.answer(
            f"Сертификатов со статусом «{STATUS_LABELS[status]}» пока нет.",
            reply_markup=ADMIN_MENU_KEYBOARD,
        )
        return
    rows = [f"<b>{STATUS_LABELS[status]} — последние 20</b>", ""]
    rows.extend(
        f"<code>{item.public_id}</code> — {item.amount} 🍅"
        for item in certificates
    )
    rows.extend(["", "Чтобы открыть карточку, выберите поиск и введите ID."])
    await message.answer(
        "\n".join(rows),
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_MENU_KEYBOARD,
    )


@router.message(AdminFlow.waiting_for_certificate_id, F.text == BTN_BACK)
@router.message(AdminFlow.viewing_certificate, F.text == BTN_BACK)
async def admin_back(
    message: Message,
    state: FSMContext,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    await show_admin_menu(message, state)


@router.message(AdminFlow.waiting_for_certificate_id, F.text)
async def admin_search_input(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    public_id = normalize_public_id(message.text)
    if not public_id:
        await message.answer(
            "Не удалось распознать ID сертификата. "
            "Используйте формат <code>xxxx-xxxx</code>.",
            parse_mode=ParseMode.HTML,
            reply_markup=ADMIN_SEARCH_KEYBOARD,
        )
        return
    certificate = await db.get_certificate_by_public_id(public_id)
    if not certificate:
        await message.answer(
            f"Сертификат <code>{public_id}</code> не найден.",
            parse_mode=ParseMode.HTML,
            reply_markup=ADMIN_SEARCH_KEYBOARD,
        )
        return
    await show_admin_certificate(message, state, certificate)


@router.message(AdminFlow.viewing_certificate, F.text == BTN_REDEEM)
async def admin_redeem_prompt(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    public_id = (await state.get_data()).get("admin_public_id")
    certificate = (
        await db.get_certificate_by_public_id(public_id)
        if public_id
        else None
    )
    if not certificate:
        await show_admin_menu(message, state)
        return
    if certificate.status != CertificateStatus.ACTIVE:
        await show_admin_certificate(message, state, certificate)
        return

    await state.set_state(AdminFlow.confirming_redeem)
    await message.answer(
        f"Погасить сертификат <code>{certificate.public_id}</code> "
        f"номиналом <b>{certificate.amount} 🍅</b>?\n\n"
        "После подтверждения действие нельзя будет отменить через интерфейс бота.",
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_REDEEM_CONFIRM_KEYBOARD,
    )


@router.message(AdminFlow.confirming_redeem, F.text == BTN_CANCEL)
async def admin_redeem_cancel(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    public_id = (await state.get_data()).get("admin_public_id")
    certificate = (
        await db.get_certificate_by_public_id(public_id)
        if public_id
        else None
    )
    if certificate:
        await show_admin_certificate(message, state, certificate)
    else:
        await show_admin_menu(message, state)


@router.message(
    AdminFlow.confirming_redeem,
    F.text == BTN_CONFIRM_REDEEM,
)
async def admin_redeem_confirm(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not is_admin(message, settings):
        await reject_admin_access(message, state)
        return
    public_id = (await state.get_data()).get("admin_public_id")
    if not public_id:
        await show_admin_menu(message, state)
        return

    certificate, changed = await db.redeem_certificate_by_public_id(
        public_id=public_id,
        redeemed_by_telegram_id=message.from_user.id,
        redeemed_by_username=telegram_username(message),
    )
    if not certificate:
        await message.answer(
            f"Сертификат <code>{public_id}</code> не найден.",
            parse_mode=ParseMode.HTML,
            reply_markup=ADMIN_MENU_KEYBOARD,
        )
        await state.clear()
        return

    await state.set_state(AdminFlow.viewing_certificate)
    await state.update_data(admin_public_id=certificate.public_id)
    heading = (
        f"Сертификат <code>{certificate.public_id}</code> погашен."
        if changed
        else f"Сертификат <code>{certificate.public_id}</code> уже был погашен."
    )
    await message.answer(
        f"{heading}\n\n{certificate_card_text(certificate, admin=True)}",
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_CERTIFICATE_REDEEMED_KEYBOARD,
    )


@router.message(F.text == BTN_BACK)
async def back_to_main_menu(message: Message, state: FSMContext) -> None:
    await show_main_menu(message, state)


@router.message(CertificateFlow.choosing_amount)
async def invalid_amount(message: Message) -> None:
    await message.answer(
        "Выберите номинал кнопкой ниже.",
        reply_markup=AMOUNT_KEYBOARD,
    )


@router.message(CertificateFlow.waiting_for_payment)
async def invalid_payment_step(
    message: Message,
    state: FSMContext,
) -> None:
    amount = (await state.get_data()).get("amount")
    if amount not in ALLOWED_AMOUNTS:
        await show_amount_step(message, state)
        return
    await message.answer(
        f"Нажмите «Оплатить {amount} 🍅» или вернитесь назад.",
        reply_markup=payment_keyboard(amount),
    )


@router.message(UsernamePurchaseFlow.choosing_answer)
async def invalid_username_purchase_answer(message: Message) -> None:
    await message.answer(
        "Выберите «Да» или «Нет».",
        reply_markup=USERNAME_PURCHASE_KEYBOARD,
    )


@router.message(AdminFlow.confirming_redeem)
async def invalid_redeem_confirmation(message: Message) -> None:
    await message.answer(
        "Подтвердите или отмените погашение кнопкой ниже.",
        reply_markup=ADMIN_REDEEM_CONFIRM_KEYBOARD,
    )
