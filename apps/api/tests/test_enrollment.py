from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from allsafe_api.main import create_app
from allsafe_api.models import Device, EnrollmentToken


def enrollment_payload(token: str, hostname: str = "workstation-01") -> dict[str, str]:
    return {
        "enrollment_token": token,
        "hostname": hostname,
        "platform": "windows",
        "agent_version": "0.1.0",
    }


def test_enrollment_token_is_single_use(client, admin_headers):
    response = client.post(
        "/api/v1/enrollment-tokens", headers=admin_headers, json={"label": "First device"}
    )
    assert response.status_code == 201, response.text
    token = response.json()["enrollment_token"]
    assert response.json()["expires_at"]

    first = client.post("/api/v1/agent/enroll", json=enrollment_payload(token))
    assert first.status_code == 201, first.text
    second = client.post(
        "/api/v1/agent/enroll", json=enrollment_payload(token, "unexpected-second-device")
    )
    assert second.status_code == 401
    devices = client.get("/api/v1/devices", headers=admin_headers).json()
    assert [device["device_id"] for device in devices] == [first.json()["device_id"]]


def test_simultaneous_enrollment_only_creates_one_device(client, admin_headers):
    response = client.post(
        "/api/v1/enrollment-tokens",
        headers=admin_headers,
        json={"label": "Concurrent enrollment"},
    )
    assert response.status_code == 201, response.text
    token = response.json()["enrollment_token"]
    start = Barrier(2, timeout=10)

    def attempt(hostname):
        start.wait()
        return client.post("/api/v1/agent/enroll", json=enrollment_payload(token, hostname))

    with ThreadPoolExecutor(max_workers=2) as workers:
        responses = list(workers.map(attempt, ["first-contender", "second-contender"]))

    assert sorted(result.status_code for result in responses) == [201, 401]
    enrolled = next(result.json() for result in responses if result.status_code == 201)
    devices = client.get("/api/v1/devices", headers=admin_headers).json()
    assert [device["device_id"] for device in devices] == [enrolled["device_id"]]
    audit = client.get("/api/v1/audit-events", headers=admin_headers).json()
    enrollment_events = [event for event in audit if event["event_type"] == "device.enrolled"]
    assert len(enrollment_events) == 1
    assert enrollment_events[0]["target_id"] == enrolled["device_id"]


def test_expired_enrollment_token_cannot_create_device(client, admin_headers):
    response = client.post(
        "/api/v1/enrollment-tokens", headers=admin_headers, json={"label": "Expiring token"}
    )
    assert response.status_code == 201, response.text
    token = response.json()["enrollment_token"]
    with client.app.state.session_factory() as session:
        stored_token = session.scalar(select(EnrollmentToken))
        assert stored_token is not None
        stored_token.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()

    response = client.post("/api/v1/agent/enroll", json=enrollment_payload(token))
    assert response.status_code == 401
    assert client.get("/api/v1/devices", headers=admin_headers).json() == []


def test_unknown_enrollment_token_is_rejected(client, admin_headers):
    response = client.post("/api/v1/agent/enroll", json=enrollment_payload("x" * 64))
    assert response.status_code == 401
    assert client.get("/api/v1/devices", headers=admin_headers).json() == []


@pytest.mark.parametrize("ttl_seconds", [0, 59, 3601])
def test_enrollment_token_lifetime_is_bounded(client, admin_headers, ttl_seconds):
    response = client.post(
        "/api/v1/enrollment-tokens",
        headers=admin_headers,
        json={"label": "Invalid lifetime", "ttl_seconds": ttl_seconds},
    )
    assert response.status_code == 422
    with client.app.state.session_factory() as session:
        assert session.scalar(select(EnrollmentToken)) is None


def test_device_and_credential_remain_valid_after_app_restart(settings, admin_headers):
    with TestClient(create_app(settings)) as first_client:
        response = first_client.post(
            "/api/v1/enrollment-tokens", headers=admin_headers, json={"label": "Persistent"}
        )
        assert response.status_code == 201, response.text
        response = first_client.post(
            "/api/v1/agent/enroll",
            json=enrollment_payload(response.json()["enrollment_token"]),
        )
        assert response.status_code == 201, response.text
        device = response.json()

    with TestClient(create_app(settings)) as second_client:
        devices = second_client.get("/api/v1/devices", headers=admin_headers).json()
        assert len(devices) == 1
        assert devices[0]["device_id"] == device["device_id"]
        response = second_client.post(
            "/api/v1/agent/heartbeat",
            headers={"Authorization": f"Bearer {device['agent_token']}"},
            json={"device_id": device["device_id"], "agent_version": "0.1.1"},
        )
        assert response.status_code == 200, response.text


def test_credentials_are_hashed_and_not_exposed_in_reads(client, admin_headers):
    response = client.post(
        "/api/v1/enrollment-tokens", headers=admin_headers, json={"label": "Secret storage"}
    )
    assert response.status_code == 201, response.text
    enrollment_token = response.json()["enrollment_token"]
    response = client.post("/api/v1/agent/enroll", json=enrollment_payload(enrollment_token))
    assert response.status_code == 201, response.text
    device = response.json()

    with client.app.state.session_factory() as session:
        stored_enrollment = session.scalar(select(EnrollmentToken))
        stored_device = session.get(Device, device["device_id"])
        assert stored_enrollment is not None and stored_device is not None
        assert enrollment_token not in stored_enrollment.token_hash
        assert device["agent_token"] not in stored_device.agent_token_hash

    for path in ("/api/v1/devices", "/api/v1/audit-events"):
        response = client.get(path, headers=admin_headers)
        assert response.status_code == 200, response.text
        assert enrollment_token not in response.text
        assert device["agent_token"] not in response.text
        assert stored_enrollment.token_hash not in response.text
        assert stored_device.agent_token_hash not in response.text
        assert "token_hash" not in response.text
