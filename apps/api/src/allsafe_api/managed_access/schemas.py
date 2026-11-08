"""Bounded HTTP/WebSocket contracts for the managed access boundary."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from allsafe_api.schemas import as_utc


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Reason(RequestModel):
    reason: str = Field(min_length=3, max_length=300)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3 or any(ord(c) < 32 for c in value):
            raise ValueError("A meaningful single-line reason is required")
        return value


class CreateTerminalSession(Reason):
    device_id: str
    cols: int = Field(default=100, ge=20, le=240)
    rows: int = Field(default=30, ge=5, le=100)

    @field_validator("device_id")
    @classmethod
    def canonical_device_id(cls, value: str) -> str:
        return str(UUID(value))


class TerminalSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    device_id: str
    status: Literal["pending", "connecting", "active", "closed", "expired"]
    created_at: datetime
    expires_at: datetime
    closed_reason: str | None

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc_dates(cls, value: datetime) -> datetime | None:
        return as_utc(value)


class ServiceStatus(BaseModel):
    configured: bool
    account: str | None = None


class AccessStatus(BaseModel):
    device_id: str
    terminal: ServiceStatus
    rdp: ServiceStatus
    error_code: str | None = None


class Hello(RequestModel):
    type: Literal["hello"]
    csrf: str = Field(min_length=32, max_length=128)


class Input(RequestModel):
    type: Literal["input"]
    data: str = Field(min_length=1, max_length=8192)

    @field_validator("data")
    @classmethod
    def bounded_utf8(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 8192:
            raise ValueError("Input is too large")
        return value


class Resize(RequestModel):
    type: Literal["resize"]
    cols: int = Field(ge=20, le=240)
    rows: int = Field(ge=5, le=100)


class Ack(RequestModel):
    type: Literal["ack"]
    sequence: int = Field(ge=1, le=2**31 - 1)


INPUT_ADAPTER: TypeAdapter[Input | Resize | Ack] = TypeAdapter(
    Annotated[Input | Resize | Ack, Field(discriminator="type")]
)
