"""Authentication and authorization behavior of the single-organization prototype."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from allsafe_api.config import Settings
from allsafe_api.main import create_app
from allsafe_api.models import User, UserSession

ADMIN_EMAIL = "admin@allsafe.local"
ADMIN_PASSWORD = "Test-Admin-Password-1234"
USER_PASSWORD = "Test-User-Password-1234"


@dataclass(frozen=True)
class LoginSession:
    user: dict[str, Any]
    token: str
    csrf: str

    def headers(self, *, csrf: bool = True) -> dict[str, str]:
        headers = {"Cookie": f"allsafe_session={self.token}; allsafe_csrf={self.csrf}"}
        if csrf:
            headers["X-CSRF-Token"] = self.csrf
        return headers


def login(
    client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD
) -> LoginSession:
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return LoginSession(
        response.json(),
        response.cookies["allsafe_session"],
        response.cookies["allsafe_csrf"],
    )


def create_user(
    client: TestClient,
    administrator: LoginSession,
    *,
    role: str = "employee",
    email: str = "employee@allsafe.local",
    training_permission: bool = False,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/users",
        headers=administrator.headers(),
        json={
            "email": email,
            "display_name": "Test Employee",
            "password": USER_PASSWORD,
            "role": role,
            "training_permission": training_permission,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_initial_administrator_login_and_session_cookie_flags(identity_client: TestClient) -> None:
    response = identity_client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert response.json()["email"] == ADMIN_EMAIL
    assert response.json()["role"] == "admin"
    assert response.json()["active"] is True
    cookies = response.headers.get_list("set-cookie")
    session_cookie = next(value for value in cookies if value.startswith("allsafe_session="))
    csrf_cookie = next(value for value in cookies if value.startswith("allsafe_csrf="))
    assert "httponly" in session_cookie.lower()
    assert "samesite=lax" in session_cookie.lower()
    assert "httponly" not in csrf_cookie.lower()
    assert "samesite=lax" in csrf_cookie.lower()
    assert identity_client.get("/api/v1/auth/me").json() == response.json()


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/auth/me",
        "/api/v1/users",
        "/api/v1/devices",
        "/api/v1/modules",
        "/api/v1/audit-events",
    ],
)
def test_user_resources_require_authentication(identity_client: TestClient, path: str) -> None:
    assert identity_client.get(path).status_code == 401
    assert (
        identity_client.get(path, headers={"Cookie": "allsafe_session=unknown"}).status_code == 401
    )


def test_unknown_account_and_wrong_password_have_same_response(identity_client: TestClient) -> None:
    unknown = identity_client.post(
        "/api/v1/auth/login",
        json={"email": "missing@allsafe.local", "password": USER_PASSWORD},
    )
    wrong = identity_client.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": USER_PASSWORD}
    )
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()
    assert "allsafe_session" not in unknown.cookies
    assert "allsafe_session" not in wrong.cookies


@pytest.mark.parametrize(
    ("role", "can_read", "can_manage"),
    [("admin", True, True), ("analyst", True, False), ("employee", False, False)],
)
def test_roles_separate_management_reads_and_writes(
    identity_client: TestClient, role: str, can_read: bool, can_manage: bool
) -> None:
    administrator = login(identity_client)
    created = create_user(identity_client, administrator, role=role)
    actor = login(identity_client, created["email"], USER_PASSWORD)
    assert identity_client.get("/api/v1/auth/me", headers=actor.headers()).status_code == 200
    for path in ("/api/v1/devices", "/api/v1/modules", "/api/v1/audit-events"):
        response = identity_client.get(path, headers=actor.headers())
        assert response.status_code == (200 if can_read else 403), response.text
    response = identity_client.post(
        "/api/v1/enrollment-tokens", headers=actor.headers(), json={"label": "Role test"}
    )
    assert response.status_code == (201 if can_manage else 403), response.text
    response = identity_client.get("/api/v1/users", headers=actor.headers())
    assert response.status_code == (200 if can_manage else 403), response.text
    if not can_manage:
        response = identity_client.patch(
            f"/api/v1/users/{actor.user['id']}",
            headers=actor.headers(),
            json={"role": "admin", "training_permission": True},
        )
        assert response.status_code == 403, response.text
        assert (
            identity_client.get("/api/v1/auth/me", headers=actor.headers()).json()["role"] == role
        )
    assert ("devices:read" in actor.user["permissions"]) is can_read
    assert ("devices:manage" in actor.user["permissions"]) is can_manage


def test_training_permission_is_independent_from_role(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    employee = create_user(identity_client, administrator)
    analyst = create_user(
        identity_client, administrator, role="analyst", email="analyst@allsafe.local"
    )
    normal = login(identity_client, employee["email"], USER_PASSWORD)
    assert "training:approve" not in normal.user["permissions"]
    analyst_session = login(identity_client, analyst["email"], USER_PASSWORD)
    assert "training:approve" not in analyst_session.user["permissions"]
    response = identity_client.patch(
        f"/api/v1/users/{employee['id']}",
        headers=administrator.headers(),
        json={"training_permission": True},
    )
    assert response.status_code == 200, response.text
    authorized = login(identity_client, employee["email"], USER_PASSWORD)
    assert authorized.user["role"] == "employee"
    assert "training:approve" in authorized.user["permissions"]
    assert "devices:manage" not in authorized.user["permissions"]


def test_administrator_requires_explicit_training_permission(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    created = create_user(identity_client, administrator, role="admin", training_permission=False)
    unapproved = login(identity_client, created["email"], USER_PASSWORD)
    assert unapproved.user["role"] == "admin"
    assert "training:approve" not in unapproved.user["permissions"]
    assert "devices:manage" in unapproved.user["permissions"]
    response = identity_client.patch(
        f"/api/v1/users/{created['id']}",
        headers=administrator.headers(),
        json={"training_permission": True},
    )
    assert response.status_code == 200, response.text
    assert identity_client.get("/api/v1/auth/me", headers=unapproved.headers()).status_code == 401
    approved = login(identity_client, created["email"], USER_PASSWORD)
    assert approved.user["role"] == "admin"
    assert set(approved.user["permissions"]) - set(unapproved.user["permissions"]) == {
        "training:approve"
    }


def test_cookie_mutations_require_matching_csrf_token(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    body = {"label": "CSRF protected enrollment"}
    response = identity_client.post(
        "/api/v1/enrollment-tokens", headers=administrator.headers(csrf=False), json=body
    )
    assert response.status_code == 403
    mismatched = administrator.headers()
    mismatched["X-CSRF-Token"] = "not-the-session-token"
    assert (
        identity_client.post("/api/v1/enrollment-tokens", headers=mismatched, json=body).status_code
        == 403
    )
    forged = administrator.headers()
    forged["Cookie"] = f"allsafe_session={administrator.token}; allsafe_csrf=forged"
    forged["X-CSRF-Token"] = "forged"
    assert (
        identity_client.post("/api/v1/enrollment-tokens", headers=forged, json=body).status_code
        == 403
    )
    no_csrf_cookie = administrator.headers()
    no_csrf_cookie["Cookie"] = f"allsafe_session={administrator.token}"
    assert (
        identity_client.post(
            "/api/v1/enrollment-tokens", headers=no_csrf_cookie, json=body
        ).status_code
        == 403
    )
    assert (
        identity_client.post(
            "/api/v1/enrollment-tokens", headers=administrator.headers(), json=body
        ).status_code
        == 201
    )


@pytest.mark.parametrize(
    "origin", ["https://untrusted.example", "http://localhost:8000", "http://127.0.0.1:8001"]
)
def test_cross_origin_cookie_mutation_is_rejected(identity_client: TestClient, origin: str) -> None:
    administrator = login(identity_client)
    headers = administrator.headers()
    headers["Origin"] = origin
    response = identity_client.post(
        "/api/v1/enrollment-tokens", headers=headers, json={"label": "Cross origin"}
    )
    assert response.status_code == 403


def test_non_ascii_csrf_values_are_rejected_without_server_error(
    identity_client: TestClient,
) -> None:
    administrator = login(identity_client)
    headers = [
        (
            b"cookie",
            f"allsafe_session={administrator.token}; allsafe_csrf=".encode("ascii") + b"\xff",
        ),
        (b"x-csrf-token", b"\xff"),
    ]
    response = identity_client.post(
        "/api/v1/enrollment-tokens", headers=headers, json={"label": "Malformed CSRF"}
    )
    assert response.status_code == 403


def test_logout_revokes_session_even_when_old_cookie_is_replayed(
    identity_client: TestClient,
) -> None:
    administrator = login(identity_client)
    response = identity_client.post("/api/v1/auth/logout", headers=administrator.headers())
    assert response.status_code == 204, response.text
    assert identity_client.get("/api/v1/auth/me").status_code == 401
    assert (
        identity_client.get("/api/v1/auth/me", headers=administrator.headers()).status_code == 401
    )


def test_expired_session_cannot_read_or_mutate(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    with identity_client.app.state.session_factory() as database:
        stored = database.scalar(select(UserSession))
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        database.commit()
    assert (
        identity_client.get("/api/v1/auth/me", headers=administrator.headers()).status_code == 401
    )
    assert (
        identity_client.post(
            "/api/v1/enrollment-tokens",
            headers=administrator.headers(),
            json={"label": "Expired session"},
        ).status_code
        == 401
    )


def test_deactivation_revokes_sessions_and_blocks_login(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    employee = create_user(identity_client, administrator)
    old_session = login(identity_client, employee["email"], USER_PASSWORD)
    response = identity_client.patch(
        f"/api/v1/users/{employee['id']}",
        headers=administrator.headers(),
        json={"active": False},
    )
    assert response.status_code == 200, response.text
    assert identity_client.get("/api/v1/auth/me", headers=old_session.headers()).status_code == 401
    identity_client.cookies.clear()
    response = identity_client.post(
        "/api/v1/auth/login", json={"email": employee["email"], "password": USER_PASSWORD}
    )
    assert response.status_code == 401
    response = identity_client.patch(
        f"/api/v1/users/{employee['id']}",
        headers=administrator.headers(),
        json={"active": True},
    )
    assert response.status_code == 200, response.text
    login(identity_client, employee["email"], USER_PASSWORD)
    assert identity_client.get("/api/v1/auth/me", headers=old_session.headers()).status_code == 401


def test_role_change_revokes_old_session(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    analyst = create_user(identity_client, administrator, role="analyst")
    old_session = login(identity_client, analyst["email"], USER_PASSWORD)
    response = identity_client.patch(
        f"/api/v1/users/{analyst['id']}",
        headers=administrator.headers(),
        json={"role": "employee"},
    )
    assert response.status_code == 200, response.text
    assert identity_client.get("/api/v1/devices", headers=old_session.headers()).status_code == 401
    current = login(identity_client, analyst["email"], USER_PASSWORD)
    assert identity_client.get("/api/v1/devices", headers=current.headers()).status_code == 403


def test_password_reset_revokes_old_session_and_old_password(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    employee = create_user(identity_client, administrator)
    old_session = login(identity_client, employee["email"], USER_PASSWORD)
    new_password = "Reset-User-Password-5678"
    response = identity_client.post(
        f"/api/v1/users/{employee['id']}/password",
        headers=administrator.headers(),
        json={"password": new_password},
    )
    assert response.status_code in (200, 204), response.text
    assert identity_client.get("/api/v1/auth/me", headers=old_session.headers()).status_code == 401
    identity_client.cookies.clear()
    response = identity_client.post(
        "/api/v1/auth/login", json={"email": employee["email"], "password": USER_PASSWORD}
    )
    assert response.status_code == 401
    current = login(identity_client, employee["email"], new_password)
    assert current.user["id"] == employee["id"]


def test_training_permission_removal_revokes_old_session(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    employee = create_user(identity_client, administrator, training_permission=True)
    old_session = login(identity_client, employee["email"], USER_PASSWORD)
    assert "training:approve" in old_session.user["permissions"]
    response = identity_client.patch(
        f"/api/v1/users/{employee['id']}",
        headers=administrator.headers(),
        json={"training_permission": False},
    )
    assert response.status_code == 200, response.text
    assert identity_client.get("/api/v1/auth/me", headers=old_session.headers()).status_code == 401
    current = login(identity_client, employee["email"], USER_PASSWORD)
    assert "training:approve" not in current.user["permissions"]


@pytest.mark.parametrize("change", [{"active": False}, {"role": "analyst"}])
def test_last_active_administrator_cannot_be_disabled_or_demoted(
    identity_client: TestClient, change: dict[str, Any]
) -> None:
    administrator = login(identity_client)
    response = identity_client.patch(
        f"/api/v1/users/{administrator.user['id']}",
        headers=administrator.headers(),
        json=change,
    )
    assert response.status_code == 409, response.text
    assert identity_client.get("/api/v1/users", headers=administrator.headers()).status_code == 200


def test_additional_administrator_allows_administrator_demotion(
    identity_client: TestClient,
) -> None:
    administrator = login(identity_client)
    create_user(identity_client, administrator, role="admin")
    response = identity_client.patch(
        f"/api/v1/users/{administrator.user['id']}",
        headers=administrator.headers(),
        json={"role": "employee"},
    )
    assert response.status_code == 200, response.text
    assert identity_client.get("/api/v1/users", headers=administrator.headers()).status_code == 401
    current = login(identity_client)
    assert current.user["role"] == "employee"
    assert identity_client.get("/api/v1/users", headers=current.headers()).status_code == 403


def test_duplicate_user_email_is_rejected_without_duplicate_account(
    identity_client: TestClient,
) -> None:
    administrator = login(identity_client)
    create_user(identity_client, administrator)
    response = identity_client.post(
        "/api/v1/users",
        headers=administrator.headers(),
        json={
            "email": "EMPLOYEE@ALLSAFE.LOCAL",
            "display_name": "Duplicate",
            "password": USER_PASSWORD,
            "role": "employee",
        },
    )
    assert response.status_code == 409, response.text
    users = identity_client.get("/api/v1/users", headers=administrator.headers()).json()
    assert len(users) == 2


def test_concurrent_administrator_demotions_preserve_one_active_administrator(
    identity_client: TestClient,
) -> None:
    first = login(identity_client)
    second_user = create_user(identity_client, first, role="admin")
    second = login(identity_client, second_user["email"], USER_PASSWORD)
    start = Barrier(2, timeout=10)

    def demote_self(actor: LoginSession) -> int:
        start.wait()
        return identity_client.patch(
            f"/api/v1/users/{actor.user['id']}",
            headers=actor.headers(),
            json={"role": "employee"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        statuses = list(workers.map(demote_self, [first, second]))
    assert sorted(statuses) == [200, 409]
    with identity_client.app.state.session_factory() as database:
        administrators = database.scalars(
            select(User).where(User.active.is_(True), User.role == "admin")
        ).all()
        assert len(administrators) == 1


def test_password_and_session_secrets_are_hashed_and_absent_from_responses(
    identity_client: TestClient,
) -> None:
    administrator = login(identity_client)
    create_user(identity_client, administrator)
    with identity_client.app.state.session_factory() as database:
        users = database.scalars(select(User)).all()
        assert len(users) == 2
        for user in users:
            assert user.password_hash
            assert ADMIN_PASSWORD not in user.password_hash
            assert USER_PASSWORD not in user.password_hash
        stored_session = database.scalar(select(UserSession))
        assert stored_session is not None
        assert administrator.token not in stored_session.token_hash
        password_hashes = [user.password_hash for user in users]
        session_hash = stored_session.token_hash
    for path in ("/api/v1/auth/me", "/api/v1/users", "/api/v1/audit-events"):
        response = identity_client.get(path, headers=administrator.headers())
        assert response.status_code == 200, response.text
        for secret in (
            ADMIN_PASSWORD,
            USER_PASSWORD,
            administrator.token,
            administrator.csrf,
            session_hash,
            *password_hashes,
        ):
            assert secret not in response.text
        assert "password_hash" not in response.text
        assert "token_hash" not in response.text


def test_repeated_failed_login_is_throttled_and_survives_restart(
    identity_settings: Settings,
) -> None:
    body = {"email": ADMIN_EMAIL, "password": USER_PASSWORD}
    with TestClient(create_app(identity_settings)) as client:
        for _ in range(5):
            assert client.post("/api/v1/auth/login", json=body).status_code == 401
        assert client.post("/api/v1/auth/login", json=body).status_code == 429
    with TestClient(create_app(identity_settings)) as restarted:
        assert restarted.post("/api/v1/auth/login", json=body).status_code == 429
        correct = {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        assert restarted.post("/api/v1/auth/login", json=correct).status_code == 429


def test_user_session_and_account_survive_restart(identity_settings: Settings) -> None:
    with TestClient(create_app(identity_settings)) as client:
        administrator = login(client)
        created = create_user(client, administrator)
    with TestClient(create_app(identity_settings)) as restarted:
        assert (
            restarted.get("/api/v1/auth/me", headers=administrator.headers()).json()["id"]
            == administrator.user["id"]
        )
        users = restarted.get("/api/v1/users", headers=administrator.headers()).json()
        assert len(users) == 2
        assert any(user["id"] == created["id"] for user in users)
        employee = login(restarted, created["email"], USER_PASSWORD)
        assert employee.user["id"] == created["id"]


def test_agent_cannot_use_user_endpoints_and_rotated_key_replaces_old_key(
    identity_client: TestClient,
) -> None:
    administrator = login(identity_client)
    response = identity_client.post(
        "/api/v1/enrollment-tokens",
        headers=administrator.headers(),
        json={"label": "Rotating credential"},
    )
    assert response.status_code == 201, response.text
    enrolled = identity_client.post(
        "/api/v1/agent/enroll",
        json={
            "enrollment_token": response.json()["enrollment_token"],
            "hostname": "rotation-test",
            "platform": "windows",
            "agent_version": "0.1.0",
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    device = enrolled.json()
    identity_client.cookies.clear()
    agent_headers = {"Authorization": f"Bearer {device['agent_token']}"}
    for path in ("/api/v1/auth/me", "/api/v1/users", "/api/v1/devices"):
        assert identity_client.get(path, headers=agent_headers).status_code in (401, 403)
    heartbeat = {"device_id": device["device_id"], "agent_version": "0.1.1"}
    assert (
        identity_client.post(
            "/api/v1/agent/heartbeat", headers=agent_headers, json=heartbeat
        ).status_code
        == 200
    )
    response = identity_client.post(
        f"/api/v1/devices/{device['device_id']}/rotate-token", headers=administrator.headers()
    )
    assert response.status_code == 200, response.text
    assert response.json()["device_id"] == device["device_id"]
    new_token = response.json()["agent_token"]
    assert new_token != device["agent_token"]
    assert (
        identity_client.post(
            "/api/v1/agent/heartbeat", headers=agent_headers, json=heartbeat
        ).status_code
        == 401
    )
    assert (
        identity_client.post(
            "/api/v1/agent/heartbeat",
            headers={"Authorization": f"Bearer {new_token}"},
            json=heartbeat,
        ).status_code
        == 200
    )
    audit = identity_client.get("/api/v1/audit-events", headers=administrator.headers()).json()
    events = [event for event in audit if "rotat" in event["event_type"]]
    assert len(events) == 1
    assert events[0]["target_id"] == device["device_id"]
    assert events[0]["actor"] != "bootstrap-admin"
    assert new_token not in str(audit)
    assert device["agent_token"] not in str(audit)
