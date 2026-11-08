from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError

from allsafe_api.config import Settings
from allsafe_api.main import create_app

ADMIN_EMAIL = "admin@allsafe.local"
LOOPBACK = ("127.0.0.1", 50000)


def dev_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "development",
        "database_url": f"sqlite:///{(tmp_path / 'dev.db').as_posix()}",
        "initialize_schema": True,
        "bootstrap_admin_token": None,
        "authentication_mode": "local",
        "initial_admin_email": ADMIN_EMAIL,
        "initial_admin_password": SecretStr("Test-Admin-Password-1234"),
        "frontend_url": "http://127.0.0.1:5173",
        "dev_auto_login": True,
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def dev_client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(dev_settings(tmp_path)), client=LOOPBACK) as test_client:
        yield test_client


def test_auto_login_is_disabled_by_default(identity_client: TestClient) -> None:
    assert identity_client.get("/api/v1/auth/config").json()["dev_auto_login"] is False
    assert identity_client.post("/api/v1/auth/dev-login").status_code == 404
    assert identity_client.get("/api/v1/auth/me").status_code == 401


def test_auto_login_opens_an_audited_administrator_session(dev_client: TestClient) -> None:
    assert dev_client.get("/api/v1/auth/config").json()["dev_auto_login"] is True

    response = dev_client.post("/api/v1/auth/dev-login")

    assert response.status_code == 200, response.text
    assert response.json()["email"] == ADMIN_EMAIL
    assert response.json()["role"] == "admin"
    cookies = response.headers.get_list("set-cookie")
    assert any(value.startswith("allsafe_session=") for value in cookies)
    assert dev_client.get("/api/v1/auth/me").json() == response.json()
    events = dev_client.get("/api/v1/audit-events").json()
    assert "auth.dev_auto_login" in {event["event_type"] for event in events}


def test_auto_login_rejects_untrusted_origin(dev_client: TestClient) -> None:
    response = dev_client.post(
        "/api/v1/auth/dev-login", headers={"Origin": "https://untrusted.example"}
    )
    assert response.status_code == 403


def test_auto_login_rejects_non_loopback_clients(tmp_path: Path) -> None:
    with TestClient(create_app(dev_settings(tmp_path)), client=("192.0.2.10", 50000)) as client:
        assert client.post("/api/v1/auth/dev-login").status_code == 403


@pytest.mark.parametrize(
    "overrides",
    [
        {"environment": "test"},
        {"environment": "production"},
        {"frontend_url": "https://panel.example"},
        {"api_url": "http://192.0.2.10:8000"},
    ],
)
def test_auto_login_is_refused_outside_loopback_development(
    tmp_path: Path, overrides: dict[str, object]
) -> None:
    with pytest.raises(ValidationError, match="Development auto-login"):
        dev_settings(tmp_path, **overrides)
