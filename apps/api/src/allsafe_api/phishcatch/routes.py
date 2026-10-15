"""Central scan history and independent, explicitly authorized training decisions."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from allsafe_api.database import get_session
from allsafe_api.models import AuditEvent, new_id, utc_now
from allsafe_api.phishcatch.client import ConnectorFailure, PhishCatchClient
from allsafe_api.phishcatch.features import safe_features
from allsafe_api.phishcatch.models import PhishReview, PhishScan, TrainingApproval
from allsafe_api.phishcatch.schemas import ReviewRequest, ScanRequest, ScanResponse, display_url
from allsafe_api.schemas import as_utc
from allsafe_api.security import Actor, CurrentActor, hash_token, unauthorized

router = APIRouter(prefix="/api/v1/phishcatch", tags=["PhishCatch"])
Database = Annotated[Session, Depends(get_session)]


def human(actor: Actor, permission: str) -> None:
    if actor.user is None:
        raise unauthorized()
    if permission not in actor.permissions:
        raise HTTPException(status_code=403, detail="Permission denied")


def connector(request: Request) -> PhishCatchClient:
    return PhishCatchClient(
        request.app.state.settings, getattr(request.app.state, "phishcatch_transport", None)
    )


def accessible_scan(database: Session, actor: Actor, scan_id: str) -> PhishScan:
    human(actor, "scans:own:read")
    scan = database.get(PhishScan, scan_id)
    if scan is None or (scan.user_id != actor.id and "scans:read" not in actor.permissions):
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan


def latest_review(database: Session, scan: PhishScan) -> PhishReview | None:
    return database.scalar(
        select(PhishReview).where(
            PhishReview.scan_id == scan.id, PhishReview.revision == scan.review_revision
        )
    )


def scan_response(database: Session, scan: PhishScan) -> ScanResponse:
    review = latest_review(database, scan)
    return ScanResponse(
        id=scan.id,
        user_id=scan.user_id,
        client_request_id=scan.client_request_id,
        source=scan.source,
        url=scan.url_display,
        scan_status=scan.scan_status,
        analysis=scan.analysis,
        error_code=scan.error_code,
        created_at=as_utc(scan.created_at),
        completed_at=as_utc(scan.completed_at),
        verified_label=review.label if review else None,
        review_id=review.id if review else None,
        review_notes=review.notes if review else None,
        training_approved=database.get(TrainingApproval, scan.id) is not None,
        feature_count=len(scan.features),
    )


@router.get("/status")
def integration_status(actor: CurrentActor, request: Request) -> dict[str, Any]:
    human(actor, "scans:own:read")
    return connector(request).status()


@router.post("/scans", response_model=ScanResponse, status_code=201)
def submit_scan(
    payload: ScanRequest, actor: CurrentActor, database: Database, request: Request
) -> ScanResponse:
    human(actor, "scans:submit")
    request_id = str(payload.client_request_id)
    fingerprint = hash_token(payload.url)
    scan = PhishScan(
        id=new_id(),
        user_id=actor.id,
        client_request_id=request_id,
        source=payload.source,
        url_display=display_url(payload.url),
        url_hash=fingerprint,
        scan_status="pending",
        features={},
        review_revision=0,
    )
    try:
        with database.begin():
            database.add(scan)
            database.add(
                AuditEvent(
                    event_type="phishcatch.scan_submitted",
                    actor=actor.id,
                    target_id=scan.id,
                    details={"source": payload.source},
                )
            )
    except IntegrityError:
        database.rollback()
        existing = database.scalar(
            select(PhishScan).where(
                PhishScan.user_id == actor.id, PhishScan.client_request_id == request_id
            )
        )
        if existing is None:
            raise
        if existing.url_hash != fingerprint or existing.source != payload.source:
            raise HTTPException(
                status_code=409, detail="Request ID was already used for another scan"
            ) from None
        return scan_response(database, existing)
    try:
        result = connector(request).analyze(payload.url)
        analysis = result.analysis.model_dump(mode="json")
        upstream_status = result.analysis.scan_status
        if not result.analysis.stages or any(
            stage.status in {"failed", "unavailable", "skipped"} for stage in result.analysis.stages
        ):
            upstream_status = (
                "partial"
                if any(stage.status == "completed" for stage in result.analysis.stages)
                else "failed"
            )
        # A second service boundary enforces incomplete analysis semantics independently.
        if upstream_status != "complete" and analysis["final_verdict"] == "clean":
            analysis.update(
                final_verdict="unknown",
                confidence=None,
                malicious_probability=None,
                clean_probability=None,
            )
        analysis.update(
            url=scan.url_display, original_input=scan.url_display, normalized_url=scan.url_display
        )
        status = upstream_status
        analysis["scan_status"] = status
        features = safe_features(result.features)
        observation_id, feature_version, error_code = (
            result.analysis.observation_id,
            result.feature_version,
            None,
        )
    except ConnectorFailure as problem:
        analysis, features, observation_id, feature_version = None, {}, None, None
        status, error_code = "failed", problem.code
    # Do not hold a transaction open during the network request.
    database.execute(
        update(PhishScan)
        .where(PhishScan.id == scan.id)
        .values(
            analysis=analysis,
            features=features,
            observation_id=observation_id,
            feature_version=feature_version,
            scan_status=status,
            error_code=error_code,
            completed_at=utc_now(),
        )
    )
    database.add(
        AuditEvent(
            event_type="phishcatch.scan_completed",
            actor=actor.id,
            target_id=scan.id,
            details={"status": status},
        )
    )
    database.commit()
    database.refresh(scan)
    return scan_response(database, scan)


@router.get("/scans", response_model=list[ScanResponse])
def list_scans(
    actor: CurrentActor, database: Database, limit: Annotated[int, Query(ge=1, le=500)] = 100
) -> list[ScanResponse]:
    human(actor, "scans:own:read")
    query = select(PhishScan)
    if "scans:read" not in actor.permissions:
        query = query.where(PhishScan.user_id == actor.id)
    scans = database.scalars(
        query.order_by(PhishScan.created_at.desc(), PhishScan.id.desc()).limit(limit)
    ).all()
    return [scan_response(database, scan) for scan in scans]


@router.get("/scans/{scan_id}", response_model=ScanResponse)
def get_scan(scan_id: str, actor: CurrentActor, database: Database) -> ScanResponse:
    return scan_response(database, accessible_scan(database, actor, scan_id))


@router.post("/scans/{scan_id}/reviews", response_model=ScanResponse)
def review_scan(
    scan_id: str, payload: ReviewRequest, actor: CurrentActor, database: Database
) -> ScanResponse:
    human(actor, "scans:review")
    with database.begin():
        # UPDATE serializes this scan's review/approval decisions on SQLite and PostgreSQL.
        database.execute(
            update(PhishScan)
            .where(PhishScan.id == scan_id)
            .values(review_revision=PhishScan.review_revision + 1)
        )
        scan = accessible_scan(database, actor, scan_id)
        if scan.scan_status == "pending":
            raise HTTPException(status_code=409, detail="Analysis is still pending")
        database.execute(delete(TrainingApproval).where(TrainingApproval.scan_id == scan_id))
        database.add(
            PhishReview(
                id=new_id(),
                scan_id=scan.id,
                revision=scan.review_revision,
                label=payload.label,
                notes=payload.notes,
                reviewer_id=actor.id,
            )
        )
        database.add(
            AuditEvent(
                event_type="phishcatch.review_created",
                actor=actor.id,
                target_id=scan.id,
                details={"label": payload.label},
            )
        )
    return scan_response(database, scan)


@router.post("/scans/{scan_id}/training-approval", response_model=ScanResponse)
def approve_training(scan_id: str, actor: CurrentActor, database: Database) -> ScanResponse:
    human(actor, "training:approve")
    with database.begin():
        database.execute(
            update(PhishScan)
            .where(PhishScan.id == scan_id)
            .values(review_revision=PhishScan.review_revision)
        )
        scan = accessible_scan(database, actor, scan_id)
        review = latest_review(database, scan)
        if (
            review is None
            or review.label == "uncertain"
            or not scan.features
            or scan.feature_version != "phishcatch-v1"
        ):
            raise HTTPException(
                status_code=409,
                detail="A verified clean/malicious label and numeric features are required",
            )
        if database.get(TrainingApproval, scan.id) is None:
            database.add(
                TrainingApproval(
                    scan_id=scan.id,
                    review_id=review.id,
                    approver_id=actor.id,
                    label=1 if review.label == "malicious" else 0,
                    feature_version=scan.feature_version,
                    features=dict(scan.features),
                )
            )
            database.add(
                AuditEvent(
                    event_type="phishcatch.training_approved",
                    actor=actor.id,
                    target_id=scan.id,
                    details={},
                )
            )
    return scan_response(database, scan)


@router.delete("/scans/{scan_id}/training-approval", status_code=204)
def remove_training_approval(scan_id: str, actor: CurrentActor, database: Database) -> Response:
    human(actor, "training:approve")
    with database.begin():
        database.execute(
            update(PhishScan)
            .where(PhishScan.id == scan_id)
            .values(review_revision=PhishScan.review_revision)
        )
        accessible_scan(database, actor, scan_id)
        database.execute(delete(TrainingApproval).where(TrainingApproval.scan_id == scan_id))
        database.add(
            AuditEvent(
                event_type="phishcatch.training_removed",
                actor=actor.id,
                target_id=scan_id,
                details={},
            )
        )
    return Response(status_code=204)


@router.get("/training-export")
def export_training(
    actor: CurrentActor,
    database: Database,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> dict[str, Any]:
    human(actor, "training:approve")
    approvals = database.scalars(
        select(TrainingApproval)
        .order_by(TrainingApproval.created_at, TrainingApproval.scan_id)
        .limit(limit)
    ).all()
    response.headers["Cache-Control"] = "no-store"
    return {
        "feature_version": "phishcatch-v1",
        "samples": [
            {"label": approval.label, "features": approval.features} for approval in approvals
        ],
    }
