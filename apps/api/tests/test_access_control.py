import pytest
from fastapi.testclient import TestClient

from allsafe_api.main import create_app


@pytest.mark.parametrize("path", ["/api/v1/modules", "/api/v1/devices", "/api/v1/audit-events"])
def test_management_reads_require_valid_admin_authentication(client, path):
    assert client.get(path).status_code == 401
    response = client.get(path, headers={"Authorization": "Bearer wrong-token"})
    assert response.status_code == 401


def test_admin_can_list_management_resources(client, admin_headers):
    for path in ("/api/v1/modules", "/api/v1/devices", "/api/v1/audit-events"):
        response = client.get(path, headers=admin_headers)
        assert response.status_code == 200, response.text
        assert isinstance(response.json(), list)


def test_device_credential_cannot_read_or_change_management_resources(client, enroll_device):
    device = enroll_device()
    agent_headers = {"Authorization": f"Bearer {device['agent_token']}"}
    for path in ("/api/v1/modules", "/api/v1/devices", "/api/v1/audit-events"):
        assert client.get(path, headers=agent_headers).status_code in (401, 403)
    response = client.post(
        "/api/v1/enrollment-tokens", headers=agent_headers, json={"label": "unauthorized"}
    )
    assert response.status_code in (401, 403)
    response = client.post(f"/api/v1/devices/{device['device_id']}/revoke", headers=agent_headers)
    assert response.status_code in (401, 403)


def test_admin_credential_cannot_impersonate_device(client, admin_headers, enroll_device):
    device = enroll_device()
    response = client.post(
        "/api/v1/agent/heartbeat",
        headers=admin_headers,
        json={"device_id": device["device_id"], "agent_version": "0.1.0"},
    )
    assert response.status_code in (401, 403)


def test_unconfigured_admin_access_fails_closed(settings):
    settings.bootstrap_admin_token = None
    with TestClient(create_app(settings)) as client:
        for header in ({}, {"Authorization": "Bearer test-admin-secret"}):
            response = client.get("/api/v1/devices", headers=header)
            assert response.status_code in (401, 403, 503)


def test_liveness_and_readiness_are_public(client):
    assert client.get("/health").status_code == 200
    assert client.get("/health/ready").status_code == 200
