import asyncio
import sqlite3
import tempfile
from pathlib import Path

from app.db import Database
from app.models import CertificateStatus


def test_test_certificate_and_redemption_are_unique() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            await db.init()
            certificate = await db.issue_test_certificate(
                telegram_user_id=1,
                chat_id=1,
                amount_kopecks=500_000,
                comment="Тест",
                redeem_token="secret-token-1",
            )

            assert certificate.status == CertificateStatus.ACTIVE
            assert len(certificate.id) == 36

            found = await db.get_certificate_by_id_or_code(certificate.id)
            assert found is not None
            assert found.id == certificate.id

            redeemed, changed = await db.redeem_certificate_by_id(
                certificate_id=certificate.id,
                redeemed_by=123,
            )
            assert changed is True
            assert redeemed is not None
            assert redeemed.status == CertificateStatus.REDEEMED
            assert redeemed.redeemed_by == 123

            redeemed_again, changed_again = await db.redeem_certificate_by_id(
                certificate_id=certificate.id,
                redeemed_by=456,
            )
            assert changed_again is False
            assert redeemed_again is not None
            assert redeemed_again.redeemed_by == 123

    asyncio.run(run())


def test_only_one_concurrent_redemption_succeeds() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            db = Database(Path(directory) / "test.sqlite3")
            await db.init()
            certificate = await db.issue_test_certificate(
                telegram_user_id=1,
                chat_id=1,
                amount_kopecks=1_000_000,
                comment=None,
                redeem_token="secret-token-concurrent",
            )

            results = await asyncio.gather(
                db.redeem_certificate_by_id(
                    certificate_id=certificate.id,
                    redeemed_by=111,
                ),
                db.redeem_certificate_by_id(
                    certificate_id=certificate.id,
                    redeemed_by=222,
                ),
            )

            assert sum(changed for _, changed in results) == 1
            stored = await db.get_certificate_by_id(certificate.id)
            assert stored is not None
            assert stored.status == CertificateStatus.REDEEMED
            assert stored.redeemed_at is not None
            assert stored.redeemed_by in {111, 222}

    asyncio.run(run())


def test_v1_database_is_migrated_with_redeemed_by() -> None:
    async def run() -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.sqlite3"
            with sqlite3.connect(path) as connection:
                connection.executescript(
                    """
                    CREATE TABLE orders (
                        id TEXT PRIMARY KEY,
                        telegram_user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        amount_kopecks INTEGER NOT NULL,
                        comment TEXT,
                        status TEXT NOT NULL,
                        invoice_payload TEXT NOT NULL UNIQUE,
                        telegram_payment_charge_id TEXT UNIQUE,
                        provider_payment_charge_id TEXT UNIQUE,
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
                        redeemed_at TEXT
                    );
                    """
                )

            db = Database(path)
            await db.init()

            with sqlite3.connect(path) as connection:
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(certificates)")
                }
            assert "redeemed_by" in columns

    asyncio.run(run())
