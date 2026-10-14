"""Validated request and response contracts for version one of the API."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class EnrollmentTokenRequest(RequestModel):
    label: str = Field(min_length=1, max_length=120)
    ttl_seconds: int = Field(default=900, ge=60, le=3600)


class EnrollmentTokenResponse(BaseModel):
    enrollment_token: str
    expires_at: datetime


class EnrollRequest(RequestModel):
    enrollment_token: SecretStr = Field(min_length=32, max_length=128)
    hostname: str = Field(min_length=1, max_length=255)
    platform: Literal["windows", "linux", "macos"]
    agent_version: str = Field(min_length=1, max_length=64)


class EnrollResponse(BaseModel):
    device_id: str
    agent_token: str


class Inventory(RequestModel):
    os_version: str | None = Field(default=None, max_length=255)
    cpu_count: int | None = Field(default=None, ge=1, le=4096)
    memory_total_bytes: int | None = Field(default=None, ge=0, le=2**63 - 1)


class HeartbeatRequest(RequestModel):
    device_id: str = Field(min_length=36, max_length=36)
    agent_version: str = Field(min_length=1, max_length=64)
    inventory: Inventory | None = None


class DeviceResponse(BaseModel):
    device_id: str
    hostname: str
    platform: Literal["windows", "linux", "macos"]
    agent_version: str
    status: Literal["online", "offline", "revoked"]
    created_at: datetime
    last_seen_at: datetime | None
    revoked_at: datetime | None
    inventory: Inventory

    @field_validator("created_at", "last_seen_at", "revoked_at")
    @classmethod
    def utc_dates(cls, value: datetime | None) -> datetime | None:
        return as_utc(value)


class ModuleResponse(BaseModel):
    id: str
    name: str
    status: Literal["available", "unavailable", "planned"]
    capabilities: list[str]
    description: str


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    actor: str
    target_id: str
    occurred_at: datetime
    details: dict[str, Any]

    @field_validator("occurred_at")
    @classmethod
    def utc_dates(cls, value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UserRole = Literal["admin", "analyst", "employee"]


class EmailRequest(RequestModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or any(character.isspace() for character in normalized):
            raise ValueError("A valid email address is required")
        return normalized


class LoginRequest(EmailRequest):
    password: SecretStr = Field(min_length=1, max_length=1024)


class CreateUserRequest(EmailRequest):
    display_name: str = Field(min_length=1, max_length=120)
    password: SecretStr | None = Field(default=None, min_length=12, max_length=1024)
    role: UserRole = "employee"
    training_permission: bool = False


class UpdateUserRequest(RequestModel):
    role: UserRole | None = None
    active: bool | None = None
    training_permission: bool | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("role", "active", "training_permission", "display_name", mode="before")
    @classmethod
    def reject_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Omit unchanged fields instead of using null")
        return value


class ResetPasswordRequest(RequestModel):
    password: SecretStr = Field(min_length=12, max_length=1024)


class LinkOIDCRequest(RequestModel):
    issuer: str = Field(min_length=1, max_length=512)
    subject: str = Field(min_length=1, max_length=255)


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    role: UserRole
    permissions: list[str]
    active: bool


class MobileLoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(ge=60, le=28800)
    user: UserResponse
