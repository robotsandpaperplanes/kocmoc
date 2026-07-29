import re
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    database_path: Path = Field(default=Path("./data/bot.sqlite3"), alias="DATABASE_PATH")
    admin_telegram_ids_raw: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")
    backup_dir: Path = Field(default=Path("./data/backups"), alias="BACKUP_DIR")
    backup_interval_hours: float = Field(
        default=24,
        ge=0,
        alias="BACKUP_INTERVAL_HOURS",
    )
    backup_keep_count: int = Field(default=14, ge=1, alias="BACKUP_KEEP_COUNT")
    notify_admins_on_error: bool = Field(
        default=True,
        alias="NOTIFY_ADMINS_ON_ERROR",
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("bot_token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        value = value.strip()
        if not value or "replace" in value.lower():
            raise ValueError("Укажите реальный BOT_TOKEN в .env")
        return value

    @property
    def admin_telegram_ids(self) -> set[int]:
        result: set[int] = set()
        for item in re.split(r"[\s,;&]+", self.admin_telegram_ids_raw.strip()):
            if not item:
                continue
            try:
                result.add(int(item))
            except ValueError as exc:
                raise ValueError(
                    "ADMIN_TELEGRAM_IDS должен содержать Telegram ID "
                    "через пробел, запятую, точку с запятой или &"
                ) from exc
        return result

    def is_admin(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self.admin_telegram_ids
