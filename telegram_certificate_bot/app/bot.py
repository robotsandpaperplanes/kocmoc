from __future__ import annotations

import logging
import secrets
from datetime import datetime
from html import escape

from aiogram import Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message, ReplyKeyboardRemove
from aiogram.utils.deep_linking import create_start_link

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
    BTN_ADMIN,
    BTN_BACK,
    BTN_CANCEL,
    BTN_CERTIFICATE,
    BTN_CONFIRM_REDEEM,
    BTN_EDIT_COMMENT,
    BTN_FIND_CERTIFICATE,
    BTN_MENU_1,
    BTN_MENU_2,
    BTN_PAY,
    BTN_RECENT_ACTIVE,
    BTN_REDEEM,
    BTN_SAVE_COMMENT,
    BTN_SKIP,
    COMMENT_CONFIRM_KEYBOARD,
    COMMENT_ENTRY_KEYBOARD,
    PAYMENT_KEYBOARD,
    main_menu,
)
from .models import Certificate, CertificateStatus
from .qr import create_certificate_png
from .states import AdminFlow, CertificateFlow

logger = logging.getLogger(__name__)
router = Router()

ALLOWED_AMOUNTS = set(AMOUNT_LABELS.values())
MAX_COMMENT_LENGTH = 500


def format_rubles(kopecks: int) -> str:
    return f"{kopecks // 100:,}".replace(",", " ") + " ₽"


def format_timestamp(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return value
    return dt.strftime("%d.%m.%Y %H:%M UTC")


def setup_handlers(*, db: Database, settings: Settings) -> Dispatcher:
    dp = Dispatcher()
    dp["db"] = db
    dp["settings"] = settings
    dp.include_router(router)
    return dp


def menu_for(user_id: int, settings: Settings):
    return main_menu(is_admin=settings.is_admin(user_id))


def certificate_text(certificate: Certificate, *, include_secret_warning: bool = False) -> str:
    status = "Активен" if certificate.status == CertificateStatus.ACTIVE else "Погашен"
    comment = escape(certificate.comment) if certificate.comment else "—"
    lines = [
        f"<b>Сертификат</b>",
        "",
        f"ID: <code>{certificate.id}</code>",
        f"Короткий код: <code>{certificate.public_code}</code>",
        f"Номинал: <b>{format_rubles(certificate.amount_kopecks)}</b>",
        f"Комментарий: {comment}",
        f"Статус: <b>{status}</b>",
        f"Создан: {format_timestamp(certificate.created_at)}",
    ]
    if certificate.status == CertificateStatus.REDEEMED:
        lines.append(f"Погашен: {format_timestamp(certificate.redeemed_at)}")
        if certificate.redeemed_by:
            lines.append(f"Telegram ID сотрудника: <code>{certificate.redeemed_by}</code>")
    if include_secret_warning:
        lines.extend(["", "QR-код является ключом сертификата. Не публикуйте его открыто."])
    return "\n".join(lines)


async def show_admin_certificate(
    message: Message,
    state: FSMContext,
    certificate: Certificate,
) -> None:
    await state.set_state(AdminFlow.viewing_certificate)
    await state.update_data(admin_certificate_id=certificate.id)
    keyboard = (
        ADMIN_CERTIFICATE_ACTIVE_KEYBOARD
        if certificate.status == CertificateStatus.ACTIVE
        else ADMIN_CERTIFICATE_REDEEMED_KEYBOARD
    )
    await message.answer(
        certificate_text(certificate),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )


async def show_admin_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(
        "<b>Администрирование сертификатов</b>\n\n"
        "Можно найти сертификат по UUID или короткому коду, посмотреть последние активные и погасить сертификат.",
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_MENU_KEYBOARD,
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
        token = payload.removeprefix("cert_")
        certificate = await db.get_certificate_by_token(token)
        if not certificate:
            await message.answer(
                "Сертификат не найден или QR-код недействителен.",
                reply_markup=menu_for(message.from_user.id, settings),
            )
            return

        if settings.is_admin(message.from_user.id):
            await show_admin_certificate(message, state, certificate)
            return

        await message.answer(
            certificate_text(certificate),
            parse_mode=ParseMode.HTML,
            reply_markup=menu_for(message.from_user.id, settings),
        )
        return

    await message.answer(
        "Выберите раздел:",
        reply_markup=menu_for(message.from_user.id, settings),
    )


@router.message(Command("myid"))
async def my_id(message: Message, settings: Settings) -> None:
    admin_note = "\nАдминистратор: да" if settings.is_admin(message.from_user.id) else ""
    await message.answer(
        f"Ваш Telegram ID: <code>{message.from_user.id}</code>{admin_note}",
        parse_mode=ParseMode.HTML,
        reply_markup=menu_for(message.from_user.id, settings),
    )


@router.message(F.text.in_({BTN_MENU_1, BTN_MENU_2}))
async def empty_menu_item(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(
        "Раздел пока пуст.",
        reply_markup=menu_for(message.from_user.id, settings),
    )


@router.message(F.text == BTN_CERTIFICATE)
async def certificate_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(CertificateFlow.choosing_amount)
    await message.answer(
        "Выберите номинал сертификата:",
        reply_markup=AMOUNT_KEYBOARD,
    )


@router.message(CertificateFlow.choosing_amount, F.text.in_(set(AMOUNT_LABELS)))
async def choose_amount(message: Message, state: FSMContext) -> None:
    amount = AMOUNT_LABELS[message.text]
    await state.set_state(CertificateFlow.waiting_for_comment)
    await state.update_data(amount_kopecks=amount, draft_comment=None, comment=None)
    await message.answer(
        f"Номинал: <b>{format_rubles(amount)}</b>\n\n"
        "Введите комментарий для сертификата или нажмите «Пропустить».\n"
        f"Максимальная длина — {MAX_COMMENT_LENGTH} символов.",
        parse_mode=ParseMode.HTML,
        reply_markup=COMMENT_ENTRY_KEYBOARD,
    )


@router.message(CertificateFlow.choosing_amount, F.text == BTN_CANCEL)
@router.message(CertificateFlow.waiting_for_comment, F.text == BTN_CANCEL)
@router.message(CertificateFlow.confirming_comment, F.text == BTN_CANCEL)
@router.message(CertificateFlow.waiting_for_payment, F.text == BTN_CANCEL)
async def cancel_certificate(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(
        "Оформление сертификата отменено.",
        reply_markup=menu_for(message.from_user.id, settings),
    )


@router.message(CertificateFlow.waiting_for_comment, F.text == BTN_SKIP)
async def skip_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=None, draft_comment=None)
    await show_payment_step(message, state)


@router.message(CertificateFlow.waiting_for_comment, F.text)
async def receive_comment(message: Message, state: FSMContext) -> None:
    comment = message.text.strip()
    if not comment:
        await message.answer(
            "Комментарий не может быть пустым.",
            reply_markup=COMMENT_ENTRY_KEYBOARD,
        )
        return
    if len(comment) > MAX_COMMENT_LENGTH:
        await message.answer(
            f"Комментарий слишком длинный: {len(comment)} символов. "
            f"Допустимо не более {MAX_COMMENT_LENGTH}.",
            reply_markup=COMMENT_ENTRY_KEYBOARD,
        )
        return

    await state.update_data(draft_comment=comment)
    await state.set_state(CertificateFlow.confirming_comment)
    await message.answer(
        "Комментарий:\n\n"
        f"<blockquote>{escape(comment)}</blockquote>\n"
        "Сохранить его в сертификате?",
        parse_mode=ParseMode.HTML,
        reply_markup=COMMENT_CONFIRM_KEYBOARD,
    )


@router.message(CertificateFlow.confirming_comment, F.text == BTN_SAVE_COMMENT)
async def save_comment(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    comment = data.get("draft_comment")
    if not comment:
        await state.set_state(CertificateFlow.waiting_for_comment)
        await message.answer(
            "Сначала введите комментарий.",
            reply_markup=COMMENT_ENTRY_KEYBOARD,
        )
        return
    await state.update_data(comment=comment)
    await show_payment_step(message, state)


@router.message(CertificateFlow.confirming_comment, F.text == BTN_SKIP)
async def skip_confirmed_comment(message: Message, state: FSMContext) -> None:
    await state.update_data(comment=None)
    await show_payment_step(message, state)


@router.message(CertificateFlow.confirming_comment, F.text == BTN_EDIT_COMMENT)
@router.message(CertificateFlow.waiting_for_payment, F.text == BTN_EDIT_COMMENT)
async def edit_comment(message: Message, state: FSMContext) -> None:
    await state.set_state(CertificateFlow.waiting_for_comment)
    await message.answer(
        "Введите новый комментарий или нажмите «Пропустить».",
        reply_markup=COMMENT_ENTRY_KEYBOARD,
    )


async def show_payment_step(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    amount = data.get("amount_kopecks")
    if amount not in ALLOWED_AMOUNTS:
        await state.clear()
        await message.answer("Сессия устарела. Начните оформление заново.")
        return

    comment = data.get("comment")
    comment_text = escape(comment) if comment else "без комментария"
    await state.set_state(CertificateFlow.waiting_for_payment)
    await message.answer(
        "<b>Проверьте сертификат</b>\n\n"
        f"Номинал: <b>{format_rubles(amount)}</b>\n"
        f"Комментарий: {comment_text}\n\n"
        "Сейчас включён тестовый режим: кнопка «Оплатить» не списывает деньги, "
        "а сразу выпускает случайный сертификат.",
        parse_mode=ParseMode.HTML,
        reply_markup=PAYMENT_KEYBOARD,
    )


@router.message(CertificateFlow.waiting_for_payment, F.text == BTN_PAY)
async def test_payment(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    data = await state.get_data()
    amount = data.get("amount_kopecks")
    comment = data.get("comment")
    if amount not in ALLOWED_AMOUNTS:
        await state.clear()
        await message.answer(
            "Сессия устарела. Начните оформление заново.",
            reply_markup=menu_for(message.from_user.id, settings),
        )
        return

    # Убираем кнопку «Оплатить» сразу, чтобы двойное нажатие не создало два сертификата.
    await state.clear()
    await message.answer("Создаю сертификат…", reply_markup=ReplyKeyboardRemove())

    try:
        certificate = await db.issue_test_certificate(
            telegram_user_id=message.from_user.id,
            chat_id=message.chat.id,
            amount_kopecks=amount,
            comment=comment,
            redeem_token=secrets.token_urlsafe(24),
        )
        deep_link = await create_start_link(
            message.bot,
            f"cert_{certificate.redeem_token}",
            encode=False,
        )
        image_buffer = create_certificate_png(
            certificate_id=certificate.id,
            amount_text=format_rubles(certificate.amount_kopecks),
            comment=certificate.comment,
            qr_data=deep_link,
        )
        image_file = BufferedInputFile(
            image_buffer.read(),
            filename=f"certificate-{certificate.id}.png",
        )
    except Exception:
        logger.exception("Could not issue test certificate")
        await message.answer(
            "Не удалось создать сертификат. Попробуйте ещё раз.",
            reply_markup=menu_for(message.from_user.id, settings),
        )
        return

    await message.answer_photo(
        photo=image_file,
        caption=(
            "<b>Тестовый сертификат создан</b>\n\n"
            f"ID: <code>{certificate.id}</code>\n"
            f"Номинал: <b>{format_rubles(certificate.amount_kopecks)}</b>\n\n"
            "Деньги не списывались. QR открывает сертификат в этом Telegram-боте."
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=menu_for(message.from_user.id, settings),
    )


@router.message(F.text == BTN_ADMIN)
async def admin_start(message: Message, state: FSMContext, settings: Settings) -> None:
    if not settings.is_admin(message.from_user.id):
        await state.clear()
        await message.answer(
            "У вас нет доступа к администрированию.",
            reply_markup=menu_for(message.from_user.id, settings),
        )
        return
    await show_admin_menu(message, state)


@router.message(F.text == BTN_FIND_CERTIFICATE)
async def admin_find_certificate(message: Message, state: FSMContext, settings: Settings) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    await state.set_state(AdminFlow.waiting_for_certificate_id)
    await message.answer(
        "Введите полный UUID сертификата или короткий код вида <code>CERT-…</code>.",
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_SEARCH_KEYBOARD,
    )


@router.message(AdminFlow.waiting_for_certificate_id, F.text == BTN_BACK)
@router.message(AdminFlow.viewing_certificate, F.text == BTN_BACK)
async def admin_back(message: Message, state: FSMContext, settings: Settings) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    await show_admin_menu(message, state)


@router.message(AdminFlow.waiting_for_certificate_id, F.text)
async def admin_search_input(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    certificate = await db.get_certificate_by_id_or_code(message.text)
    if not certificate:
        await message.answer(
            "Сертификат не найден. Проверьте ID и попробуйте ещё раз.",
            reply_markup=ADMIN_SEARCH_KEYBOARD,
        )
        return
    await show_admin_certificate(message, state, certificate)


@router.message(F.text == BTN_RECENT_ACTIVE)
async def admin_recent_active(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    await state.clear()
    certificates = await db.list_recent_active_certificates(limit=10)
    if not certificates:
        await message.answer(
            "Активных сертификатов пока нет.",
            reply_markup=ADMIN_MENU_KEYBOARD,
        )
        return

    rows = ["<b>Последние активные сертификаты</b>", ""]
    for index, certificate in enumerate(certificates, start=1):
        rows.extend(
            [
                f"{index}. <code>{certificate.public_code}</code>",
                f"   {format_rubles(certificate.amount_kopecks)}",
                f"   ID: <code>{certificate.id}</code>",
                "",
            ]
        )
    rows.append("Для погашения выберите «Найти сертификат» и вставьте его ID.")
    await message.answer(
        "\n".join(rows),
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_MENU_KEYBOARD,
    )


@router.message(AdminFlow.viewing_certificate, F.text == BTN_REDEEM)
async def admin_redeem_prompt(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    data = await state.get_data()
    certificate_id = data.get("admin_certificate_id")
    certificate = await db.get_certificate_by_id(certificate_id) if certificate_id else None
    if not certificate:
        await show_admin_menu(message, state)
        return
    if certificate.status != CertificateStatus.ACTIVE:
        await show_admin_certificate(message, state, certificate)
        return

    await state.set_state(AdminFlow.confirming_redeem)
    await message.answer(
        "<b>Погасить сертификат?</b>\n\n"
        f"ID: <code>{certificate.id}</code>\n"
        f"Номинал: <b>{format_rubles(certificate.amount_kopecks)}</b>\n\n"
        "После подтверждения повторное использование будет невозможно.",
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
    if not settings.is_admin(message.from_user.id):
        return
    data = await state.get_data()
    certificate_id = data.get("admin_certificate_id")
    certificate = await db.get_certificate_by_id(certificate_id) if certificate_id else None
    if certificate:
        await show_admin_certificate(message, state, certificate)
    else:
        await show_admin_menu(message, state)


@router.message(AdminFlow.confirming_redeem, F.text == BTN_CONFIRM_REDEEM)
async def admin_redeem_confirm(
    message: Message,
    state: FSMContext,
    db: Database,
    settings: Settings,
) -> None:
    if not settings.is_admin(message.from_user.id):
        return
    data = await state.get_data()
    certificate_id = data.get("admin_certificate_id")
    if not certificate_id:
        await show_admin_menu(message, state)
        return

    certificate, changed = await db.redeem_certificate_by_id(
        certificate_id=certificate_id,
        redeemed_by=message.from_user.id,
    )
    if not certificate:
        await message.answer("Сертификат не найден.", reply_markup=ADMIN_MENU_KEYBOARD)
        await state.clear()
        return

    prefix = "<b>Сертификат погашен</b>" if changed else "<b>Сертификат уже был погашен</b>"
    await state.set_state(AdminFlow.viewing_certificate)
    await state.update_data(admin_certificate_id=certificate.id)
    await message.answer(
        f"{prefix}\n\n{certificate_text(certificate)}",
        parse_mode=ParseMode.HTML,
        reply_markup=ADMIN_CERTIFICATE_REDEEMED_KEYBOARD,
    )


@router.message(F.text == BTN_BACK)
async def back_to_main_menu(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    await message.answer(
        "Главное меню:",
        reply_markup=menu_for(message.from_user.id, settings),
    )


@router.message(CertificateFlow.choosing_amount)
async def invalid_amount(message: Message) -> None:
    await message.answer("Выберите номинал кнопкой ниже.", reply_markup=AMOUNT_KEYBOARD)


@router.message(CertificateFlow.confirming_comment)
async def invalid_comment_confirmation(message: Message) -> None:
    await message.answer(
        "Выберите действие кнопкой ниже.",
        reply_markup=COMMENT_CONFIRM_KEYBOARD,
    )


@router.message(CertificateFlow.waiting_for_payment)
async def invalid_payment_step(message: Message) -> None:
    await message.answer(
        "Нажмите «Оплатить», измените комментарий или отмените оформление.",
        reply_markup=PAYMENT_KEYBOARD,
    )


@router.message(AdminFlow.confirming_redeem)
async def invalid_redeem_confirmation(message: Message) -> None:
    await message.answer(
        "Подтвердите или отмените погашение кнопкой ниже.",
        reply_markup=ADMIN_REDEEM_CONFIRM_KEYBOARD,
    )
