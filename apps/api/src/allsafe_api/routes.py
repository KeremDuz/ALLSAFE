"""Enrollment, heartbeat, visibility and audit routes for the lab foundation."""

import hmac
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from allsafe_api.config import Settings
from allsafe_api.database import get_session
from allsafe_api.models import AuditEvent, Device, EnrollmentToken, new_id, utc_now
from allsafe_api.schemas import (
    AuditEventResponse,
    DeviceResponse,
    EnrollmentTokenRequest,
    EnrollmentTokenResponse,
    EnrollRequest,
    EnrollResponse,
    HeartbeatRequest,
    Inventory,
    ModuleResponse,
    as_utc,
)
from allsafe_api.security import (
    BearerCredentials,
    generate_token,
    hash_token,
    require_admin,
    unauthorized,
)

router = APIRouter()
DatabaseSession = Annotated[Session, Depends(get_session)]
Admin = Annotated[str, Depends(require_admin)]


def device_response(device: Device, settings: Settings) -> DeviceResponse:
    last_seen = as_utc(device.last_seen_at)
    cutoff = utc_now() - timedelta(seconds=settings.heartbeat_timeout_seconds)
    device_status = "offline"
    if device.revoked_at is not None:
        device_status = "revoked"
    elif last_seen is not None and last_seen >= cutoff:
        device_status = "online"
    return DeviceResponse(
        device_id=device.id,
        hostname=device.hostname,
        platform=device.platform,
        agent_version=device.agent_version,
        status=device_status,
        created_at=device.created_at,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
        inventory=Inventory.model_validate(device.inventory),
    )


@router.get("/health", tags=["Health"])
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready", tags=["Health"])
def readiness(session: DatabaseSession) -> dict[str, str]:
    try:
        # A reachable database without the required schema is not ready to serve.
        session.execute(select(Device.id).limit(1)).first()
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        ) from None
    return {"status": "ready"}


@router.get("/api/v1/modules", response_model=list[ModuleResponse], tags=["Modules"])
def list_modules(_: Admin) -> list[ModuleResponse]:
    return [
        ModuleResponse(
            id="core",
            name="ALLSAFE Core",
            status="available",
            capabilities=["device-enrollment", "heartbeat", "inventory", "audit"],
            description="Single-organization lab enrollment and device visibility.",
        ),
        ModuleResponse(
            id="phishcatch",
            name="PhishCatch",
            status="unavailable",
            capabilities=[],
            description="Upstream source is available; ALLSAFE integration is pending.",
        ),
        ModuleResponse(
            id="wazuh",
            name="Wazuh",
            status="unavailable",
            capabilities=[],
            description="Server and Indexer connectors are not implemented yet.",
        ),
        ModuleResponse(
            id="endpoint-management",
            name="Endpoint Management",
            status="planned",
            capabilities=[],
            description="Managed jobs and remote actions are planned after enrollment.",
        ),
    ]


@router.post(
    "/api/v1/enrollment-tokens",
    response_model=EnrollmentTokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Enrollment"],
)
def issue_enrollment_token(
    payload: EnrollmentTokenRequest, session: DatabaseSession, admin: Admin
) -> EnrollmentTokenResponse:
    now = utc_now()
    token = generate_token()
    token_id = new_id()
    expires_at = now + timedelta(seconds=payload.ttl_seconds)
    with session.begin():
        session.add(
            EnrollmentToken(
                id=token_id,
                token_hash=hash_token(token),
                label=payload.label,
                created_at=now,
                expires_at=expires_at,
            )
        )
        session.add(
            AuditEvent(
                event_type="enrollment_token.issued",
                actor=admin,
                target_id=token_id,
                occurred_at=now,
                details={"label": payload.label, "expires_at": expires_at.isoformat()},
            )
        )
    return EnrollmentTokenResponse(enrollment_token=token, expires_at=expires_at)


@router.post(
    "/api/v1/agent/enroll",
    response_model=EnrollResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Agent"],
)
def enroll_device(payload: EnrollRequest, session: DatabaseSession) -> EnrollResponse:
    now = utc_now()
    agent_token = generate_token()
    device_id = new_id()
    enrollment_hash = hash_token(payload.enrollment_token.get_secret_value())
    with session.begin():
        # Eligibility and redemption are one UPDATE. Parallel consumers cannot both
        # redeem the same token; the whole transaction rolls back if device creation fails.
        redeemed_id = session.execute(
            update(EnrollmentToken)
            .where(
                EnrollmentToken.token_hash == enrollment_hash,
                EnrollmentToken.redeemed_at.is_(None),
                EnrollmentToken.expires_at > now,
            )
            .values(redeemed_at=now)
            .returning(EnrollmentToken.id)
        ).scalar_one_or_none()
        if redeemed_id is None:
            raise unauthorized()
        session.add(
            Device(
                id=device_id,
                hostname=payload.hostname,
                platform=payload.platform,
                agent_version=payload.agent_version,
                agent_token_hash=hash_token(agent_token),
                created_at=now,
                inventory={},
            )
        )
        session.add(
            AuditEvent(
                event_type="device.enrolled",
                actor="device-enrollment",
                target_id=device_id,
                occurred_at=now,
                details={"enrollment_id": redeemed_id, "hostname": payload.hostname},
            )
        )
    return EnrollResponse(device_id=device_id, agent_token=agent_token)


@router.post("/api/v1/agent/heartbeat", response_model=DeviceResponse, tags=["Agent"])
def heartbeat(
    payload: HeartbeatRequest,
    request: Request,
    session: DatabaseSession,
    credentials: BearerCredentials,
) -> DeviceResponse:
    if credentials is None:
        raise unauthorized()
    supplied_hash = hash_token(credentials.credentials)
    with session.begin():
        device = session.get(Device, payload.device_id)
        if device is None or device.revoked_at is not None:
            raise unauthorized()
        if not hmac.compare_digest(device.agent_token_hash, supplied_hash):
            raise unauthorized()
        values = {"last_seen_at": utc_now(), "agent_version": payload.agent_version}
        if payload.inventory is not None:
            values["inventory"] = payload.inventory.model_dump(exclude_none=True)
        accepted_id = session.execute(
            update(Device)
            .where(
                Device.id == device.id,
                Device.revoked_at.is_(None),
                Device.agent_token_hash == supplied_hash,
            )
            .values(**values)
            .returning(Device.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if accepted_id is None:
            # Recheck in the UPDATE so a simultaneous revocation cannot be bypassed.
            raise unauthorized()
        session.refresh(device)
    return device_response(device, request.app.state.settings)


@router.get("/api/v1/devices", response_model=list[DeviceResponse], tags=["Devices"])
def list_devices(
    request: Request,
    session: DatabaseSession,
    _: Admin,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[DeviceResponse]:
    devices = session.scalars(select(Device).order_by(Device.created_at.desc()).limit(limit))
    return [device_response(device, request.app.state.settings) for device in devices]


@router.get("/api/v1/devices/{device_id}", response_model=DeviceResponse, tags=["Devices"])
def get_device(
    device_id: str, request: Request, session: DatabaseSession, _: Admin
) -> DeviceResponse:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device_response(device, request.app.state.settings)


@router.post("/api/v1/devices/{device_id}/revoke", response_model=DeviceResponse, tags=["Devices"])
def revoke_device(
    device_id: str, request: Request, session: DatabaseSession, admin: Admin
) -> DeviceResponse:
    now = utc_now()
    with session.begin():
        device = session.get(Device, device_id)
        if device is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
        revoked_id = session.execute(
            update(Device)
            .where(Device.id == device_id, Device.revoked_at.is_(None))
            .values(revoked_at=now)
            .returning(Device.id)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if revoked_id is not None:
            session.add(
                AuditEvent(
                    event_type="device.revoked",
                    actor=admin,
                    target_id=device_id,
                    occurred_at=now,
                    details={},
                )
            )
        session.refresh(device)
    return device_response(device, request.app.state.settings)


@router.get("/api/v1/audit-events", response_model=list[AuditEventResponse], tags=["Audit"])
def list_audit_events(
    session: DatabaseSession,
    _: Admin,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEventResponse]:
    events = session.scalars(
        select(AuditEvent).order_by(AuditEvent.occurred_at.desc()).limit(limit)
    )
    return [AuditEventResponse.model_validate(event) for event in events]
