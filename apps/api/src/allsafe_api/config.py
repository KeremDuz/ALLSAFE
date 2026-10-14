"""Typed settings for the laboratory API."""

from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read configuration from ALLSAFE_ variables (or an explicit constructor)."""

    model_config = SettingsConfigDict(env_prefix="ALLSAFE_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/allsafe.db"
    bootstrap_admin_token: SecretStr | None = None
    initialize_schema: bool = Field(
        default=True,
        description="Create missing tables in development/test only; use Alembic otherwise.",
    )
    heartbeat_timeout_seconds: int = Field(default=120, ge=10, le=86400)

    @field_validator("bootstrap_admin_token", mode="before")
    @classmethod
    def empty_token_is_unconfigured(cls, value: object) -> object:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str) and not raw.strip():
            return None
        return value
