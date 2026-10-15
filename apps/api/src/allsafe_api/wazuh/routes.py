"""Read Wazuh evidence and maintain explicit local device identity bindings."""

import hashlib
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from allsafe_api.database import get_session
from allsafe_api.models import AuditEvent, Device, new_id, utc_now
from allsafe_api.schemas import RequestModel, as_utc
from allsafe_api.security import Actor, CurrentActor, unauthorized
from allsafe_api.wazuh.client import WazuhConnector
from allsafe_api.wazuh.models import WazuhMapping


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/wazuh", tags=["Wazuh"], dependencies=[Depends(no_store)])
Database = Annotated[Session, Depends(get_session)]


class MappingRequest(RequestModel):
    device_id: UUID
    agent_id: str = Field(min_length=1, max_length=32, pattern=r"^[0-9]+$")


def human(actor: Actor, permission: str) -> None:
    if actor.user is None:
        raise unauthorized()
    if permission not in actor.permissions:
        raise HTTPException(status_code=403, detail="Permission denied")


def connector(request: Request) -> WazuhConnector:
    return WazuhConnector(
        request.app.state.settings,
        getattr(request.app.state, "wazuh_server_transport", None),
        getattr(request.app.state, "wazuh_indexer_transport", None),
    )


def server_scope(request: Request) -> str | None:
    origin = request.app.state.settings.wazuh_server_url
    if not origin:
        return None
    parsed = urlsplit(origin)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    canonical = f"{parsed.scheme.lower()}|{parsed.hostname.lower()}|{port}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def mappings(database: Session, scope: str | None) -> list[WazuhMapping]:
    if scope is None:
        return []
    return list(database.scalars(select(WazuhMapping).where(WazuhMapping.server_scope == scope)))


def mapping_response(mapping: WazuhMapping) -> dict[str, Any]:
    return {
        "id": mapping.id,
        "device_id": mapping.device_id,
        "agent_id": mapping.agent_id,
        "server_scope": mapping.server_scope,
        "created_at": as_utc(mapping.created_at),
    }


def enrich(result: dict[str, Any], bindings: list[WazuhMapping]) -> dict[str, Any]:
    device_by_agent = {binding.agent_id: binding.device_id for binding in bindings}
    if result["items"] is not None:
        for item in result["items"]:
            item["device_id"] = device_by_agent.get(item.get("agent_id"))
    return result


@router.get("/status")
def integration_status(actor: CurrentActor, request: Request) -> dict[str, Any]:
    human(actor, "wazuh:read")
    return connector(request).status()


@router.get("/agents")
def list_agents(
    actor: CurrentActor,
    database: Database,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=10000),
) -> dict[str, Any]:
    human(actor, "wazuh:read")
    result = connector(request).agents(limit=limit, offset=offset)
    return enrich(result, mappings(database, server_scope(request)))


@router.get("/alerts")
def list_alerts(
    actor: CurrentActor,
    database: Database,
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    hours: int = Query(default=24, ge=1, le=168),
    device_id: UUID | None = None,
) -> dict[str, Any]:
    human(actor, "wazuh:read")
    bindings = mappings(database, server_scope(request))
    agent_id = None
    if device_id is not None:
        binding = next((item for item in bindings if item.device_id == str(device_id)), None)
        if binding is None:
            raise HTTPException(status_code=404, detail="Device has no Wazuh mapping")
        agent_id = binding.agent_id
    result = connector(request).alerts(limit=limit, hours=hours, agent_id=agent_id)
    return enrich(result, bindings)


@router.get("/mappings")
def list_mappings(
    actor: CurrentActor, database: Database, request: Request
) -> list[dict[str, Any]]:
    human(actor, "wazuh:manage")
    return [mapping_response(item) for item in mappings(database, server_scope(request))]


@router.post("/mappings", status_code=201)
def create_mapping(
    payload: MappingRequest, actor: CurrentActor, database: Database, request: Request
) -> dict[str, Any]:
    human(actor, "wazuh:manage")
    if not payload.agent_id.strip("0"):
        raise HTTPException(status_code=422, detail="Wazuh manager cannot be mapped as an endpoint")
    scope = server_scope(request)
    if scope is None:
        raise HTTPException(status_code=503, detail="Wazuh server is not configured")
    verification = connector(request).agents(limit=1, agent_id=payload.agent_id)
    if verification["state"] != "connected":
        raise HTTPException(status_code=503, detail="Wazuh agent verification unavailable")
    if not any(item["agent_id"] == payload.agent_id for item in verification["items"]):
        raise HTTPException(status_code=404, detail="Wazuh agent not found")
    device_id = str(payload.device_id)
    try:
        with database.begin():
            if database.get(Device, device_id) is None:
                raise HTTPException(status_code=404, detail="Device not found")
            existing = database.scalar(
                select(WazuhMapping).where(
                    WazuhMapping.server_scope == scope, WazuhMapping.agent_id == payload.agent_id
                )
            )
            if existing and existing.device_id == device_id:
                return mapping_response(existing)
            mapping = WazuhMapping(
                id=new_id(),
                server_scope=scope,
                device_id=device_id,
                agent_id=payload.agent_id,
                created_by=actor.id,
                created_at=utc_now(),
            )
            database.add(mapping)
            database.add(
                AuditEvent(
                    event_type="wazuh.mapping.created",
                    actor=actor.id,
                    target_id=device_id,
                    details={"mapping_id": mapping.id, "agent_id": payload.agent_id},
                )
            )
            database.flush()
            result = mapping_response(mapping)
        return result
    except IntegrityError:
        existing = database.scalar(
            select(WazuhMapping).where(
                WazuhMapping.server_scope == scope, WazuhMapping.agent_id == payload.agent_id
            )
        )
        if existing and existing.device_id == device_id:
            return mapping_response(existing)
        raise HTTPException(
            status_code=409, detail="Device or Wazuh agent already mapped"
        ) from None


@router.delete("/mappings/{mapping_id}", status_code=204)
def delete_mapping(
    mapping_id: UUID, actor: CurrentActor, database: Database, request: Request
) -> Response:
    human(actor, "wazuh:manage")
    with database.begin():
        mapping = database.get(WazuhMapping, str(mapping_id))
        if mapping is None or mapping.server_scope != server_scope(request):
            raise HTTPException(status_code=404, detail="Mapping not found")
        database.add(
            AuditEvent(
                event_type="wazuh.mapping.removed",
                actor=actor.id,
                target_id=mapping.device_id,
                details={"mapping_id": mapping.id, "agent_id": mapping.agent_id},
            )
        )
        database.delete(mapping)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
