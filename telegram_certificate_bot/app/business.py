from __future__ import annotations

import random
import re
import secrets
from datetime import datetime, timezone


PUBLIC_ID_PATTERN = re.compile(r"^\d{4}-\d{4}$")
MAX_DISPLAYED_COMMENT_LENGTH = 1000
SAILING_OUTCOMES = (
    ("Вы плывёте ✅", 96.0),
    ("Вы летите 🫵 🤣", 1.0),
    ("Вы испугались воды 😰", 2.5),
    ("На вас упал огнетушитель 🧯", 0.5),
)


def generate_public_id() -> str:
    """Return a human-readable random certificate ID."""
    return f"{secrets.randbelow(10_000):04d}-{secrets.randbelow(10_000):04d}"


def normalize_public_id(value: str) -> str | None:
    normalized = value.strip()
    return normalized if PUBLIC_ID_PATTERN.fullmatch(normalized) else None


def truncate_comment(comment: str) -> str:
    """Limit a displayed comment to 1000 characters, including the ellipsis."""
    if len(comment) >= MAX_DISPLAYED_COMMENT_LENGTH:
        return comment[: MAX_DISPLAYED_COMMENT_LENGTH - 1] + "…"
    return comment


def sailing_result() -> str:
    """Return one sailing outcome according to its configured percentage."""
    messages, weights = zip(*SAILING_OUTCOMES)
    return random.choices(messages, weights=weights, k=1)[0]


def utc_time_text(now: datetime | None = None) -> str:
    current = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    return f"Сей час {current:%H:%M}\nUTC+0"
