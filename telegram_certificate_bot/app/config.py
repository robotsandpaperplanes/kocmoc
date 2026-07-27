from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str = Field(alias="BOT_TOKEN")
    database_path: Path = Field(default=Path("./data/bot.sqlite3"), alias="DATABASE_PATH")
    admin_telegram_ids_raw: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("bot_token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        value = value.strip()
        if not value or "replace" in value.lower():
            raise ValueError("Укажите реальный BOT_TOKEN в .env")
        return value

    @field_validator("admin_telegram_ids_raw")
    @classmethod
    def validate_admin_telegram_ids(cls, value: str) -> str:
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            try:
                int(item)
            except ValueError as exc:
                raise ValueError(
                    "ADMIN_TELEGRAM_IDS должен содержать Telegram ID через запятую"
                ) from exc
        return value

    @property
    def admin_telegram_ids(self) -> set[int]:
        return {
            int(item.strip())
            for item in self.admin_telegram_ids_raw.split(",")
            if item.strip()
        }

    def is_admin(self, telegram_user_id: int) -> bool:
        return telegram_user_id in self.admin_telegram_ids
