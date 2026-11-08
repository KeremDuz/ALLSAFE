"""Persist terminal authorization metadata, never shell input or output."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from allsafe_api.models import Base, new_id, utc_now


class TerminalSession(Base):
    __tablename__ = "managed_terminal_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True)
    active_device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), unique=True)
    requester_session_id: Mapped[str] = mapped_column(ForeignKey("user_sessions.id"))
    operator_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str] = mapped_column(String(300))
    account: Mapped[str] = mapped_column(String(120))
    credential_hash: Mapped[str] = mapped_column(String(64))
    profile_fingerprint: Mapped[str] = mapped_column(String(64))
    cols: Mapped[int] = mapped_column(Integer)
    rows: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_reason: Mapped[str | None] = mapped_column(String(64))
