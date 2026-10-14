"""Native bearer sessions cannot be replayed as browser or device credentials."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from test_identity import ADMIN_EMAIL, ADMIN_PASSWORD, USER_PASSWORD, create_user, login

from allsafe_api.config import Settings
from allsafe_api.main import create_app
from allsafe_api.models import UserSession, utc_now
from allsafe_api.security import hash_token


def mobile_login(
    client: TestClient, email: str = ADMIN_EMAIL, password: str = ADMIN_PASSWORD
) -> dict[str, str]:
    response = client.post("/api/v1/auth/mobile/login", json={"email": email, "password": password})
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["token_type"] == "bearer"
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_native_token_is_hashed_bounded_and_preserves_web_session(
    identity_client: TestClient,
) -> None:
    browser = login(identity_client)
    headers = mobile_login(identity_client)
    token = headers["Authorization"].removeprefix("Bearer ")
    with identity_client.app.state.session_factory() as database:
        stored = database.scalar(
            select(UserSession).where(UserSession.token_hash == hash_token(token))
        )
        assert stored is not None and stored.channel == "mobile"
        assert stored.token_hash != token
        assert stored.expires_at - stored.created_at <= timedelta(hours=8)
    assert identity_client.get("/api/v1/auth/me", headers=browser.headers()).status_code == 200
    current = identity_client.get("/api/v1/auth/me", headers=headers)
    assert current.status_code == 200 and current.json()["id"] == browser.user["id"]
    assert token not in current.text
    assert (
        identity_client.post(
            "/api/v1/enrollment-tokens", headers=headers, json={"label": "Native administrator"}
        ).status_code
        == 201
    )


def test_tokens_cannot_cross_channels_or_fall_back_to_cookies(identity_client: TestClient) -> None:
    browser = login(identity_client)
    native = mobile_login(identity_client)
    assert (
        identity_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {browser.token}"}
        ).status_code
        == 401
    )
    assert (
        identity_client.get(
            "/api/v1/auth/me", headers={"Cookie": f"allsafe_session={native['Authorization'][7:]}"}
        ).status_code
        == 401
    )
    assert (
        identity_client.get(
            "/api/v1/auth/me", headers=browser.headers() | {"Authorization": "Bearer unknown"}
        ).status_code
        == 401
    )


def test_native_logout_only_revokes_target_native_session(identity_client: TestClient) -> None:
    browser = login(identity_client)
    first, second = mobile_login(identity_client), mobile_login(identity_client)
    assert (
        identity_client.post("/api/v1/auth/mobile/logout", headers=browser.headers()).status_code
        == 401
    )
    assert identity_client.post("/api/v1/auth/logout", headers=first).status_code == 401
    response = identity_client.post("/api/v1/auth/mobile/logout", headers=first)
    assert response.status_code == 204 and "set-cookie" not in response.headers
    assert response.headers["cache-control"] == "no-store"
    assert identity_client.get("/api/v1/auth/me", headers=first).status_code == 401
    assert identity_client.post("/api/v1/auth/mobile/logout", headers=first).status_code == 401
    assert identity_client.get("/api/v1/auth/me", headers=second).status_code == 200
    assert identity_client.get("/api/v1/auth/me", headers=browser.headers()).status_code == 200


def test_expired_mobile_session_cannot_read_or_mutate(identity_client: TestClient) -> None:
    headers = mobile_login(identity_client)
    with identity_client.app.state.session_factory() as database:
        stored = database.scalar(select(UserSession))
        assert stored is not None
        stored.expires_at = utc_now() - timedelta(seconds=1)
        database.commit()
    assert identity_client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert identity_client.post("/api/v1/auth/mobile/logout", headers=headers).status_code == 401
    assert (
        identity_client.post(
            "/api/v1/enrollment-tokens", headers=headers, json={"label": "Expired native"}
        ).status_code
        == 401
    )


def test_native_session_remains_bound_to_employee_account(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    employee = create_user(identity_client, administrator)
    headers = mobile_login(identity_client, employee["email"], USER_PASSWORD)
    current = identity_client.get("/api/v1/auth/me", headers=headers)
    assert current.json()["id"] == employee["id"]
    assert current.json()["id"] != administrator.user["id"]
    for path in ("/api/v1/users", "/api/v1/devices"):
        assert identity_client.get(path, headers=headers).status_code == 403
    assert (
        identity_client.patch(
            f"/api/v1/users/{administrator.user['id']}", headers=headers, json={"active": False}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("role", ["admin", "analyst", "employee"])
def test_scan_permissions_do_not_implicitly_grant_training(
    identity_client: TestClient, role: str
) -> None:
    administrator = login(identity_client)
    created = create_user(identity_client, administrator, role=role, training_permission=False)
    headers = mobile_login(identity_client, created["email"], USER_PASSWORD)
    permissions = identity_client.get("/api/v1/auth/me", headers=headers).json()["permissions"]
    assert {"scans:submit", "scans:own:read"}.issubset(permissions)
    assert ("scans:read" in permissions) is (role != "employee")
    assert ("scans:review" in permissions) is (role != "employee")
    assert "training:approve" not in permissions


@pytest.mark.parametrize(
    "change", [{"active": False}, {"role": "analyst"}, {"training_permission": True}]
)
def test_account_security_changes_revoke_both_session_channels(
    identity_client: TestClient, change: dict[str, object]
) -> None:
    administrator = login(identity_client)
    employee = create_user(identity_client, administrator)
    browser = login(identity_client, employee["email"], USER_PASSWORD)
    native = mobile_login(identity_client, employee["email"], USER_PASSWORD)
    assert (
        identity_client.patch(
            f"/api/v1/users/{employee['id']}", headers=administrator.headers(), json=change
        ).status_code
        == 200
    )
    assert identity_client.get("/api/v1/auth/me", headers=native).status_code == 401
    assert identity_client.get("/api/v1/auth/me", headers=browser.headers()).status_code == 401
    if change.get("active") is False:
        assert (
            identity_client.post(
                "/api/v1/auth/mobile/login",
                json={"email": employee["email"], "password": USER_PASSWORD},
            ).status_code
            == 401
        )


def test_password_reset_revokes_mobile_and_browser_sessions(identity_client: TestClient) -> None:
    administrator = login(identity_client)
    employee = create_user(identity_client, administrator)
    browser = login(identity_client, employee["email"], USER_PASSWORD)
    native = mobile_login(identity_client, employee["email"], USER_PASSWORD)
    replacement = "Native-Replacement-Password-5678"
    assert (
        identity_client.post(
            f"/api/v1/users/{employee['id']}/password",
            headers=administrator.headers(),
            json={"password": replacement},
        ).status_code
        == 204
    )
    assert identity_client.get("/api/v1/auth/me", headers=native).status_code == 401
    assert identity_client.get("/api/v1/auth/me", headers=browser.headers()).status_code == 401
    assert (
        identity_client.post(
            "/api/v1/auth/mobile/login",
            json={"email": employee["email"], "password": USER_PASSWORD},
        ).status_code
        == 401
    )
    mobile_login(identity_client, employee["email"], replacement)


def test_mobile_and_web_share_persistent_login_throttling(identity_settings: Settings) -> None:
    body = {"email": ADMIN_EMAIL, "password": USER_PASSWORD}
    with TestClient(create_app(identity_settings)) as client:
        for path in ["/api/v1/auth/mobile/login"] * 3 + ["/api/v1/auth/login"] * 2:
            assert client.post(path, json=body).status_code == 401
    with TestClient(create_app(identity_settings)) as restarted:
        for path in ("/api/v1/auth/mobile/login", "/api/v1/auth/login"):
            response = restarted.post(path, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
            assert response.status_code == 429 and response.headers["retry-after"] == "300"


def test_mobile_token_persists_across_api_restart(identity_settings: Settings) -> None:
    with TestClient(create_app(identity_settings)) as client:
        headers = mobile_login(client)
    with TestClient(create_app(identity_settings)) as restarted:
        assert restarted.get("/api/v1/auth/me", headers=headers).status_code == 200


def test_device_and_bootstrap_tokens_are_not_native_logout_sessions(
    client: TestClient, enroll_device, admin_headers: dict[str, str]
) -> None:
    device = enroll_device()
    headers = {"Authorization": f"Bearer {device['agent_token']}"}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/mobile/logout", headers=headers).status_code == 401
    assert client.post("/api/v1/auth/mobile/logout", headers=admin_headers).status_code == 401


def test_native_oidc_login_explicitly_reports_unsupported(identity_settings: Settings) -> None:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url=identity_settings.database_url,
        authentication_mode="oidc",
        oidc_server_metadata_url="https://identity.example/.well-known/openid-configuration",
        oidc_client_id="test-mobile",
        oidc_client_secret=SecretStr("test-provider-secret"),
        session_signing_secret=SecretStr("test-state-signing-secret-at-least-32-characters"),
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/auth/mobile/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 409 and "not implemented" in response.json()["detail"]
        assert "set-cookie" not in response.headers


def test_native_session_ttl_cannot_exceed_eight_hours(identity_settings: Settings) -> None:
    settings = Settings(
        _env_file=None,
        **identity_settings.model_dump(exclude={"user_session_ttl_seconds"}),
        user_session_ttl_seconds=86400,
    )
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/auth/mobile/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200 and response.json()["expires_in"] == 28800
