from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from allsafe_api.config import Settings
from allsafe_api.main import create_app

ADMIN_TOKEN = "test-admin-secret"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'allsafe.db').as_posix()}",
        initialize_schema=True,
        bootstrap_admin_token=SecretStr(ADMIN_TOKEN),
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def identity_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url=f"sqlite:///{(tmp_path / 'identity.db').as_posix()}",
        initialize_schema=True,
        bootstrap_admin_token=None,
        authentication_mode="local",
        initial_admin_email="admin@allsafe.local",
        initial_admin_password=SecretStr("Test-Admin-Password-1234"),
        cookie_secure=False,
        frontend_url="http://127.0.0.1:5173",
    )


@pytest.fixture
def identity_client(identity_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(identity_settings)) as test_client:
        yield test_client


@pytest.fixture
def admin_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {ADMIN_TOKEN}"}


@pytest.fixture
def enroll_device(
    client: TestClient, admin_headers: dict[str, str]
) -> Callable[..., dict[str, str]]:
    def enroll(hostname: str = "workstation-01") -> dict[str, str]:
        response = client.post(
            "/api/v1/enrollment-tokens",
            headers=admin_headers,
            json={"label": hostname, "ttl_seconds": 900},
        )
        assert response.status_code == 201, response.text
        response = client.post(
            "/api/v1/agent/enroll",
            json={
                "enrollment_token": response.json()["enrollment_token"],
                "hostname": hostname,
                "platform": "windows",
                "agent_version": "0.1.0",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return enroll
