"""Only session metadata is persisted; frames and input never enter the database."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from allsafe_api.models import Base, new_id, utc_now


class DesktopSession(Base):
    __tablename__ = "remote_desktop_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False, index=True)
    # NULL after termination; the unique reservation is enforced by the database,
    # including simultaneous requests handled by different HTTP threads.
    active_device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), unique=True)
    requester_session_id: Mapped[str] = mapped_column(
        ForeignKey("user_sessions.id"), nullable=False
    )
    operator_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    operator_name: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    mode: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_reason: Mapped[str | None] = mapped_column(String(64))
