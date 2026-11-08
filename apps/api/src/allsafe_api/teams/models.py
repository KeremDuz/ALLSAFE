"""Team-scoped records; access is derived from membership, never from client input."""

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from allsafe_api.models import Base, new_id, utc_now


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (UniqueConstraint("team_id", "user_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    team_role: Mapped[str] = mapped_column(String(16), nullable=False, default="member")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkItem(Base):
    __tablename__ = "team_work_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    priority: Mapped[str] = mapped_column(String(8), nullable=False, default="medium")
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class TeamDashboard(Base):
    """Only approved widget identifiers and filter values are stored; no client code."""

    __tablename__ = "team_dashboards"

    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id"), primary_key=True)
    widgets: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    filters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    updated_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
