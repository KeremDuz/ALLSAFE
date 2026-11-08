"""Transactional reservations and continuously checked authorization."""

import hmac

from fastapi import FastAPI
from sqlalchemy import inspect, select, update
from sqlalchemy.orm import Session

from allsafe_api.managed_access.models import TerminalSession
from allsafe_api.models import AuditEvent, Device, User, UserSession, utc_now
from allsafe_api.schemas import as_utc
from allsafe_api.security import ROLE_PERMISSIONS

NONTERMINAL = ("pending", "connecting", "active")
PENDING_SECONDS = 60
SESSION_SECONDS = 600


def audit(database: Session, terminal: TerminalSession, event: str) -> None:
    database.add(
        AuditEvent(
            event_type=f"managed_access.terminal.{event}",
            actor=terminal.operator_id,
            target_id=terminal.id,
            details={
                "device_id": terminal.device_id,
                "account": terminal.account,
                "kind": "ssh",
                "closed_reason": terminal.closed_reason,
            },
        )
    )


def finish(
    database: Session, terminal: TerminalSession, reason: str, *, expired: bool = False
) -> None:
    changed = database.execute(
        update(TerminalSession)
        .where(TerminalSession.id == terminal.id, TerminalSession.status.in_(NONTERMINAL))
        .values(
            status="expired" if expired else "closed", active_device_id=None, closed_reason=reason
        )
        .execution_options(synchronize_session=False)
        .returning(TerminalSession.id)
    ).scalar_one_or_none()
    database.refresh(terminal)
    if changed:
        audit(database, terminal, "expired" if expired else "closed")


def expire(database: Session, terminal: TerminalSession) -> None:
    deadline = as_utc(terminal.expires_at)
    if deadline is not None and deadline <= utc_now():
        finish(database, terminal, "session_timeout", expired=True)


def owner_valid(database: Session, terminal: TerminalSession, verifier: str | None = None) -> bool:
    login = database.get(UserSession, terminal.requester_session_id)
    user = database.get(User, terminal.operator_id)
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
        and "remote-access:manage" in ROLE_PERMISSIONS.get(user.role, frozenset())
        and (verifier is None or hmac.compare_digest(login.token_hash, verifier))
    )


def validate(database: Session, terminal: TerminalSession, verifier: str | None = None) -> bool:
    expire(database, terminal)
    if terminal.status not in NONTERMINAL:
        return False
    if not owner_valid(database, terminal, verifier):
        finish(database, terminal, "operator_unavailable")
        return False
    device = database.get(Device, terminal.device_id)
    if device is None or device.revoked_at is not None or device.platform != "windows":
        finish(database, terminal, "device_unavailable")
        return False
    if not hmac.compare_digest(device.agent_token_hash, terminal.credential_hash):
        finish(database, terminal, "device_credentials_changed")
        return False
    return True


def close_stale_sessions(application: FastAPI) -> None:
    if not inspect(application.state.engine).has_table(TerminalSession.__tablename__):
        return
    with application.state.session_factory.begin() as database:
        for terminal in database.scalars(
            select(TerminalSession).where(TerminalSession.status.in_(NONTERMINAL))
        ):
            finish(database, terminal, "server_restart")
