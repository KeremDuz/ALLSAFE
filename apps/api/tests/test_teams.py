from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_identity import USER_PASSWORD, LoginSession, create_user, login


def create_team(client: TestClient, admin: LoginSession, name: str = "SOC") -> dict[str, Any]:
    response = client.post(
        "/api/v1/teams", headers=admin.headers(), json={"name": name, "description": "Lab"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def add_member(
    client: TestClient, admin: LoginSession, team_id: str, user_id: str, role: str = "member"
) -> None:
    response = client.put(
        f"/api/v1/teams/{team_id}/members/{user_id}",
        headers=admin.headers(),
        json={"team_role": role},
    )
    assert response.status_code == 200, response.text


@pytest.fixture
def team_setup(identity_client: TestClient) -> dict[str, Any]:
    admin = login(identity_client)
    manager = create_user(identity_client, admin, email="manager@allsafe.local")
    member = create_user(identity_client, admin, email="member@allsafe.local")
    outsider = create_user(identity_client, admin, email="outsider@allsafe.local")
    team = create_team(identity_client, admin)
    add_member(identity_client, admin, team["id"], manager["id"], "manager")
    add_member(identity_client, admin, team["id"], member["id"])
    return {
        "admin": admin,
        "team": team,
        "manager": manager,
        "member": member,
        "outsider": outsider,
    }


def as_user(client: TestClient, email: str) -> LoginSession:
    return login(client, email, USER_PASSWORD)


def test_only_administrators_create_teams_and_manage_members(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    manager = as_user(identity_client, "manager@allsafe.local")
    team_id = team_setup["team"]["id"]

    assert (
        identity_client.post(
            "/api/v1/teams", headers=manager.headers(), json={"name": "Shadow team"}
        ).status_code
        == 403
    )
    response = identity_client.put(
        f"/api/v1/teams/{team_id}/members/{team_setup['outsider']['id']}",
        headers=manager.headers(),
        json={"team_role": "manager"},
    )
    assert response.status_code == 403


def test_duplicate_team_name_is_rejected(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    response = identity_client.post(
        "/api/v1/teams", headers=team_setup["admin"].headers(), json={"name": "SOC"}
    )
    assert response.status_code == 409


def test_non_members_cannot_discover_or_read_a_team(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    outsider = as_user(identity_client, "outsider@allsafe.local")
    team_id = team_setup["team"]["id"]

    assert identity_client.get("/api/v1/teams", headers=outsider.headers()).json() == []
    for path in ("", "/work-items", "/summary", "/dashboard"):
        response = identity_client.get(f"/api/v1/teams/{team_id}{path}", headers=outsider.headers())
        assert response.status_code == 404, path
    response = identity_client.post(
        f"/api/v1/teams/{team_id}/work-items", headers=outsider.headers(), json={"title": "x"}
    )
    assert response.status_code == 404


def test_member_lists_own_team_with_role_and_members(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    member = as_user(identity_client, "member@allsafe.local")
    teams = identity_client.get("/api/v1/teams", headers=member.headers()).json()
    assert [(team["name"], team["my_role"]) for team in teams] == [("SOC", "member")]

    detail = identity_client.get(
        f"/api/v1/teams/{team_setup['team']['id']}", headers=member.headers()
    ).json()
    assert {item["email"]: item["team_role"] for item in detail["members"]} == {
        "manager@allsafe.local": "manager",
        "member@allsafe.local": "member",
    }


def test_members_work_on_their_own_items_only(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    team_id = team_setup["team"]["id"]
    manager = as_user(identity_client, "manager@allsafe.local")
    assigned = identity_client.post(
        f"/api/v1/teams/{team_id}/work-items",
        headers=manager.headers(),
        json={"title": "Review alerts", "owner_id": team_setup["manager"]["id"]},
    ).json()

    member = as_user(identity_client, "member@allsafe.local")
    own = identity_client.post(
        f"/api/v1/teams/{team_id}/work-items",
        headers=member.headers(),
        json={"title": "Check phishing report", "owner_id": team_setup["member"]["id"]},
    )
    assert own.status_code == 201, own.text
    assigned_to_other = identity_client.post(
        f"/api/v1/teams/{team_id}/work-items",
        headers=member.headers(),
        json={"title": "Push work", "owner_id": team_setup["manager"]["id"]},
    )
    assert assigned_to_other.status_code == 403

    progress = identity_client.patch(
        f"/api/v1/teams/{team_id}/work-items/{own.json()['id']}",
        headers=member.headers(),
        json={"status": "in_progress"},
    )
    assert progress.status_code == 200
    assert progress.json()["status"] == "in_progress"
    foreign = identity_client.patch(
        f"/api/v1/teams/{team_id}/work-items/{assigned['id']}",
        headers=member.headers(),
        json={"status": "done"},
    )
    assert foreign.status_code == 403


def test_owner_must_belong_to_the_team(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    manager = as_user(identity_client, "manager@allsafe.local")
    response = identity_client.post(
        f"/api/v1/teams/{team_setup['team']['id']}/work-items",
        headers=manager.headers(),
        json={"title": "Leak", "owner_id": team_setup["outsider"]["id"]},
    )
    assert response.status_code == 422


def test_work_items_do_not_cross_teams(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    admin = team_setup["admin"]
    other = create_team(identity_client, admin, "Network")
    item = identity_client.post(
        f"/api/v1/teams/{other['id']}/work-items", headers=admin.headers(), json={"title": "VLAN"}
    ).json()
    manager = as_user(identity_client, "manager@allsafe.local")
    response = identity_client.patch(
        f"/api/v1/teams/{team_setup['team']['id']}/work-items/{item['id']}",
        headers=manager.headers(),
        json={"status": "done"},
    )
    assert response.status_code == 404


def test_summary_is_for_leadership_and_counts_progress(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    team_id = team_setup["team"]["id"]
    manager = as_user(identity_client, "manager@allsafe.local")
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    for title, status, due in (
        ("A", "open", yesterday),
        ("B", "done", None),
        ("C", "blocked", None),
    ):
        created = identity_client.post(
            f"/api/v1/teams/{team_id}/work-items",
            headers=manager.headers(),
            json={"title": title, "owner_id": team_setup["member"]["id"], "due_date": due},
        ).json()
        identity_client.patch(
            f"/api/v1/teams/{team_id}/work-items/{created['id']}",
            headers=manager.headers(),
            json={"status": status},
        )

    summary = identity_client.get(f"/api/v1/teams/{team_id}/summary", headers=manager.headers())
    assert summary.status_code == 200
    body = summary.json()
    assert body["total"] == 3
    assert body["by_status"] == {"open": 1, "in_progress": 0, "blocked": 1, "done": 1}
    assert body["overdue"] == 1
    assert body["done_last_7_days"] == 1
    assert body["by_owner"] == [
        {"owner_id": team_setup["member"]["id"], "display_name": "Test Employee", "open_items": 2}
    ]

    member = as_user(identity_client, "member@allsafe.local")
    assert (
        identity_client.get(
            f"/api/v1/teams/{team_id}/summary", headers=member.headers()
        ).status_code
        == 403
    )


def test_dashboard_accepts_only_approved_widgets_from_leadership(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    team_id = team_setup["team"]["id"]
    member = as_user(identity_client, "member@allsafe.local")
    default = identity_client.get(f"/api/v1/teams/{team_id}/dashboard", headers=member.headers())
    assert default.json()["widgets"] == ["status", "owners", "overdue", "recent"]
    assert (
        identity_client.put(
            f"/api/v1/teams/{team_id}/dashboard", headers=member.headers(), json={"widgets": []}
        ).status_code
        == 403
    )

    manager = as_user(identity_client, "manager@allsafe.local")
    rejected = identity_client.put(
        f"/api/v1/teams/{team_id}/dashboard",
        headers=manager.headers(),
        json={"widgets": ["<script>"]},
    )
    assert rejected.status_code == 422
    saved = identity_client.put(
        f"/api/v1/teams/{team_id}/dashboard",
        headers=manager.headers(),
        json={"widgets": ["overdue", "status", "overdue"], "filters": {"hide_done": True}},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["widgets"] == ["overdue", "status"]

    member = as_user(identity_client, "member@allsafe.local")
    reread = identity_client.get(f"/api/v1/teams/{team_id}/dashboard", headers=member.headers())
    assert reread.json()["widgets"] == ["overdue", "status"]
    assert reread.json()["filters"] == {"owner": "all", "hide_done": True}


def test_removing_a_member_unassigns_open_work_and_is_audited(
    identity_client: TestClient, team_setup: dict[str, Any]
) -> None:
    admin = team_setup["admin"]
    team_id = team_setup["team"]["id"]
    member_id = team_setup["member"]["id"]
    item = identity_client.post(
        f"/api/v1/teams/{team_id}/work-items",
        headers=admin.headers(),
        json={"title": "Patch lab PC", "owner_id": member_id},
    ).json()

    removed = identity_client.delete(
        f"/api/v1/teams/{team_id}/members/{member_id}", headers=admin.headers()
    )
    assert removed.status_code == 204
    items = identity_client.get(
        f"/api/v1/teams/{team_id}/work-items", headers=admin.headers()
    ).json()
    assert next(entry for entry in items if entry["id"] == item["id"])["owner_id"] is None

    member = as_user(identity_client, "member@allsafe.local")
    assert identity_client.get("/api/v1/teams", headers=member.headers()).json() == []
    events = {
        event["event_type"]
        for event in identity_client.get("/api/v1/audit-events", headers=admin.headers()).json()
    }
    assert {"team.created", "team.member.set", "team.member.removed"} <= events


def test_team_changes_require_csrf(identity_client: TestClient, team_setup: dict[str, Any]) -> None:
    admin = team_setup["admin"]
    response = identity_client.post(
        "/api/v1/teams", headers=admin.headers(csrf=False), json={"name": "No CSRF"}
    )
    assert response.status_code in {401, 403}
