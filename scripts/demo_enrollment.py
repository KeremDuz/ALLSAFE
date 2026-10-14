"""Demonstrate a simulated device on an already running local ALLSAFE API."""

import json

import httpx
from allsafe_api.config import Settings


def main() -> None:
    settings = Settings()
    if settings.bootstrap_admin_token is None:
        raise SystemExit("Run setup.ps1 first and start the local API.")
    admin_headers = {
        "Authorization": f"Bearer {settings.bootstrap_admin_token.get_secret_value()}"
    }
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=10) as client:
        invitation = client.post(
            "/api/v1/enrollment-tokens",
            json={"label": "Demo lab device"},
            headers=admin_headers,
        )
        invitation.raise_for_status()
        enrollment = client.post(
            "/api/v1/agent/enroll",
            json={
                "enrollment_token": invitation.json()["enrollment_token"],
                "hostname": "allsafe-demo-01",
                "platform": "windows",
                "agent_version": "simulator-0.1.0",
            },
        )
        enrollment.raise_for_status()
        credential = enrollment.json()
        heartbeat = client.post(
            "/api/v1/agent/heartbeat",
            headers={"Authorization": f"Bearer {credential['agent_token']}"},
            json={
                "device_id": credential["device_id"],
                "agent_version": "simulator-0.1.0",
                "inventory": {"os_version": "Windows lab demo", "cpu_count": 4},
            },
        )
        heartbeat.raise_for_status()
        visible = client.get(
            f"/api/v1/devices/{credential['device_id']}", headers=admin_headers
        )
        visible.raise_for_status()
        print(json.dumps(visible.json(), indent=2))
        # Revoke the simulated credential rather than leave a usable demo device.
        revoked = client.post(
            f"/api/v1/devices/{credential['device_id']}/revoke", headers=admin_headers
        )
        revoked.raise_for_status()
        print("Simulated device demonstrated and revoked. No credentials printed.")


if __name__ == "__main__":
    main()
