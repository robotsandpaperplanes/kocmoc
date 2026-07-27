from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class OrderStatus(str, Enum):
    CREATED = "created"
    INVOICED = "invoiced"
    PAID = "paid"


class CertificateStatus(str, Enum):
    ACTIVE = "active"
    REDEEMED = "redeemed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Order:
    id: str
    telegram_user_id: int
    chat_id: int
    amount: int
    comment: str | None
    status: OrderStatus
    invoice_payload: str
    buyer_username: str | None = None


@dataclass(frozen=True)
class Certificate:
    id: str
    order_id: str
    public_id: str
    buyer_telegram_id: int
    buyer_username: str | None
    amount: int
    comment: str | None
    status: CertificateStatus
    created_at: str
    redeemed_at: str | None = None
    redeemed_by_telegram_id: int | None = None
    redeemed_by_username: str | None = None
    redeem_token: str | None = None
