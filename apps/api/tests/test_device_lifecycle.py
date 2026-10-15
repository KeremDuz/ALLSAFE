import pytest


def heartbeat(client, device, inventory=None, agent_version="0.1.1"):
    body = {"device_id": device["device_id"], "agent_version": agent_version}
    if inventory is not None:
        body["inventory"] = inventory
    return client.post(
        "/api/v1/agent/heartbeat",
        headers={"Authorization": f"Bearer {device['agent_token']}"},
        json=body,
    )


def test_heartbeat_updates_device_inventory_and_last_seen(client, admin_headers, enroll_device):
    device = enroll_device()
    inventory = {
        "os_version": "Windows 11",
        "cpu_count": 8,
        "memory_total_bytes": 16 * 1024**3,
    }
    response = heartbeat(client, device, inventory)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["device_id"] == device["device_id"]
    assert updated["agent_version"] == "0.1.1"
    assert updated["last_seen_at"] is not None
    assert updated["inventory"] == inventory
    assert updated["status"] == "online"

    devices = client.get("/api/v1/devices", headers=admin_headers).json()
    assert devices[0]["inventory"] == inventory
    assert devices[0]["last_seen_at"] == updated["last_seen_at"]


def test_agent_cannot_send_heartbeat_for_another_device(client, admin_headers, enroll_device):
    first = enroll_device("first")
    second = enroll_device("second")
    response = client.post(
        "/api/v1/agent/heartbeat",
        headers={"Authorization": f"Bearer {first['agent_token']}"},
        json={"device_id": second["device_id"], "agent_version": "unauthorized-update"},
    )
    assert response.status_code in (401, 403)
    devices = client.get("/api/v1/devices", headers=admin_headers).json()
    second_record = next(item for item in devices if item["device_id"] == second["device_id"])
    assert second_record["agent_version"] == "0.1.0"
    assert second_record["last_seen_at"] is None


def test_revoke_blocks_future_heartbeats_and_is_audited(client, admin_headers, enroll_device):
    device = enroll_device()
    assert heartbeat(client, device).status_code == 200
    response = client.post(f"/api/v1/devices/{device['device_id']}/revoke", headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["revoked_at"] is not None
    assert response.json()["status"] == "revoked"
    response = heartbeat(client, device, agent_version="revoked-agent-update")
    assert response.status_code in (401, 403)

    devices = client.get("/api/v1/devices", headers=admin_headers).json()
    assert devices[0]["agent_version"] == "0.1.1"
    audit = client.get("/api/v1/audit-events", headers=admin_headers).json()
    assert any(
        event["target_id"] == device["device_id"] and "revok" in event["event_type"]
        for event in audit
    )


@pytest.mark.parametrize(
    "invalid_inventory",
    [
        {"cpu_count": 0},
        {"cpu_count": 4097},
        {"memory_total_bytes": -1},
        {"memory_total_bytes": 2**63},
        {"os_version": "x" * 256},
    ],
)
def test_invalid_inventory_is_rejected_without_updating_device(
    client, admin_headers, enroll_device, invalid_inventory
):
    device = enroll_device()
    response = heartbeat(client, device, invalid_inventory)
    assert response.status_code == 422
    devices = client.get("/api/v1/devices", headers=admin_headers).json()
    assert devices[0]["last_seen_at"] is None
    assert devices[0]["agent_version"] == "0.1.0"
