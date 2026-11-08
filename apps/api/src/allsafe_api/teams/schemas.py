"""Team request/response models with closed vocabularies."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from allsafe_api.schemas import RequestModel

TeamRole = Literal["member", "lead", "manager"]
WorkStatus = Literal["open", "in_progress", "blocked", "done"]
Priority = Literal["low", "medium", "high"]
Widget = Literal["status", "owners", "overdue", "recent"]
DEFAULT_WIDGETS: list[Widget] = ["status", "owners", "overdue", "recent"]


class TeamRequest(RequestModel):
    name: str = Field(min_length=2, max_length=80)
    description: str = Field(default="", max_length=300)


class TeamUpdateRequest(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=300)


class MembershipRequest(RequestModel):
    team_role: TeamRole = "member"


class WorkItemRequest(RequestModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=1000)
    priority: Priority = "medium"
    owner_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None


class WorkItemUpdateRequest(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    status: WorkStatus | None = None
    priority: Priority | None = None
    owner_id: str | None = Field(default=None, max_length=36)
    due_date: date | None = None


class DashboardFilters(RequestModel):
    owner: Literal["all", "me"] = "all"
    hide_done: bool = False


class DashboardRequest(RequestModel):
    widgets: list[Widget] = Field(default_factory=lambda: list(DEFAULT_WIDGETS), max_length=4)
    filters: DashboardFilters = Field(default_factory=DashboardFilters)


class MemberResponse(BaseModel):
    user_id: str
    display_name: str
    email: str
    team_role: TeamRole
    active: bool


class TeamResponse(BaseModel):
    id: str
    name: str
    description: str
    created_at: datetime
    my_role: TeamRole | Literal["admin"]
    member_count: int
    open_items: int


class TeamDetailResponse(TeamResponse):
    members: list[MemberResponse]


class WorkItemResponse(BaseModel):
    id: str
    team_id: str
    title: str
    description: str
    status: WorkStatus
    priority: Priority
    owner_id: str | None
    due_date: date | None
    created_by: str
    created_at: datetime
    updated_at: datetime


class OwnerLoad(BaseModel):
    owner_id: str | None
    display_name: str
    open_items: int


class TeamSummaryResponse(BaseModel):
    team_id: str
    total: int
    by_status: dict[WorkStatus, int]
    overdue: int
    done_last_7_days: int
    by_owner: list[OwnerLoad]


class DashboardResponse(BaseModel):
    team_id: str
    widgets: list[Widget]
    filters: DashboardFilters
    updated_at: datetime | None
