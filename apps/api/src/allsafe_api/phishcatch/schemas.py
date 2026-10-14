"""Bounded service and human review contracts."""

from datetime import datetime
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from allsafe_api.schemas import RequestModel


def display_url(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


class ScanRequest(RequestModel):
    url: str = Field(min_length=1, max_length=2048)
    source: Literal["qr", "url"]
    client_request_id: UUID

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value if "://" in value else f"https://{value}"
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError
            _ = parsed.port
            if any(character.isspace() or ord(character) < 32 for character in value):
                raise ValueError
        except ValueError as problem:
            raise ValueError("An HTTP(S) URL without embedded credentials is required") from problem
        if len(value) > 2048:
            raise ValueError("URL is too long")
        return value


class UpstreamStage(BaseModel):
    scanner: str = Field(max_length=80, pattern=r"^[A-Za-z0-9_ -]+$")
    verdict: Literal["clean", "malicious", "unknown"]
    status: Literal["completed", "unavailable", "failed", "skipped"] = "completed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_score: float | None = Field(default=None, ge=0, le=1)


class UpstreamAnalysis(BaseModel):
    contract_version: Literal["2"]
    observation_id: int | None = Field(default=None, ge=1)
    scan_status: Literal["complete", "partial", "failed"]
    final_verdict: Literal["clean", "malicious", "unknown"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    risk_score: float | None = Field(default=None, ge=0, le=1)
    malicious_probability: float | None = Field(default=None, ge=0, le=1)
    clean_probability: float | None = Field(default=None, ge=0, le=1)
    decided_by: str = Field(max_length=80, pattern=r"^[A-Za-z0-9_ -]+$")
    stages: list[UpstreamStage] = Field(max_length=30)


class IntegrationResponse(BaseModel):
    analysis: UpstreamAnalysis
    feature_version: Literal["phishcatch-v1"]
    features: dict[str, float] = Field(max_length=200)


class ReviewRequest(RequestModel):
    label: Literal["clean", "malicious", "uncertain"]
    notes: str = Field(default="", max_length=1000)


class ScanResponse(BaseModel):
    id: str
    user_id: str
    client_request_id: str
    source: Literal["qr", "url"]
    url: str
    scan_status: Literal["pending", "complete", "partial", "failed"]
    analysis: dict[str, Any] | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None
    verified_label: Literal["clean", "malicious", "uncertain"] | None
    review_id: str | None
    review_notes: str | None
    training_approved: bool
    feature_count: int
