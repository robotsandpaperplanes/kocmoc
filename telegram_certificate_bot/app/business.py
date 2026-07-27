from __future__ import annotations

import random
import re
import secrets
from datetime import datetime, timezone


PUBLIC_ID_PATTERN = re.compile(r"^\d{4}-\d{4}$")
MAX_DISPLAYED_COMMENT_LENGTH = 1000


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
    """Return the rare flying result for exactly one draw out of one hundred."""
    return "Вы плывете ✅" if random.randrange(100) < 99 else "Вы летите 🤣"


def utc_time_text(now: datetime | None = None) -> str:
    current = now.astimezone(timezone.utc) if now else datetime.now(timezone.utc)
    return f"Сей час {current:%H:%M}\nUTC+0"
