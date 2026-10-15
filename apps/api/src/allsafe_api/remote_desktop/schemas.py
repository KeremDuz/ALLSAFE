"""Small, strict desktop protocol; no clipboard, file, command or shell channels."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from allsafe_api.schemas import RequestModel, as_utc


class CreateDesktopSession(RequestModel):
    device_id: UUID
    reason: str = Field(min_length=3, max_length=300)
    mode: Literal["view", "control"]


class DesktopDecision(RequestModel):
    device_id: UUID
    approved: bool = Field(strict=True)


class DesktopSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    operator_name: str
    reason: str
    mode: Literal["view", "control"]
    status: Literal["pending", "approved", "active", "denied", "closed", "expired"]
    created_at: datetime
    expires_at: datetime
    closed_reason: str | None

    @field_validator("created_at", "expires_at")
    @classmethod
    def utc_dates(cls, value: datetime) -> datetime | None:
        return as_utc(value)


class PendingDesktopSessions(BaseModel):
    sessions: list[DesktopSessionResponse]


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ViewerHello(ProtocolModel):
    type: Literal["hello"]
    csrf: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class AgentHello(ProtocolModel):
    type: Literal["hello"]
    device_id: str = Field(min_length=36, max_length=36)


class Display(ProtocolModel):
    type: Literal["display"]
    width: int = Field(ge=1, le=1920)
    height: int = Field(ge=1, le=1080)


class Stop(ProtocolModel):
    type: Literal["stop"]


class Pointer(ProtocolModel):
    type: Literal["pointer"]
    action: Literal["move", "down", "up"]
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    button: Literal["left", "right", "middle"]


class Wheel(ProtocolModel):
    type: Literal["wheel"]
    delta: int = Field(ge=-1200, le=1200)


KEY_CODES = frozenset(
    [f"Key{letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
    + [f"Digit{digit}" for digit in range(10)]
    + [f"Numpad{digit}" for digit in range(10)]
    + [f"F{number}" for number in range(1, 13)]
    + [
        "Enter",
        "Escape",
        "Backspace",
        "Tab",
        "Space",
        "Minus",
        "Equal",
        "BracketLeft",
        "BracketRight",
        "Backslash",
        "Semicolon",
        "Quote",
        "Backquote",
        "Comma",
        "Period",
        "Slash",
        "CapsLock",
        "ArrowLeft",
        "ArrowRight",
        "ArrowUp",
        "ArrowDown",
        "Home",
        "End",
        "PageUp",
        "PageDown",
        "Delete",
        "Insert",
        "ShiftLeft",
        "ShiftRight",
        "ControlLeft",
        "ControlRight",
        "AltLeft",
        "AltRight",
        "NumpadAdd",
        "NumpadSubtract",
        "NumpadMultiply",
        "NumpadDivide",
        "NumpadDecimal",
        "NumpadEnter",
        "NumLock",
    ]
)


class Key(ProtocolModel):
    type: Literal["key"]
    action: Literal["down", "up"]
    code: str

    @field_validator("code")
    @classmethod
    def allowed_code(cls, value: str) -> str:
        if value not in KEY_CODES:
            raise ValueError("Unsupported keyboard code")
        return value


class Release(ProtocolModel):
    type: Literal["release"]


InputMessage = Annotated[Pointer | Wheel | Key | Release, Field(discriminator="type")]
INPUT_ADAPTER = TypeAdapter(InputMessage)
AGENT_ADAPTER = TypeAdapter(Annotated[Display | Stop, Field(discriminator="type")])
