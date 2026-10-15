"""Transactional consent and lifetime rules, shared by HTTP and the relay."""

import hmac

from fastapi import FastAPI, HTTPException
from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from allsafe_api.models import AuditEvent, Device, User, UserSession, utc_now
from allsafe_api.remote_desktop.models import DesktopSession
from allsafe_api.schemas import as_utc
from allsafe_api.security import ROLE_PERMISSIONS

NONTERMINAL = ("pending", "approved", "active")
CONSENT_SECONDS = 120
SESSION_SECONDS = 600


def audit(database: Session, desktop: DesktopSession, event: str) -> None:
    database.add(
        AuditEvent(
            event_type=f"desktop.{event}",
            actor=desktop.operator_id,
            target_id=desktop.id,
            details={
                "device_id": desktop.device_id,
                "mode": desktop.mode,
                "closed_reason": desktop.closed_reason,
            },
        )
    )


def finish(
    database: Session, desktop: DesktopSession, reason: str, *, expired: bool = False
) -> None:
    if desktop.status not in NONTERMINAL:
        return
    accepted = database.execute(
        update(DesktopSession)
        .where(DesktopSession.id == desktop.id, DesktopSession.status.in_(NONTERMINAL))
        .values(
            status="expired" if expired else "closed", active_device_id=None, closed_reason=reason
        )
        .execution_options(synchronize_session=False)
        .returning(DesktopSession.id)
    ).scalar_one_or_none()
    database.refresh(desktop)
    if accepted:
        audit(database, desktop, "expired" if expired else "closed")


def expire(database: Session, desktop: DesktopSession) -> None:
    deadline = as_utc(desktop.expires_at)
    if deadline is not None and deadline <= utc_now():
        finish(
            database,
            desktop,
            "consent_timeout" if desktop.status == "pending" else "session_timeout",
            expired=True,
        )


def owner_valid(database: Session, desktop: DesktopSession) -> bool:
    login = database.get(UserSession, desktop.requester_session_id)
    user = database.get(User, desktop.operator_id)
    expiry = as_utc(login.expires_at) if login else None
    return bool(
        login
        and user
        and user.active
        and login.user_id == user.id
        and login.channel == "web"
        and login.revoked_at is None
        and expiry
        and expiry > utc_now()
        and "desktop:manage" in ROLE_PERMISSIONS.get(user.role, frozenset())
    )


def device_valid(device: Device | None, supplied_hash: str) -> bool:
    return bool(
        device
        and device.revoked_at is None
        and device.platform == "windows"
        and hmac.compare_digest(device.agent_token_hash, supplied_hash)
    )


def lock_device(database: Session, device_id: str) -> Device | None:
    # An UPDATE obtains the write/row lock on SQLite and PostgreSQL before reading
    # reservations. The unique nullable reservation is a second database guard.
    database.execute(
        update(Device).where(Device.id == device_id).values(agent_version=Device.agent_version)
    )
    return database.get(Device, device_id)


def require_device(database: Session, device_id: str, supplied_hash: str) -> Device:
    device = lock_device(database, device_id)
    if not device_valid(device, supplied_hash):
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    assert device is not None
    return device


def close_device_sessions(database: Session, device_id: str, reason: str) -> None:
    for desktop in database.scalars(
        select(DesktopSession).where(DesktopSession.active_device_id == device_id)
    ):
        finish(database, desktop, reason)


def close_stale_sessions(application: FastAPI) -> None:
    # A relay cannot survive a process restart. Never silently reconnect to an old
    # consent grant, even when the SQL expiry has not elapsed.
    if not inspect(application.state.engine).has_table(DesktopSession.__tablename__):
        # Preserve liveness/readiness diagnostics when migrations have not run.
        return
    with application.state.session_factory.begin() as database:
        for desktop in database.scalars(
            select(DesktopSession).where(DesktopSession.status.in_(NONTERMINAL))
        ):
            finish(database, desktop, "server_restart")
