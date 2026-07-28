import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot import (
    choose_amount,
    receive_comment,
    test_payment as handle_test_payment,
)
from app.business import format_amount
from app.db import Database
from app.models import CertificateStatus
from app.states import CertificateFlow


def test_purchase_fsm_creates_one_persistent_certificate() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            await db.init()
            storage = MemoryStorage()
            state = FSMContext(
                storage=storage,
                key=StorageKey(bot_id=1, chat_id=202, user_id=101),
            )
            message = SimpleNamespace(
                text=format_amount(10_000),
                from_user=SimpleNamespace(id=101, username="buyer"),
                chat=SimpleNamespace(id=202),
                answer=AsyncMock(),
            )

            await state.set_state(CertificateFlow.choosing_amount)
            await choose_amount(message, state)
            assert await state.get_state() == CertificateFlow.waiting_for_comment

            message.text = "Для друга"
            await receive_comment(message, state)
            assert await state.get_state() == CertificateFlow.waiting_for_payment

            message.text = f"Оплатить {format_amount(10_000)}"
            await handle_test_payment(message, state, db)
            assert await state.get_state() is None

            certificates = await db.list_certificates_for_buyer(101)
            assert len(certificates) == 1
            assert certificates[0].amount == 10_000
            assert certificates[0].comment == "Для друга"
            assert certificates[0].status == CertificateStatus.ACTIVE

            reloaded = Database(db.path)
            await reloaded.init()
            persisted = await reloaded.get_certificate_by_public_id(
                certificates[0].public_id
            )
            assert persisted == certificates[0]
            await storage.close()

    asyncio.run(run())
