"""OIDC application policy with provider responses stubbed after Authlib verification.

These tests do not replace an end-to-end test against a configured identity provider.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from authlib.integrations.base_client.errors import OAuthError
from fastapi import Request
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from test_identity import ADMIN_EMAIL, ADMIN_PASSWORD, create_user, login

from allsafe_api.config import Settings
from allsafe_api.main import create_app
from allsafe_api.models import User

ISSUER = "https://identity.example"
SUBJECT = "employee-provider-id"


@dataclass
class VerifiedProviderStub:
    token: dict[str, Any]
    error: OAuthError | None = None

    def create_client(self, name: str) -> "VerifiedProviderStub":
        assert name == "organization"
        return self

    async def authorize_access_token(self, _: Request) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.token


def prepare_oidc_settings(local_settings: Settings) -> tuple[Settings, dict[str, Any]]:
    with TestClient(create_app(local_settings)) as local_client:
        administrator = login(local_client)
        employee = create_user(local_client, administrator)
        response = local_client.post(
            f"/api/v1/users/{employee['id']}/oidc",
            headers=administrator.headers(),
            json={"issuer": ISSUER, "subject": SUBJECT},
        )
        assert response.status_code == 200, response.text
    oidc_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=local_settings.database_url,
        initialize_schema=True,
        bootstrap_admin_token=None,
        authentication_mode="oidc",
        oidc_server_metadata_url=f"{ISSUER}/.well-known/openid-configuration",
        oidc_client_id="allsafe-test-client",
        oidc_client_secret=SecretStr("test-provider-client-secret"),
        session_signing_secret=SecretStr("test-state-signing-secret-at-least-32-characters"),
        cookie_secure=False,
        frontend_url="http://127.0.0.1:5173",
    )
    return oidc_settings, employee


def verified_token(email: str) -> dict[str, Any]:
    return {
        "id_token": "stubbed-verified-provider-token",
        "userinfo": {
            "iss": ISSUER,
            "sub": SUBJECT,
            "email": email,
            "email_verified": True,
        },
    }


def test_local_mode_does_not_offer_oidc_login(identity_client: TestClient) -> None:
    assert identity_client.get("/api/v1/auth/config").json() == {
        "mode": "local",
        "oidc_enabled": False,
    }
    assert identity_client.get("/api/v1/auth/oidc/login").status_code == 503
    assert identity_client.get("/api/v1/auth/oidc/callback").status_code == 503


def test_oidc_configuration_requires_credentials_and_signing_secret() -> None:
    with pytest.raises(ValidationError, match="OIDC requires"):
        Settings(_env_file=None, authentication_mode="oidc")


@pytest.mark.parametrize(
    "browser_url",
    [
        {"frontend_url": "https://panel.example"},
        {"api_url": "https://api.example"},
        {"oidc_redirect_uri": "https://api.example/api/v1/auth/oidc/callback"},
    ],
)
def test_non_loopback_oidc_browser_urls_require_secure_cookies(
    browser_url: dict[str, str],
) -> None:
    configuration = {
        "authentication_mode": "oidc",
        "oidc_server_metadata_url": f"{ISSUER}/.well-known/openid-configuration",
        "oidc_client_id": "allsafe-test-client",
        "oidc_client_secret": SecretStr("test-provider-client-secret"),
        "session_signing_secret": SecretStr("test-state-signing-secret-at-least-32-characters"),
        **browser_url,
    }
    with pytest.raises(ValidationError, match="requires secure cookies"):
        Settings(_env_file=None, cookie_secure=False, **configuration)
    assert Settings(_env_file=None, cookie_secure=True, **configuration).cookie_secure is True


def test_oidc_uses_explicit_identity_mapping_without_changing_role(
    identity_settings: Settings,
) -> None:
    settings, employee = prepare_oidc_settings(identity_settings)
    with TestClient(create_app(settings)) as client:
        client.app.state.oauth = VerifiedProviderStub(verified_token(employee["email"]))
        response = client.get("/api/v1/auth/oidc/callback", follow_redirects=False)
        assert response.status_code == 303, response.text
        assert response.headers["location"] == settings.frontend_url
        assert "allsafe_session" in response.cookies
        current = client.get("/api/v1/auth/me")
        assert current.status_code == 200, current.text
        assert current.json()["id"] == employee["id"]
        assert current.json()["role"] == "employee"
        assert "users:manage" not in current.json()["permissions"]
        assert client.get("/api/v1/devices").status_code == 403
        assert client.get("/api/v1/auth/config").json() == {"mode": "oidc", "oidc_enabled": True}
        assert (
            client.post(
                "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            ).status_code
            == 409
        )


@pytest.mark.parametrize(
    "claim_changes",
    [
        {"email_verified": False},
        {"email_verified": "true"},
        {"email_verified": None},
        {"iss": "https://different-provider.example"},
        {"sub": "unmapped-provider-id"},
        {"email": ADMIN_EMAIL},
        {"sub": None},
    ],
)
def test_oidc_rejects_unverified_or_mismatched_identity_claims(
    identity_settings: Settings, claim_changes: dict[str, Any]
) -> None:
    settings, employee = prepare_oidc_settings(identity_settings)
    token = verified_token(employee["email"])
    token["userinfo"].update(claim_changes)
    with TestClient(create_app(settings)) as client:
        client.app.state.oauth = VerifiedProviderStub(token)
        response = client.get("/api/v1/auth/oidc/callback", follow_redirects=False)
        assert response.status_code == 401, response.text
        assert "allsafe_session" not in response.cookies
        assert client.get("/api/v1/auth/me").status_code == 401
        with client.app.state.session_factory() as database:
            assert len(database.scalars(select(User)).all()) == 2


def test_oidc_rejects_access_token_without_id_token(identity_settings: Settings) -> None:
    settings, employee = prepare_oidc_settings(identity_settings)
    token = verified_token(employee["email"])
    del token["id_token"]
    with TestClient(create_app(settings)) as client:
        client.app.state.oauth = VerifiedProviderStub(token)
        response = client.get("/api/v1/auth/oidc/callback", follow_redirects=False)
        assert response.status_code == 401, response.text
        assert "allsafe_session" not in response.cookies


def test_oidc_state_validation_error_does_not_issue_user_session(
    identity_settings: Settings,
) -> None:
    settings, employee = prepare_oidc_settings(identity_settings)
    with TestClient(create_app(settings)) as client:
        client.app.state.oauth = VerifiedProviderStub(
            verified_token(employee["email"]), error=OAuthError(error="invalid_state")
        )
        response = client.get("/api/v1/auth/oidc/callback", follow_redirects=False)
        assert response.status_code == 401, response.text
        assert "allsafe_session" not in response.cookies
        assert client.get("/api/v1/auth/me").status_code == 401
