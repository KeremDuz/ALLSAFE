"""Explicit local identity mapping, scoped to a configured manager origin."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from allsafe_api.models import Base, new_id, utc_now


class WazuhMapping(Base):
    __tablename__ = "wazuh_device_mappings"
    __table_args__ = (
        UniqueConstraint("server_scope", "agent_id"),
        UniqueConstraint("server_scope", "device_id"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    server_scope: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
