from dataclasses import dataclass
from enum import StrEnum


class OrderStatus(StrEnum):
    CREATED = "created"
    INVOICED = "invoiced"
    PAID = "paid"


class CertificateStatus(StrEnum):
    ACTIVE = "active"
    REDEEMED = "redeemed"


@dataclass(frozen=True, slots=True)
class Order:
    id: str
    telegram_user_id: int
    chat_id: int
    amount_kopecks: int
    comment: str | None
    status: OrderStatus
    invoice_payload: str
    telegram_payment_charge_id: str | None = None
    provider_payment_charge_id: str | None = None


@dataclass(frozen=True, slots=True)
class Certificate:
    id: str
    order_id: str
    public_code: str
    redeem_token: str
    amount_kopecks: int
    comment: str | None
    status: CertificateStatus
    created_at: str | None = None
    redeemed_at: str | None = None
    redeemed_by: int | None = None
