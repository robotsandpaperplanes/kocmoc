import asyncio
import sqlite3
import tempfile
from pathlib import Path

from app.business import normalize_public_id
from app.db import Database
from app.models import CertificateStatus


def test_create_certificate_and_prevent_repeated_redemption() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            await db.init()
            certificate = await db.issue_test_certificate(
                telegram_user_id=101,
                buyer_username="buyer",
                chat_id=202,
                amount=10_000,
                comment="Для друга",
                public_id_generator=lambda: "1234-5678",
            )

            assert certificate.public_id == "1234-5678"
            assert certificate.amount == 10_000
            assert certificate.buyer_telegram_id == 101
            assert certificate.buyer_username == "buyer"
            assert certificate.status == CertificateStatus.ACTIVE

            owned = await db.list_certificates_for_buyer(101)
            assert [item.public_id for item in owned] == ["1234-5678"]

            redeemed, changed = await db.redeem_certificate_by_public_id(
                public_id=certificate.public_id,
                redeemed_by_telegram_id=303,
                redeemed_by_username="first_admin",
            )
            assert changed is True
            assert redeemed is not None
            assert redeemed.status == CertificateStatus.REDEEMED
            assert redeemed.redeemed_at is not None
            assert redeemed.redeemed_by_telegram_id == 303
            assert redeemed.redeemed_by_username == "first_admin"

            redeemed_again, changed_again = await db.redeem_certificate_by_public_id(
                public_id=certificate.public_id,
                redeemed_by_telegram_id=404,
                redeemed_by_username="second_admin",
            )
            assert changed_again is False
            assert redeemed_again is not None
            assert redeemed_again.redeemed_at == redeemed.redeemed_at
            assert redeemed_again.redeemed_by_telegram_id == 303
            assert redeemed_again.redeemed_by_username == "first_admin"

    asyncio.run(run())


def test_public_id_collision_is_retried() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            await db.init()
            await db.issue_test_certificate(
                telegram_user_id=1,
                buyer_username=None,
                chat_id=1,
                amount=5_000,
                comment=None,
                public_id_generator=lambda: "0000-0001",
            )

            values = iter(["0000-0001", "0000-0002"])
            second = await db.issue_test_certificate(
                telegram_user_id=1,
                buyer_username=None,
                chat_id=1,
                amount=30_000,
                comment=None,
                public_id_generator=lambda: next(values),
            )
            assert second.public_id == "0000-0002"

    asyncio.run(run())


def test_same_payment_issues_only_one_certificate() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.sqlite3"
            db = Database(path)
            await db.init()

            async def issue():
                return await db.issue_paid_certificate(
                    telegram_user_id=101,
                    buyer_username="buyer",
                    chat_id=202,
                    amount=10_000,
                    comment="Один платёж",
                    invoice_payload="order:stable-payload",
                    telegram_payment_charge_id="telegram-charge-1",
                    provider_payment_charge_id="provider-charge-1",
                    public_id_generator=lambda: "1111-2222",
                )

            first, second = await asyncio.gather(issue(), issue())

            assert first.certificate.id == second.certificate.id
            assert first.certificate.public_id == "1111-2222"
            assert {first.created, second.created} == {False, True}

            with sqlite3.connect(path) as connection:
                order_count = connection.execute(
                    "SELECT COUNT(*) FROM orders"
                ).fetchone()[0]
                certificate_count = connection.execute(
                    "SELECT COUNT(*) FROM certificates"
                ).fetchone()[0]
            assert order_count == 1
            assert certificate_count == 1

    asyncio.run(run())


def test_online_backup_is_valid_and_old_copies_are_pruned() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db = Database(root / "test.sqlite3")
            await db.init()
            await db.issue_test_certificate(
                telegram_user_id=1,
                buyer_username=None,
                chat_id=1,
                amount=5_000,
                comment=None,
                public_id_generator=lambda: "2222-3333",
            )

            backup_dir = root / "backups"
            created = [
                await db.create_backup(backup_dir, keep_count=2)
                for _ in range(3)
            ]

            backups = sorted(backup_dir.glob("certificate-bot-*.sqlite3"))
            assert len(backups) == 2
            assert created[-1] in backups
            with sqlite3.connect(created[-1]) as backup:
                assert backup.execute(
                    "PRAGMA integrity_check"
                ).fetchone() == ("ok",)
                assert backup.execute(
                    "SELECT COUNT(*) FROM certificates"
                ).fetchone() == (1,)

    asyncio.run(run())


def test_archived_v2_database_is_migrated_without_losing_certificate() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            with sqlite3.connect(path) as db:
                db.executescript(
                    """
                    CREATE TABLE orders (
                        id TEXT PRIMARY KEY,
                        telegram_user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        amount_kopecks INTEGER NOT NULL,
                        comment TEXT,
                        status TEXT NOT NULL,
                        invoice_payload TEXT NOT NULL UNIQUE,
                        telegram_payment_charge_id TEXT,
                        provider_payment_charge_id TEXT,
                        created_at TEXT NOT NULL,
                        paid_at TEXT
                    );
                    CREATE TABLE certificates (
                        id TEXT PRIMARY KEY,
                        order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),
                        public_code TEXT NOT NULL UNIQUE,
                        redeem_token TEXT NOT NULL UNIQUE,
                        amount_kopecks INTEGER NOT NULL,
                        comment TEXT,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        redeemed_at TEXT,
                        redeemed_by INTEGER
                    );
                    INSERT INTO orders VALUES (
                        'order-1', 777, 888, 500000, 'Старый комментарий',
                        'paid', 'test:order-1', NULL, NULL,
                        '2026-07-24T12:00:00+00:00', '2026-07-24T12:00:00+00:00'
                    );
                    INSERT INTO certificates VALUES (
                        'certificate-1', 'order-1', 'CERT-OLD', 'old-token',
                        500000, 'Старый комментарий', 'active',
                        '2026-07-24T12:00:00+00:00', NULL, NULL
                    );
                    """
                )

            storage = Database(path)
            await storage.init()
            migrated = await storage.get_certificate_by_token("old-token")

            assert migrated is not None
            assert normalize_public_id(migrated.public_id) == migrated.public_id
            assert migrated.amount == 5_000
            assert migrated.buyer_telegram_id == 777
            assert migrated.comment == "Старый комментарий"

    asyncio.run(run())
