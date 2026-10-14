"""Predictions, independent reviews and explicitly approved feature snapshots."""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from allsafe_api.models import Base, new_id, utc_now


class PhishScan(Base):
    __tablename__ = "phish_scans"
    __table_args__ = (UniqueConstraint("user_id", "client_request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    client_request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False)
    url_display: Mapped[str] = mapped_column(String(2048), nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_code: Mapped[str | None] = mapped_column(String(64))
    observation_id: Mapped[int | None] = mapped_column(Integer)
    feature_version: Mapped[str | None] = mapped_column(String(64))
    features: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    review_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PhishReview(Base):
    __tablename__ = "phish_reviews"
    __table_args__ = (UniqueConstraint("scan_id", "revision"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    scan_id: Mapped[str] = mapped_column(ForeignKey("phish_scans.id"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    notes: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TrainingApproval(Base):
    __tablename__ = "phish_training_approvals"
    scan_id: Mapped[str] = mapped_column(ForeignKey("phish_scans.id"), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("phish_reviews.id"), nullable=False)
    approver_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    label: Mapped[int] = mapped_column(Integer, nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    features: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
