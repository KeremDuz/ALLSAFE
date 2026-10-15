"""Human web session requests and authenticated device consent decisions."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, WebSocket
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from allsafe_api.database import get_session
from allsafe_api.models import new_id, utc_now
from allsafe_api.remote_desktop.models import DesktopSession
from allsafe_api.remote_desktop.relay import connect_agent, connect_viewer
from allsafe_api.remote_desktop.schemas import (
    CreateDesktopSession,
    DesktopDecision,
    DesktopSessionResponse,
    PendingDesktopSessions,
)
from allsafe_api.remote_desktop.service import (
    CONSENT_SECONDS,
    NONTERMINAL,
    SESSION_SECONDS,
    audit,
    expire,
    finish,
    lock_device,
    owner_valid,
    require_device,
)
from allsafe_api.schemas import as_utc
from allsafe_api.security import Actor, BearerCredentials, CurrentActor, hash_token, unauthorized

router = APIRouter(tags=["Remote desktop"])
Database = Annotated[Session, Depends(get_session)]


def desktop_operator(actor: CurrentActor) -> Actor:
    if (
        actor.user is None
        or actor.session_channel != "web"
        or actor.session_id is None
        or "desktop:manage" not in actor.permissions
    ):
        raise HTTPException(status_code=403, detail="A human administrator web session is required")
    return actor


Operator = Annotated[Actor, Depends(desktop_operator)]


def owned(database: Session, session_id: UUID, actor: Actor) -> DesktopSession:
    desktop = database.get(DesktopSession, str(session_id))
    if desktop is None or desktop.requester_session_id != actor.session_id:
        raise HTTPException(status_code=404, detail="Desktop session not found")
    return desktop


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post(
    "/api/v1/remote-desktop/sessions", status_code=201, response_model=DesktopSessionResponse
)
def request_session(
    payload: CreateDesktopSession,
    actor: Operator,
    database: Database,
    request: Request,
    response: Response,
) -> DesktopSessionResponse:
    no_store(response)
    try:
        with database.begin():
            device = lock_device(database, str(payload.device_id))
            if device is None:
                raise HTTPException(status_code=404, detail="Device not found")
            last_seen = as_utc(device.last_seen_at)
            cutoff = utc_now() - timedelta(
                seconds=request.app.state.settings.heartbeat_timeout_seconds
            )
            if (
                device.revoked_at is not None
                or device.platform != "windows"
                or last_seen is None
                or last_seen < cutoff
            ):
                raise HTTPException(status_code=409, detail="An online Windows device is required")
            existing = database.scalar(
                select(DesktopSession).where(DesktopSession.active_device_id == device.id)
            )
            if existing:
                expire(database, existing)
                if existing.status in NONTERMINAL:
                    if owner_valid(database, existing):
                        raise HTTPException(status_code=409, detail="Device already has a session")
                    finish(database, existing, "operator_unavailable")
            now = utc_now()
            assert actor.user is not None and actor.session_id is not None
            desktop = DesktopSession(
                id=new_id(),
                device_id=device.id,
                active_device_id=device.id,
                requester_session_id=actor.session_id,
                operator_id=actor.id,
                operator_name=actor.user.display_name,
                reason=payload.reason,
                mode=payload.mode,
                status="pending",
                created_at=now,
                expires_at=now + timedelta(seconds=CONSENT_SECONDS),
            )
            database.add(desktop)
            audit(database, desktop, "requested")
            database.flush()
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Device already has a session") from None
    return DesktopSessionResponse.model_validate(desktop)


@router.get("/api/v1/remote-desktop/sessions/{session_id}", response_model=DesktopSessionResponse)
def get_session_state(
    session_id: UUID, actor: Operator, database: Database, response: Response
) -> DesktopSessionResponse:
    no_store(response)
    with database.begin():
        desktop = owned(database, session_id, actor)
        expire(database, desktop)
    return DesktopSessionResponse.model_validate(desktop)


@router.post(
    "/api/v1/remote-desktop/sessions/{session_id}/close", response_model=DesktopSessionResponse
)
def close_session(
    session_id: UUID, actor: Operator, database: Database, response: Response
) -> DesktopSessionResponse:
    no_store(response)
    with database.begin():
        desktop = owned(database, session_id, actor)
        expire(database, desktop)
        finish(database, desktop, "operator_closed")
    return DesktopSessionResponse.model_validate(desktop)


@router.get("/api/v1/agent/remote-desktop/pending", response_model=PendingDesktopSessions)
def pending_sessions(
    device_id: Annotated[UUID, Query()],
    credentials: BearerCredentials,
    database: Database,
    response: Response,
) -> PendingDesktopSessions:
    no_store(response)
    if credentials is None:
        raise unauthorized()
    with database.begin():
        require_device(database, str(device_id), hash_token(credentials.credentials))
        desktop = database.scalar(
            select(DesktopSession).where(DesktopSession.active_device_id == str(device_id))
        )
        if desktop:
            expire(database, desktop)
            if desktop.status in NONTERMINAL and not owner_valid(database, desktop):
                finish(database, desktop, "operator_unavailable")
        items = (
            [DesktopSessionResponse.model_validate(desktop)]
            if (desktop and desktop.status == "pending")
            else []
        )
    return PendingDesktopSessions(sessions=items)


@router.post(
    "/api/v1/agent/remote-desktop/sessions/{session_id}/decision",
    response_model=DesktopSessionResponse,
)
def decide_session(
    session_id: UUID,
    payload: DesktopDecision,
    credentials: BearerCredentials,
    database: Database,
    response: Response,
) -> DesktopSessionResponse:
    no_store(response)
    if credentials is None:
        raise unauthorized()
    with database.begin():
        require_device(database, str(payload.device_id), hash_token(credentials.credentials))
        desktop = database.get(DesktopSession, str(session_id))
        if desktop is None or desktop.device_id != str(payload.device_id):
            raise HTTPException(status_code=404, detail="Desktop session not found")
        expire(database, desktop)
        if desktop.status in NONTERMINAL and not owner_valid(database, desktop):
            finish(database, desktop, "operator_unavailable")
        if desktop.status != "pending":
            # Return terminal state without reversing it, including repeated decisions.
            return DesktopSessionResponse.model_validate(desktop)
        accepted = database.execute(
            update(DesktopSession)
            .where(
                DesktopSession.id == desktop.id,
                DesktopSession.status == "pending",
                DesktopSession.expires_at > utc_now(),
            )
            .values(
                status="approved" if payload.approved else "denied",
                expires_at=(
                    utc_now() + timedelta(seconds=SESSION_SECONDS)
                    if payload.approved
                    else desktop.expires_at
                ),
                active_device_id=desktop.device_id if payload.approved else None,
                closed_reason=None if payload.approved else "user_denied",
            )
            .execution_options(synchronize_session=False)
            .returning(DesktopSession.id)
        ).scalar_one_or_none()
        database.refresh(desktop)
        if accepted:
            audit(database, desktop, "approved" if payload.approved else "denied")
        else:
            expire(database, desktop)
    return DesktopSessionResponse.model_validate(desktop)


@router.websocket("/api/v1/remote-desktop/sessions/{session_id}/viewer")
async def viewer(session_id: UUID, websocket: WebSocket) -> None:
    await connect_viewer(websocket, str(session_id))


@router.websocket("/api/v1/agent/remote-desktop/sessions/{session_id}/stream")
async def agent(session_id: UUID, websocket: WebSocket) -> None:
    await connect_agent(websocket, str(session_id))
