"""Team workspaces: administrators own membership, team roles scope everything else."""

from collections import Counter
from datetime import date, timedelta
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from allsafe_api.database import get_session
from allsafe_api.models import AuditEvent, User, utc_now
from allsafe_api.schemas import as_utc
from allsafe_api.security import Actor, CurrentActor, unauthorized
from allsafe_api.teams.models import Team, TeamDashboard, TeamMembership, WorkItem
from allsafe_api.teams.schemas import (
    DEFAULT_WIDGETS,
    DashboardFilters,
    DashboardRequest,
    DashboardResponse,
    MemberResponse,
    MembershipRequest,
    OwnerLoad,
    TeamDetailResponse,
    TeamRequest,
    TeamResponse,
    TeamSummaryResponse,
    TeamUpdateRequest,
    WorkItemRequest,
    WorkItemResponse,
    WorkItemUpdateRequest,
)


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/v1/teams", tags=["Teams"], dependencies=[Depends(no_store)])
Database = Annotated[Session, Depends(get_session)]
Access = Literal["member", "lead", "manager", "admin"]
LEADERSHIP: frozenset[str] = frozenset({"lead", "manager", "admin"})
WORK_STATUSES = ("open", "in_progress", "blocked", "done")


def human(actor: Actor) -> str:
    if actor.user is None:
        raise unauthorized()
    return actor.id


def is_admin(actor: Actor) -> bool:
    return "teams:manage" in actor.permissions


def require_admin(actor: Actor) -> None:
    human(actor)
    if not is_admin(actor):
        raise HTTPException(status_code=403, detail="Permission denied")


def team_access(database: Session, actor: Actor, team_id: UUID) -> tuple[Team, Access]:
    """Non-members get 404 so team names and existence are not disclosed."""
    user_id = human(actor)
    team = database.get(Team, str(team_id))
    if team is not None:
        if is_admin(actor):
            return team, "admin"
        role = database.scalar(
            select(TeamMembership.team_role).where(
                TeamMembership.team_id == team.id, TeamMembership.user_id == user_id
            )
        )
        if role is not None:
            return team, role  # type: ignore[return-value]
    raise HTTPException(status_code=404, detail="Team not found")


def require_leadership(access: Access) -> None:
    if access not in LEADERSHIP:
        raise HTTPException(status_code=403, detail="Permission denied")


def audit(database: Session, actor: Actor, event: str, target: str, **details: object) -> None:
    database.add(AuditEvent(event_type=event, actor=actor.id, target_id=target, details=details))


def team_response(database: Session, team: Team, access: Access) -> TeamResponse:
    members = database.scalar(
        select(func.count()).select_from(TeamMembership).where(TeamMembership.team_id == team.id)
    )
    open_items = database.scalar(
        select(func.count())
        .select_from(WorkItem)
        .where(WorkItem.team_id == team.id, WorkItem.status != "done")
    )
    return TeamResponse(
        id=team.id,
        name=team.name,
        description=team.description,
        created_at=as_utc(team.created_at),
        my_role=access,
        member_count=members or 0,
        open_items=open_items or 0,
    )


def item_response(item: WorkItem) -> WorkItemResponse:
    return WorkItemResponse(
        id=item.id,
        team_id=item.team_id,
        title=item.title,
        description=item.description,
        status=item.status,  # type: ignore[arg-type]
        priority=item.priority,  # type: ignore[arg-type]
        owner_id=item.owner_id,
        due_date=item.due_date,
        created_by=item.created_by,
        created_at=as_utc(item.created_at),
        updated_at=as_utc(item.updated_at),
    )


def require_member(database: Session, team_id: str, user_id: str | None) -> None:
    if user_id is None:
        return
    exists = database.scalar(
        select(TeamMembership.id).where(
            TeamMembership.team_id == team_id, TeamMembership.user_id == user_id
        )
    )
    if exists is None:
        raise HTTPException(status_code=422, detail="Owner must be a team member")


@router.get("", response_model=list[TeamResponse])
def list_teams(actor: CurrentActor, database: Database) -> list[TeamResponse]:
    user_id = human(actor)
    if is_admin(actor):
        teams = [(team, "admin") for team in database.scalars(select(Team).order_by(Team.name))]
    else:
        teams = list(
            database.execute(
                select(Team, TeamMembership.team_role)
                .join(TeamMembership, TeamMembership.team_id == Team.id)
                .where(TeamMembership.user_id == user_id)
                .order_by(Team.name)
            )
        )
    return [team_response(database, team, access) for team, access in teams]  # type: ignore[arg-type]


@router.post("", response_model=TeamResponse, status_code=201)
def create_team(payload: TeamRequest, actor: CurrentActor, database: Database) -> TeamResponse:
    require_admin(actor)
    team = Team(name=payload.name, description=payload.description, created_by=actor.id)
    try:
        with database.begin():
            database.add(team)
            database.flush()
            audit(database, actor, "team.created", team.id, name=team.name)
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Team name already exists") from None
    return team_response(database, team, "admin")


@router.get("/{team_id}", response_model=TeamDetailResponse)
def get_team(team_id: UUID, actor: CurrentActor, database: Database) -> TeamDetailResponse:
    team, access = team_access(database, actor, team_id)
    rows = database.execute(
        select(TeamMembership, User)
        .join(User, User.id == TeamMembership.user_id)
        .where(TeamMembership.team_id == team.id)
        .order_by(User.display_name)
    )
    members = [
        MemberResponse(
            user_id=user.id,
            display_name=user.display_name,
            email=user.email,
            team_role=membership.team_role,  # type: ignore[arg-type]
            active=user.active,
        )
        for membership, user in rows
    ]
    return TeamDetailResponse(**team_response(database, team, access).model_dump(), members=members)


@router.patch("/{team_id}", response_model=TeamResponse)
def update_team(
    team_id: UUID, payload: TeamUpdateRequest, actor: CurrentActor, database: Database
) -> TeamResponse:
    require_admin(actor)
    try:
        with database.begin():
            team, _ = team_access(database, actor, team_id)
            changes = payload.model_dump(exclude_unset=True, exclude_none=True)
            for field, value in changes.items():
                setattr(team, field, value)
            audit(database, actor, "team.updated", team.id, fields=sorted(changes))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Team name already exists") from None
    return team_response(database, team, "admin")


@router.put("/{team_id}/members/{user_id}", response_model=MemberResponse)
def set_member(
    team_id: UUID,
    user_id: UUID,
    payload: MembershipRequest,
    actor: CurrentActor,
    database: Database,
) -> MemberResponse:
    require_admin(actor)
    try:
        with database.begin():
            team, _ = team_access(database, actor, team_id)
            user = database.get(User, str(user_id))
            if user is None:
                raise HTTPException(status_code=404, detail="User not found")
            membership = database.scalar(
                select(TeamMembership).where(
                    TeamMembership.team_id == team.id, TeamMembership.user_id == user.id
                )
            )
            if membership is None:
                membership = TeamMembership(team_id=team.id, user_id=user.id)
                database.add(membership)
            membership.team_role = payload.team_role
            audit(
                database,
                actor,
                "team.member.set",
                team.id,
                user_id=user.id,
                team_role=payload.team_role,
            )
    except IntegrityError:
        raise HTTPException(status_code=409, detail="Membership changed concurrently") from None
    return MemberResponse(
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        team_role=payload.team_role,
        active=user.active,
    )


@router.delete("/{team_id}/members/{user_id}", status_code=204)
def remove_member(
    team_id: UUID, user_id: UUID, actor: CurrentActor, database: Database
) -> Response:
    require_admin(actor)
    with database.begin():
        team, _ = team_access(database, actor, team_id)
        membership = database.scalar(
            select(TeamMembership).where(
                TeamMembership.team_id == team.id, TeamMembership.user_id == str(user_id)
            )
        )
        if membership is None:
            raise HTTPException(status_code=404, detail="Member not found")
        # Unfinished work must not stay owned by someone who can no longer see it.
        for item in database.scalars(
            select(WorkItem).where(
                WorkItem.team_id == team.id,
                WorkItem.owner_id == membership.user_id,
                WorkItem.status != "done",
            )
        ):
            item.owner_id = None
            item.updated_at = utc_now()
        audit(database, actor, "team.member.removed", team.id, user_id=membership.user_id)
        database.delete(membership)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/{team_id}/work-items", response_model=list[WorkItemResponse])
def list_work_items(
    team_id: UUID, actor: CurrentActor, database: Database
) -> list[WorkItemResponse]:
    team, _ = team_access(database, actor, team_id)
    items = database.scalars(
        select(WorkItem).where(WorkItem.team_id == team.id).order_by(WorkItem.created_at.desc())
    )
    return [item_response(item) for item in items]


@router.post("/{team_id}/work-items", response_model=WorkItemResponse, status_code=201)
def create_work_item(
    team_id: UUID, payload: WorkItemRequest, actor: CurrentActor, database: Database
) -> WorkItemResponse:
    with database.begin():
        team, access = team_access(database, actor, team_id)
        owner_id = payload.owner_id
        if access not in LEADERSHIP and owner_id not in (None, actor.id):
            raise HTTPException(
                status_code=403, detail="Members can only assign work to themselves"
            )
        require_member(database, team.id, owner_id)
        now = utc_now()
        item = WorkItem(
            team_id=team.id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            owner_id=owner_id,
            due_date=payload.due_date,
            created_by=actor.id,
            created_at=now,
            updated_at=now,
        )
        database.add(item)
        database.flush()
        audit(database, actor, "team.work_item.created", team.id, work_item_id=item.id)
    return item_response(item)


@router.patch("/{team_id}/work-items/{item_id}", response_model=WorkItemResponse)
def update_work_item(
    team_id: UUID,
    item_id: UUID,
    payload: WorkItemUpdateRequest,
    actor: CurrentActor,
    database: Database,
) -> WorkItemResponse:
    with database.begin():
        team, access = team_access(database, actor, team_id)
        item = database.get(WorkItem, str(item_id))
        if item is None or item.team_id != team.id:
            raise HTTPException(status_code=404, detail="Work item not found")
        changes = payload.model_dump(exclude_unset=True)
        if access not in LEADERSHIP:
            if actor.id not in (item.owner_id, item.created_by):
                raise HTTPException(status_code=403, detail="Permission denied")
            if "owner_id" in changes and changes["owner_id"] not in (None, actor.id):
                raise HTTPException(
                    status_code=403, detail="Members can only assign work to themselves"
                )
        if "owner_id" in changes:
            require_member(database, team.id, changes["owner_id"])
        for field in ("title", "description", "status", "priority"):
            if changes.get(field) is not None:
                setattr(item, field, changes[field])
        for field in ("owner_id", "due_date"):
            if field in changes:
                setattr(item, field, changes[field])
        item.updated_at = utc_now()
        audit(
            database,
            actor,
            "team.work_item.updated",
            team.id,
            work_item_id=item.id,
            fields=sorted(changes),
        )
    return item_response(item)


@router.get("/{team_id}/summary", response_model=TeamSummaryResponse)
def team_summary(team_id: UUID, actor: CurrentActor, database: Database) -> TeamSummaryResponse:
    team, access = team_access(database, actor, team_id)
    require_leadership(access)
    items = list(database.scalars(select(WorkItem).where(WorkItem.team_id == team.id)))
    names = {
        user_id: name
        for user_id, name in database.execute(
            select(User.id, User.display_name)
            .join(TeamMembership, TeamMembership.user_id == User.id)
            .where(TeamMembership.team_id == team.id)
        )
    }
    today = date.today()
    week_ago = utc_now() - timedelta(days=7)
    statuses = Counter(item.status for item in items)
    owners = Counter(item.owner_id for item in items if item.status != "done")
    return TeamSummaryResponse(
        team_id=team.id,
        total=len(items),
        by_status={status: statuses.get(status, 0) for status in WORK_STATUSES},  # type: ignore[misc]
        overdue=sum(
            1
            for item in items
            if item.status != "done" and item.due_date is not None and item.due_date < today
        ),
        done_last_7_days=sum(
            1 for item in items if item.status == "done" and as_utc(item.updated_at) >= week_ago
        ),
        by_owner=[
            OwnerLoad(
                owner_id=owner,
                display_name=names.get(owner, "Atanmamış") if owner else "Atanmamış",
                open_items=count,
            )
            for owner, count in owners.most_common()
        ],
    )


@router.get("/{team_id}/dashboard", response_model=DashboardResponse)
def get_dashboard(team_id: UUID, actor: CurrentActor, database: Database) -> DashboardResponse:
    team, _ = team_access(database, actor, team_id)
    saved = database.get(TeamDashboard, team.id)
    if saved is None:
        return DashboardResponse(
            team_id=team.id,
            widgets=list(DEFAULT_WIDGETS),
            filters=DashboardFilters(),
            updated_at=None,
        )
    return DashboardResponse(
        team_id=team.id,
        widgets=saved.widgets,  # type: ignore[arg-type]
        filters=DashboardFilters(**saved.filters),
        updated_at=as_utc(saved.updated_at),
    )


@router.put("/{team_id}/dashboard", response_model=DashboardResponse)
def save_dashboard(
    team_id: UUID, payload: DashboardRequest, actor: CurrentActor, database: Database
) -> DashboardResponse:
    widgets = list(dict.fromkeys(payload.widgets))
    with database.begin():
        team, access = team_access(database, actor, team_id)
        require_leadership(access)
        saved = database.get(TeamDashboard, team.id)
        if saved is None:
            saved = TeamDashboard(team_id=team.id, updated_by=actor.id)
            database.add(saved)
        saved.widgets = widgets
        saved.filters = payload.filters.model_dump()
        saved.updated_by = actor.id
        saved.updated_at = utc_now()
        audit(database, actor, "team.dashboard.updated", team.id, widgets=widgets)
    return DashboardResponse(
        team_id=team.id,
        widgets=widgets,  # type: ignore[arg-type]
        filters=payload.filters,
        updated_at=as_utc(saved.updated_at),
    )
