from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import aiosqlite

from .models import Certificate, CertificateStatus, Order, OrderStatus


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    telegram_user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks > 0),
                    comment TEXT,
                    status TEXT NOT NULL,
                    invoice_payload TEXT NOT NULL UNIQUE,
                    telegram_payment_charge_id TEXT UNIQUE,
                    provider_payment_charge_id TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    paid_at TEXT
                );

                CREATE TABLE IF NOT EXISTS certificates (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),
                    public_code TEXT NOT NULL UNIQUE,
                    redeem_token TEXT NOT NULL UNIQUE,
                    amount_kopecks INTEGER NOT NULL CHECK(amount_kopecks > 0),
                    comment TEXT,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    redeemed_at TEXT,
                    redeemed_by INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_certificates_token
                    ON certificates(redeem_token);
                CREATE INDEX IF NOT EXISTS idx_certificates_status_created
                    ON certificates(status, created_at DESC);
                """
            )
            await self._migrate_certificates(db)
            await db.commit()

    async def _migrate_certificates(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(certificates)")
        columns = {row[1] for row in await cursor.fetchall()}
        if "redeemed_by" not in columns:
            await db.execute("ALTER TABLE certificates ADD COLUMN redeemed_by INTEGER")

    async def create_order(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        amount_kopecks: int,
        comment: str | None,
    ) -> Order:
        order_id = str(uuid4())
        payload = f"certificate:{order_id}"
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """
                INSERT INTO orders (
                    id, telegram_user_id, chat_id, amount_kopecks, comment,
                    status, invoice_payload, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    telegram_user_id,
                    chat_id,
                    amount_kopecks,
                    comment,
                    OrderStatus.CREATED.value,
                    payload,
                    utc_now(),
                ),
            )
            await db.commit()
        return Order(
            id=order_id,
            telegram_user_id=telegram_user_id,
            chat_id=chat_id,
            amount_kopecks=amount_kopecks,
            comment=comment,
            status=OrderStatus.CREATED,
            invoice_payload=payload,
        )

    async def issue_test_certificate(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        amount_kopecks: int,
        comment: str | None,
        redeem_token: str,
    ) -> Certificate:
        """Create a paid test order and a unique certificate in one transaction."""
        order_id = str(uuid4())
        certificate_id = str(uuid4())
        public_code = self._public_code(certificate_id)
        created_at = utc_now()
        payload = f"test:{order_id}"

        async with aiosqlite.connect(self.path) as db:
            await db.execute("BEGIN IMMEDIATE")
            await db.execute(
                """
                INSERT INTO orders (
                    id, telegram_user_id, chat_id, amount_kopecks, comment,
                    status, invoice_payload, created_at, paid_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    telegram_user_id,
                    chat_id,
                    amount_kopecks,
                    comment,
                    OrderStatus.PAID.value,
                    payload,
                    created_at,
                    created_at,
                ),
            )
            await db.execute(
                """
                INSERT INTO certificates (
                    id, order_id, public_code, redeem_token, amount_kopecks,
                    comment, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    certificate_id,
                    order_id,
                    public_code,
                    redeem_token,
                    amount_kopecks,
                    comment,
                    CertificateStatus.ACTIVE.value,
                    created_at,
                ),
            )
            await db.commit()

        return Certificate(
            id=certificate_id,
            order_id=order_id,
            public_code=public_code,
            redeem_token=redeem_token,
            amount_kopecks=amount_kopecks,
            comment=comment,
            status=CertificateStatus.ACTIVE,
            created_at=created_at,
        )

    async def get_certificate_by_token(self, token: str) -> Certificate | None:
        return await self._get_certificate(
            "SELECT * FROM certificates WHERE redeem_token = ?",
            (token,),
        )

    async def get_certificate_by_id_or_code(self, value: str) -> Certificate | None:
        normalized = value.strip()
        return await self._get_certificate(
            """
            SELECT * FROM certificates
            WHERE lower(id) = lower(?) OR upper(public_code) = upper(?)
            """,
            (normalized, normalized),
        )

    async def get_certificate_by_id(self, certificate_id: str) -> Certificate | None:
        return await self._get_certificate(
            "SELECT * FROM certificates WHERE id = ?",
            (certificate_id,),
        )

    async def list_recent_active_certificates(self, *, limit: int = 10) -> list[Certificate]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """
                SELECT * FROM certificates
                WHERE status = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (CertificateStatus.ACTIVE.value, limit),
            )
            rows = await cursor.fetchall()
        return [self._certificate_from_row(row) for row in rows]

    async def redeem_certificate_by_id(
        self,
        *,
        certificate_id: str,
        redeemed_by: int,
    ) -> tuple[Certificate | None, bool]:
        """Return (certificate, changed). Only the first redemption changes the row."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT * FROM certificates WHERE id = ?",
                (certificate_id,),
            )
            row = await cursor.fetchone()
            if not row:
                await db.rollback()
                return None, False

            if row["status"] != CertificateStatus.ACTIVE.value:
                await db.commit()
                return self._certificate_from_row(row), False

            redeemed_at = utc_now()
            update = await db.execute(
                """
                UPDATE certificates
                SET status = ?, redeemed_at = ?, redeemed_by = ?
                WHERE id = ? AND status = ?
                """,
                (
                    CertificateStatus.REDEEMED.value,
                    redeemed_at,
                    redeemed_by,
                    certificate_id,
                    CertificateStatus.ACTIVE.value,
                ),
            )
            changed = update.rowcount == 1
            await db.commit()

        certificate = await self.get_certificate_by_id(certificate_id)
        return certificate, changed

    async def redeem_certificate(self, token: str) -> Certificate | None:
        """Backward-compatible token redemption used by older integrations."""
        certificate = await self.get_certificate_by_token(token)
        if not certificate:
            return None
        redeemed, _ = await self.redeem_certificate_by_id(
            certificate_id=certificate.id,
            redeemed_by=0,
        )
        return redeemed

    async def _get_certificate(self, query: str, params: tuple[object, ...]) -> Certificate | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
        return self._certificate_from_row(row) if row else None

    @staticmethod
    def _public_code(certificate_id: str) -> str:
        return f"CERT-{certificate_id.replace('-', '')[:12].upper()}"

    @staticmethod
    def _order_from_row(row: aiosqlite.Row) -> Order:
        return Order(
            id=row["id"],
            telegram_user_id=row["telegram_user_id"],
            chat_id=row["chat_id"],
            amount_kopecks=row["amount_kopecks"],
            comment=row["comment"],
            status=OrderStatus(row["status"]),
            invoice_payload=row["invoice_payload"],
            telegram_payment_charge_id=row["telegram_payment_charge_id"],
            provider_payment_charge_id=row["provider_payment_charge_id"],
        )

    @staticmethod
    def _certificate_from_row(row: aiosqlite.Row) -> Certificate:
        keys = set(row.keys())
        return Certificate(
            id=row["id"],
            order_id=row["order_id"],
            public_code=row["public_code"],
            redeem_token=row["redeem_token"],
            amount_kopecks=row["amount_kopecks"],
            comment=row["comment"],
            status=CertificateStatus(row["status"]),
            created_at=row["created_at"] if "created_at" in keys else None,
            redeemed_at=row["redeemed_at"] if "redeemed_at" in keys else None,
            redeemed_by=row["redeemed_by"] if "redeemed_by" in keys else None,
        )
