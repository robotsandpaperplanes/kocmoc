from __future__ import annotations

import secrets
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import aiosqlite

from .business import CERTIFICATE_AMOUNTS, generate_public_id
from .models import (
    Certificate,
    CertificateIssueResult,
    CertificateStatus,
    OrderStatus,
)


SQLITE_BUSY_TIMEOUT_MS = 10_000


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    """SQLite storage with migrations from the archived MVP/V2 schema."""

    def __init__(self, path: Path) -> None:
        self.path = path

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            await self._configure_connection(db, foreign_keys=True)
            await db.execute("PRAGMA journal_mode=WAL")
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
                    paid_at TEXT,
                    buyer_username TEXT
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
                    redeemed_by INTEGER,
                    public_id TEXT,
                    amount INTEGER,
                    buyer_telegram_id INTEGER,
                    buyer_username TEXT,
                    redeemed_by_telegram_id INTEGER,
                    redeemed_by_username TEXT
                );
                """
            )
            await self._migrate(db)
            await self._assert_integrity(db)
            await db.executescript(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_certificates_public_id
                    ON certificates(public_id);
                CREATE INDEX IF NOT EXISTS idx_certificates_buyer_created
                    ON certificates(buyer_telegram_id, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_certificates_status_created
                    ON certificates(status, created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_certificates_token
                    ON certificates(redeem_token);
                """
            )
            await db.commit()

    async def create_backup(
        self,
        backup_dir: Path,
        *,
        keep_count: int,
    ) -> Path:
        """Create and verify an online SQLite backup, then prune old copies."""
        if keep_count < 1:
            raise ValueError("keep_count должен быть положительным")

        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        destination = backup_dir / f"certificate-bot-{timestamp}.sqlite3"
        if destination.resolve() == self.path.resolve():
            raise ValueError("Путь резервной копии совпадает с основной базой")

        try:
            async with aiosqlite.connect(self.path) as source:
                await self._configure_connection(source)
                async with aiosqlite.connect(destination) as target:
                    await self._configure_connection(target)
                    await source.backup(target)
                    cursor = await target.execute("PRAGMA integrity_check")
                    result = await cursor.fetchone()
                    if not result or result[0] != "ok":
                        raise RuntimeError("Проверка резервной копии SQLite не пройдена")
        except Exception:
            destination.unlink(missing_ok=True)
            raise

        backups = sorted(backup_dir.glob("certificate-bot-*.sqlite3"))
        for expired in backups[:-keep_count]:
            expired.unlink(missing_ok=True)
        return destination

    @staticmethod
    async def _configure_connection(
        db: aiosqlite.Connection,
        *,
        foreign_keys: bool = False,
    ) -> None:
        await db.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        if foreign_keys:
            await db.execute("PRAGMA foreign_keys=ON")

    @staticmethod
    async def _assert_integrity(db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA quick_check")
        result = await cursor.fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError("Проверка целостности основной базы SQLite не пройдена")

    async def _migrate(self, db: aiosqlite.Connection) -> None:
        order_columns = await self._column_names(db, "orders")
        if "buyer_username" not in order_columns:
            await db.execute("ALTER TABLE orders ADD COLUMN buyer_username TEXT")

        certificate_columns = await self._column_names(db, "certificates")
        additions = {
            "public_id": "TEXT",
            "amount": "INTEGER",
            "buyer_telegram_id": "INTEGER",
            "buyer_username": "TEXT",
            "redeemed_by": "INTEGER",
            "redeemed_by_telegram_id": "INTEGER",
            "redeemed_by_username": "TEXT",
        }
        for column, column_type in additions.items():
            if column not in certificate_columns:
                await db.execute(
                    f"ALTER TABLE certificates ADD COLUMN {column} {column_type}"
                )

        await db.execute(
            """
            UPDATE certificates
            SET amount = CASE
                WHEN amount IS NOT NULL THEN amount
                ELSE CAST(amount_kopecks / 100 AS INTEGER)
            END
            WHERE amount IS NULL
            """
        )
        # Early test builds stored the four old tomato denominations directly
        # in both amount columns. Preserve those certificates by mapping each
        # old button position to its new ruble denomination.
        await db.execute(
            """
            UPDATE certificates
            SET
                amount = CASE amount
                    WHEN 5 THEN 5000
                    WHEN 10 THEN 10000
                    WHEN 15 THEN 30000
                    WHEN 20 THEN 50000
                END,
                amount_kopecks = CASE amount
                    WHEN 5 THEN 500000
                    WHEN 10 THEN 1000000
                    WHEN 15 THEN 3000000
                    WHEN 20 THEN 5000000
                END
            WHERE amount IN (5, 10, 15, 20)
              AND amount_kopecks IN (5, 10, 15, 20)
            """
        )
        await db.execute(
            """
            UPDATE orders
            SET amount_kopecks = CASE amount_kopecks
                WHEN 5 THEN 500000
                WHEN 10 THEN 1000000
                WHEN 15 THEN 3000000
                WHEN 20 THEN 5000000
            END
            WHERE amount_kopecks IN (5, 10, 15, 20)
              AND invoice_payload LIKE 'test:%'
            """
        )
        await db.execute(
            """
            UPDATE certificates
            SET buyer_telegram_id = (
                SELECT telegram_user_id FROM orders WHERE orders.id = certificates.order_id
            )
            WHERE buyer_telegram_id IS NULL
            """
        )
        await db.execute(
            """
            UPDATE certificates
            SET buyer_username = (
                SELECT buyer_username FROM orders WHERE orders.id = certificates.order_id
            )
            WHERE buyer_username IS NULL
            """
        )
        await db.execute(
            """
            UPDATE certificates
            SET redeemed_by_telegram_id = redeemed_by
            WHERE redeemed_by_telegram_id IS NULL AND redeemed_by IS NOT NULL
            """
        )

        cursor = await db.execute(
            "SELECT id FROM certificates WHERE public_id IS NULL OR public_id = ''"
        )
        for row in await cursor.fetchall():
            public_id = await self._unused_public_id(db, generate_public_id)
            await db.execute(
                "UPDATE certificates SET public_id = ? WHERE id = ?",
                (public_id, row[0]),
            )

    @staticmethod
    async def _column_names(
        db: aiosqlite.Connection,
        table: str,
    ) -> set[str]:
        cursor = await db.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in await cursor.fetchall()}

    @staticmethod
    async def _unused_public_id(
        db: aiosqlite.Connection,
        generator: Callable[[], str],
    ) -> str:
        for _ in range(100):
            candidate = generator()
            cursor = await db.execute(
                "SELECT 1 FROM certificates WHERE public_id = ?",
                (candidate,),
            )
            if not await cursor.fetchone():
                return candidate
        raise RuntimeError("Не удалось создать уникальный ID сертификата")

    async def issue_paid_certificate(
        self,
        *,
        telegram_user_id: int,
        buyer_username: str | None,
        chat_id: int,
        amount: int,
        comment: str | None,
        invoice_payload: str,
        telegram_payment_charge_id: str | None = None,
        provider_payment_charge_id: str | None = None,
        paid_at: str | None = None,
        public_id_generator: Callable[[], str] = generate_public_id,
    ) -> CertificateIssueResult:
        """Issue at most one certificate for the same confirmed payment."""
        if amount not in CERTIFICATE_AMOUNTS:
            raise ValueError("Недопустимый номинал сертификата")
        invoice_payload = invoice_payload.strip()
        if not invoice_payload:
            raise ValueError("invoice_payload не должен быть пустым")

        order_id = str(uuid4())
        certificate_id = str(uuid4())
        created_at = utc_now()
        redeem_token = secrets.token_urlsafe(24)

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await self._configure_connection(db, foreign_keys=True)
            try:
                await db.execute("BEGIN IMMEDIATE")
                existing = await self._find_certificate_for_payment(
                    db,
                    invoice_payload=invoice_payload,
                    telegram_payment_charge_id=telegram_payment_charge_id,
                    provider_payment_charge_id=provider_payment_charge_id,
                )
                if existing:
                    if (
                        existing["payment_invoice_payload"] != invoice_payload
                        or existing["payment_telegram_user_id"] != telegram_user_id
                        or existing["payment_amount_kopecks"] != amount * 100
                    ):
                        raise ValueError(
                            "Платёжные идентификаторы уже связаны с другим заказом"
                        )
                    await db.commit()
                    return CertificateIssueResult(
                        certificate=self._certificate_from_row(existing),
                        created=False,
                    )

                public_id = await self._unused_public_id(db, public_id_generator)
                await db.execute(
                    """
                    INSERT INTO orders (
                        id, telegram_user_id, chat_id, amount_kopecks, comment,
                        status, invoice_payload, telegram_payment_charge_id,
                        provider_payment_charge_id, created_at, paid_at,
                        buyer_username
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        telegram_user_id,
                        chat_id,
                        amount * 100,
                        comment,
                        OrderStatus.PAID.value,
                        invoice_payload,
                        telegram_payment_charge_id,
                        provider_payment_charge_id,
                        created_at,
                        paid_at or created_at,
                        buyer_username,
                    ),
                )
                await db.execute(
                    """
                    INSERT INTO certificates (
                        id, order_id, public_code, redeem_token, amount_kopecks,
                        comment, status, created_at, public_id, amount,
                        buyer_telegram_id, buyer_username
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        certificate_id,
                        order_id,
                        public_id,
                        redeem_token,
                        amount * 100,
                        comment,
                        CertificateStatus.ACTIVE.value,
                        created_at,
                        public_id,
                        amount,
                        telegram_user_id,
                        buyer_username,
                    ),
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

        certificate = Certificate(
            id=certificate_id,
            order_id=order_id,
            public_id=public_id,
            buyer_telegram_id=telegram_user_id,
            buyer_username=buyer_username,
            amount=amount,
            comment=comment,
            status=CertificateStatus.ACTIVE,
            created_at=created_at,
            redeem_token=redeem_token,
        )
        return CertificateIssueResult(certificate=certificate, created=True)

    async def issue_test_certificate(
        self,
        *,
        telegram_user_id: int,
        buyer_username: str | None,
        chat_id: int,
        amount: int,
        comment: str | None,
        idempotency_key: str | None = None,
        public_id_generator: Callable[[], str] = generate_public_id,
    ) -> Certificate:
        """Issue a test certificate with the same idempotency as real payment."""
        result = await self.issue_paid_certificate(
            telegram_user_id=telegram_user_id,
            buyer_username=buyer_username,
            chat_id=chat_id,
            amount=amount,
            comment=comment,
            invoice_payload=f"test:{idempotency_key or uuid4()}",
            public_id_generator=public_id_generator,
        )
        return result.certificate

    @staticmethod
    async def _find_certificate_for_payment(
        db: aiosqlite.Connection,
        *,
        invoice_payload: str,
        telegram_payment_charge_id: str | None,
        provider_payment_charge_id: str | None,
    ) -> aiosqlite.Row | None:
        conditions = ["orders.invoice_payload = ?"]
        params: list[object] = [invoice_payload]
        if telegram_payment_charge_id:
            conditions.append("orders.telegram_payment_charge_id = ?")
            params.append(telegram_payment_charge_id)
        if provider_payment_charge_id:
            conditions.append("orders.provider_payment_charge_id = ?")
            params.append(provider_payment_charge_id)

        cursor = await db.execute(
            f"""
            SELECT
                certificates.*,
                orders.invoice_payload AS payment_invoice_payload,
                orders.telegram_user_id AS payment_telegram_user_id,
                orders.amount_kopecks AS payment_amount_kopecks
            FROM orders
            JOIN certificates ON certificates.order_id = orders.id
            WHERE {" OR ".join(conditions)}
            """,
            tuple(params),
        )
        rows = await cursor.fetchall()
        if len({row["id"] for row in rows}) > 1:
            raise RuntimeError(
                "Платёжные идентификаторы связаны с разными сертификатами"
            )
        return rows[0] if rows else None

    async def get_certificate_by_public_id(
        self,
        public_id: str,
    ) -> Certificate | None:
        return await self._get_certificate(
            "SELECT * FROM certificates WHERE public_id = ?",
            (public_id,),
        )

    async def get_certificate_by_id(self, certificate_id: str) -> Certificate | None:
        return await self._get_certificate(
            "SELECT * FROM certificates WHERE id = ?",
            (certificate_id,),
        )

    async def get_certificate_by_token(self, token: str) -> Certificate | None:
        return await self._get_certificate(
            "SELECT * FROM certificates WHERE redeem_token = ?",
            (token,),
        )

    async def get_certificate_by_id_or_code(
        self,
        value: str,
    ) -> Certificate | None:
        """Compatibility lookup for UUIDs and old public_code values."""
        normalized = value.strip()
        return await self._get_certificate(
            """
            SELECT * FROM certificates
            WHERE lower(id) = lower(?)
               OR public_id = ?
               OR upper(public_code) = upper(?)
            """,
            (normalized, normalized, normalized),
        )

    async def list_certificates_for_buyer(
        self,
        telegram_user_id: int,
    ) -> list[Certificate]:
        return await self._list_certificates(
            """
            SELECT * FROM certificates
            WHERE buyer_telegram_id = ?
            ORDER BY created_at DESC
            """,
            (telegram_user_id,),
        )

    async def list_certificates_by_status(
        self,
        status: CertificateStatus,
        *,
        limit: int = 20,
    ) -> list[Certificate]:
        return await self._list_certificates(
            """
            SELECT * FROM certificates
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (status.value, limit),
        )

    async def list_recent_active_certificates(
        self,
        *,
        limit: int = 10,
    ) -> list[Certificate]:
        return await self.list_certificates_by_status(
            CertificateStatus.ACTIVE,
            limit=limit,
        )

    async def redeem_certificate_by_public_id(
        self,
        *,
        public_id: str,
        redeemed_by_telegram_id: int,
        redeemed_by_username: str | None,
    ) -> tuple[Certificate | None, bool]:
        """Atomically redeem once and preserve the first administrator."""
        redeemed_at = utc_now()
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await self._configure_connection(db, foreign_keys=True)
            await db.execute("BEGIN IMMEDIATE")
            update = await db.execute(
                """
                UPDATE certificates
                SET status = ?,
                    redeemed_at = ?,
                    redeemed_by = ?,
                    redeemed_by_telegram_id = ?,
                    redeemed_by_username = ?
                WHERE public_id = ? AND status = ?
                """,
                (
                    CertificateStatus.REDEEMED.value,
                    redeemed_at,
                    redeemed_by_telegram_id,
                    redeemed_by_telegram_id,
                    redeemed_by_username,
                    public_id,
                    CertificateStatus.ACTIVE.value,
                ),
            )
            changed = update.rowcount == 1
            cursor = await db.execute(
                "SELECT * FROM certificates WHERE public_id = ?",
                (public_id,),
            )
            row = await cursor.fetchone()
            await db.commit()

        return (self._certificate_from_row(row), changed) if row else (None, False)

    async def redeem_certificate_by_id(
        self,
        *,
        certificate_id: str,
        redeemed_by: int,
    ) -> tuple[Certificate | None, bool]:
        """Backward-compatible UUID redemption entrypoint."""
        certificate = await self.get_certificate_by_id(certificate_id)
        if not certificate:
            return None, False
        return await self.redeem_certificate_by_public_id(
            public_id=certificate.public_id,
            redeemed_by_telegram_id=redeemed_by,
            redeemed_by_username=None,
        )

    async def _get_certificate(
        self,
        query: str,
        params: tuple[object, ...],
    ) -> Certificate | None:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await self._configure_connection(db)
            cursor = await db.execute(query, params)
            row = await cursor.fetchone()
        return self._certificate_from_row(row) if row else None

    async def _list_certificates(
        self,
        query: str,
        params: tuple[object, ...],
    ) -> list[Certificate]:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await self._configure_connection(db)
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [self._certificate_from_row(row) for row in rows]

    @staticmethod
    def _certificate_from_row(row: aiosqlite.Row) -> Certificate:
        return Certificate(
            id=row["id"],
            order_id=row["order_id"],
            public_id=row["public_id"],
            buyer_telegram_id=row["buyer_telegram_id"],
            buyer_username=row["buyer_username"],
            amount=row["amount"],
            comment=row["comment"],
            status=CertificateStatus(row["status"]),
            created_at=row["created_at"],
            redeemed_at=row["redeemed_at"],
            redeemed_by_telegram_id=row["redeemed_by_telegram_id"],
            redeemed_by_username=row["redeemed_by_username"],
            redeem_token=row["redeem_token"],
        )
