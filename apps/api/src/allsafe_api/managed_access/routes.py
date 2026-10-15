"""Administrator web sessions can reach only locally provisioned SSH/RDP targets."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from allsafe_api.database import get_session
from allsafe_api.managed_access.configuration import (
    ConfigurationError,
    ResolvedProfile,
    resolve_profile,
)
from allsafe_api.managed_access.models import TerminalSession
from allsafe_api.managed_access.schemas import (
    AccessStatus,
    CreateTerminalSession,
    Reason,
    ServiceStatus,
    TerminalSessionResponse,
)
from allsafe_api.managed_access.service import (
    NONTERMINAL,
    PENDING_SECONDS,
    audit,
    expire,
    finish,
    validate,
)
from allsafe_api.managed_access.transport import connect
from allsafe_api.models import AuditEvent, Device, new_id, utc_now
from allsafe_api.remote_desktop.service import lock_device
from allsafe_api.security import Actor, CurrentActor

router = APIRouter(prefix="/api/v1/managed-access", tags=["Managed remote access"])
Database = Annotated[Session, Depends(get_session)]


def operator(actor: CurrentActor) -> Actor:
    if (
        actor.user is None
        or actor.session_channel != "web"
        or actor.session_id is None
        or "remote-access:manage" not in actor.permissions
    ):
        raise HTTPException(status_code=403, detail="A human administrator web session is required")
    return actor


Operator = Annotated[Actor, Depends(operator)]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def configured_profile(request: Request, device_id: str) -> ResolvedProfile | None:
    try:
        return resolve_profile(request.app.state.settings.managed_access_config_file, device_id)
    except ConfigurationError:
        raise HTTPException(
            status_code=503, detail="Managed access configuration unavailable"
        ) from None


def require_device(database: Session, device_id: str) -> Device:
    device = lock_device(database, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if device.revoked_at is not None or device.platform != "windows":
        raise HTTPException(status_code=409, detail="An enrolled Windows device is required")
    # A stale heartbeat does not preclude SSH repair of a stopped device agent.
    return device


def owned(database: Session, session_id: str, actor: Actor) -> TerminalSession:
    terminal = database.get(TerminalSession, session_id)
    if terminal is None or terminal.requester_session_id != actor.session_id:
        raise HTTPException(status_code=404, detail="Terminal session not found")
    return terminal


@router.get("/devices/{device_id}", response_model=AccessStatus)
def access_status(
    device_id: UUID, actor: Operator, database: Database, request: Request, response: Response
) -> AccessStatus:
    no_store(response)
    device = database.get(Device, str(device_id))
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    status = AccessStatus(
        device_id=str(device_id),
        terminal=ServiceStatus(configured=False),
        rdp=ServiceStatus(configured=False),
    )
    if device.revoked_at is not None or device.platform != "windows":
        status.error_code = "device_unavailable"
        return status
    try:
        resolved = resolve_profile(
            request.app.state.settings.managed_access_config_file, str(device_id)
        )
    except ConfigurationError:
        status.error_code = "configuration_unavailable"
        return status
    if resolved:
        profile = resolved.profile
        status.terminal = ServiceStatus(
            configured=profile.ssh is not None,
            account=profile.ssh.username if profile.ssh else None,
        )
        status.rdp = ServiceStatus(
            configured=profile.rdp is not None,
            account=profile.rdp.username if profile.rdp else None,
        )
    return status


@router.post("/terminal-sessions", status_code=201, response_model=TerminalSessionResponse)
def request_terminal(
    payload: CreateTerminalSession,
    actor: Operator,
    database: Database,
    request: Request,
    response: Response,
) -> TerminalSessionResponse:
    no_store(response)
    resolved = configured_profile(request, str(payload.device_id))
    if resolved is None or resolved.profile.ssh is None:
        raise HTTPException(status_code=409, detail="SSH access is not configured for this device")
    try:
        with database.begin():
            device = require_device(database, str(payload.device_id))
            existing = database.scalar(
                select(TerminalSession).where(TerminalSession.active_device_id == device.id)
            )
            if existing:
                validate(database, existing)
                if existing.status in NONTERMINAL:
                    raise HTTPException(
                        status_code=409, detail="Device already has a terminal session"
                    )
            now = utc_now()
            assert actor.session_id is not None
            terminal = TerminalSession(
                id=new_id(),
                device_id=device.id,
                active_device_id=device.id,
                requester_session_id=actor.session_id,
                operator_id=actor.id,
                reason=payload.reason,
                account=resolved.profile.ssh.username,
                credential_hash=device.agent_token_hash,
                profile_fingerprint=resolved.fingerprint,
                cols=payload.cols,
                rows=payload.rows,
                status="pending",
                created_at=now,
                expires_at=now + timedelta(seconds=PENDING_SECONDS),
            )
            database.add(terminal)
            audit(database, terminal, "requested")
            database.flush()
    except IntegrityError:
        raise HTTPException(
            status_code=409, detail="Device already has a terminal session"
        ) from None
    return TerminalSessionResponse.model_validate(terminal)


@router.get("/terminal-sessions/{session_id}", response_model=TerminalSessionResponse)
def terminal_status(
    session_id: UUID, actor: Operator, database: Database, response: Response
) -> TerminalSessionResponse:
    no_store(response)
    with database.begin():
        terminal = owned(database, str(session_id), actor)
        validate(database, terminal)
    return TerminalSessionResponse.model_validate(terminal)


@router.post("/terminal-sessions/{session_id}/close", response_model=TerminalSessionResponse)
def close_terminal(
    session_id: UUID, actor: Operator, database: Database, response: Response
) -> TerminalSessionResponse:
    no_store(response)
    with database.begin():
        terminal = owned(database, str(session_id), actor)
        expire(database, terminal)
        finish(database, terminal, "operator_closed")
    return TerminalSessionResponse.model_validate(terminal)


@router.websocket("/terminal-sessions/{session_id}/stream")
async def terminal_stream(session_id: UUID, websocket: WebSocket) -> None:
    await connect(websocket, str(session_id))


@router.post("/devices/{device_id}/rdp-profile")
def rdp_profile(
    device_id: UUID, payload: Reason, actor: Operator, database: Database, request: Request
) -> Response:
    resolved = configured_profile(request, str(device_id))
    if resolved is None or resolved.profile.rdp is None:
        raise HTTPException(status_code=409, detail="RDP access is not configured for this device")
    profile = resolved.profile
    assert profile.rdp is not None
    host = f"[{profile.host}]" if ":" in profile.host else profile.host
    lines = [
        f"full address:s:{host}:{profile.rdp.port}",
        "prompt for credentials:i:1",
        "enablecredsspsupport:i:1",
        "authentication level:i:1",
        "redirectclipboard:i:0",
        "redirectprinters:i:0",
        "redirectcomports:i:0",
        "redirectsmartcards:i:0",
        "redirectwebauthn:i:0",
        "usbdevicestoredirect:s:",
        "devicestoredirect:s:",
        "camerastoredirect:s:",
        "drivestoredirect:s:",
        "audiocapturemode:i:0",
        "autoreconnection enabled:i:0",
        "gatewayusagemethod:i:0",
        "administrative session:i:0",
    ]
    if profile.rdp.username:
        lines.append(f"username:s:{profile.rdp.username}")
    with database.begin():
        require_device(database, str(device_id))
        database.add(
            AuditEvent(
                event_type="managed_access.rdp.profile_downloaded",
                actor=actor.id,
                target_id=str(device_id),
                details={
                    "device_id": str(device_id),
                    "kind": "rdp",
                    "account": profile.rdp.username,
                    "reason": payload.reason,
                },
            )
        )
    # A native client handoff is not an API-controlled RDP session. No passwords,
    # claim of connection success or subsequent revocation guarantee is embedded.
    return Response(
        content=b"\xff\xfe" + ("\r\n".join(lines) + "\r\n").encode("utf-16-le"),
        media_type="application/x-rdp",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": f'attachment; filename="allsafe-{device_id}.rdp"',
        },
    )
