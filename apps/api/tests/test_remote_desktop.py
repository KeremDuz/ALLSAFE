"""Desktop consent, ownership, bounded relay and revocation without screen capture."""

import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.websockets import WebSocketDisconnect

from allsafe_api.main import create_app
from allsafe_api.models import AuditEvent, Device, User, utc_now
from allsafe_api.remote_desktop import relay as relay_module
from allsafe_api.remote_desktop.models import DesktopSession
from allsafe_api.remote_desktop.relay import MAX_FRAME_BYTES
from allsafe_api.security import hash_token

ROOT = "/api/v1/remote-desktop/sessions"
AGENT = "/api/v1/agent/remote-desktop"
ORIGIN = "http://127.0.0.1:5173"


def jpeg(width: int = 1280, height: int = 720) -> bytes:
    # Synthetic baseline frame headers. The relay never decodes image pixels.
    sof = (
        b"\xff\xc0\x00\x0b\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
    )
    sos = b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00"
    return b"\xff\xd8" + sof + sos + b"\x00\xff\xd9"


JPEG = jpeg()


@dataclass
class Lab:
    client: TestClient
    token: str
    csrf: str
    device: dict[str, str]

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Cookie": f"allsafe_session={self.token}; allsafe_csrf={self.csrf}",
            "X-CSRF-Token": self.csrf,
        }

    @property
    def viewer_headers(self) -> dict[str, str]:
        return {**self.headers, "Origin": ORIGIN}

    @property
    def agent_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.device['agent_token']}"}

    def request(self, mode: str = "control") -> dict[str, Any]:
        response = self.client.post(
            ROOT,
            headers=self.headers,
            json={
                "device_id": self.device["device_id"],
                "reason": "Help with a display issue",
                "mode": mode,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    def decide(self, session_id: str, approved: bool = True):
        return self.client.post(
            f"{AGENT}/sessions/{session_id}/decision",
            headers=self.agent_headers,
            json={"device_id": self.device["device_id"], "approved": approved},
        )

    def state(self, session_id: str) -> dict[str, Any]:
        return self.client.get(f"{ROOT}/{session_id}", headers=self.headers).json()


@pytest.fixture
def lab(identity_client: TestClient):
    response = identity_client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@allsafe.local",
            "password": "Test-Admin-Password-1234",
        },
    )
    assert response.status_code == 200
    token = response.cookies["allsafe_session"]
    csrf = response.cookies["allsafe_csrf"]
    headers = {"X-CSRF-Token": csrf}
    invitation = identity_client.post(
        "/api/v1/enrollment-tokens",
        headers=headers,
        json={"label": "desktop-lab", "ttl_seconds": 900},
    ).json()
    device = identity_client.post(
        "/api/v1/agent/enroll",
        json={
            "enrollment_token": invitation["enrollment_token"],
            "hostname": "desktop-test",
            "platform": "windows",
            "agent_version": "0.1.0",
        },
    ).json()
    assert (
        identity_client.post(
            "/api/v1/agent/heartbeat",
            headers={"Authorization": f"Bearer {device['agent_token']}"},
            json={"device_id": device["device_id"], "agent_version": "0.1.0"},
        ).status_code
        == 200
    )
    return Lab(identity_client, token, csrf, device)


@contextmanager
def connected(lab: Lab, mode: str = "control"):
    desktop = lab.request(mode)
    session_id = desktop["id"]
    assert lab.decide(session_id).json()["status"] == "approved"
    with lab.client.websocket_connect(
        f"{AGENT}/sessions/{session_id}/stream", headers=lab.agent_headers
    ) as agent:
        agent.send_json({"type": "hello", "device_id": lab.device["device_id"]})
        with lab.client.websocket_connect(
            f"{ROOT}/{session_id}/viewer", headers=lab.viewer_headers
        ) as viewer:
            viewer.send_json({"type": "hello", "csrf": lab.csrf})
            assert viewer.receive_json() == {"type": "ready"}
            assert agent.receive_json() == {"type": "ready"}
            yield session_id, viewer, agent


def test_human_web_session_and_csrf_required(lab: Lab):
    payload = {"device_id": lab.device["device_id"], "reason": "Test reason", "mode": "view"}
    lab.client.cookies.clear()
    assert lab.client.post(ROOT, json=payload).status_code == 401
    assert (
        lab.client.post(
            ROOT, headers={"Cookie": f"allsafe_session={lab.token}"}, json=payload
        ).status_code
        == 403
    )
    assert (
        lab.client.post(
            ROOT, headers={**lab.headers, "Origin": "https://evil.example"}, json=payload
        ).status_code
        == 403
    )
    mobile = lab.client.post(
        "/api/v1/auth/mobile/login",
        json={"email": "admin@allsafe.local", "password": "Test-Admin-Password-1234"},
    )
    assert mobile.status_code == 200
    assert (
        lab.client.post(
            ROOT, headers={"Authorization": f"Bearer {mobile.json()['access_token']}"}, json=payload
        ).status_code
        == 403
    )


def test_bootstrap_is_not_a_human_session(client, admin_headers, enroll_device):
    device = enroll_device()
    assert (
        client.post(
            ROOT,
            headers=admin_headers,
            json={"device_id": device["device_id"], "reason": "Test reason", "mode": "view"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "field,value", [("role", "analyst"), ("role", "employee"), ("active", False)]
)
def test_only_active_admin_can_request(lab: Lab, field, value):
    with lab.client.app.state.session_factory.begin() as database:
        user = database.scalar(select(User).where(User.email == "admin@allsafe.local"))
        setattr(user, field, value)
    response = lab.client.post(
        ROOT,
        headers=lab.headers,
        json={"device_id": lab.device["device_id"], "reason": "Test reason", "mode": "view"},
    )
    assert response.status_code == (401 if field == "active" else 403)


@pytest.mark.parametrize(
    "field,value", [("platform", "linux"), ("revoked_at", True), ("last_seen_at", None)]
)
def test_only_online_nonrevoked_windows_device(lab: Lab, field, value):
    with lab.client.app.state.session_factory.begin() as database:
        device = database.get(Device, lab.device["device_id"])
        setattr(device, field, utc_now() if value is True else value)
    response = lab.client.post(
        ROOT,
        headers=lab.headers,
        json={"device_id": lab.device["device_id"], "reason": "Test reason", "mode": "view"},
    )
    assert response.status_code == 409


def test_request_pending_consent_denial_and_audit(lab: Lab):
    desktop = lab.request()
    assert desktop["status"] == "pending"
    pending = lab.client.get(
        f"{AGENT}/pending", headers=lab.agent_headers, params={"device_id": lab.device["device_id"]}
    )
    assert pending.json()["sessions"] == [desktop]
    denied = lab.decide(desktop["id"], approved=False).json()
    assert denied["status"] == "denied"
    assert lab.decide(desktop["id"]).json()["status"] == "denied"
    assert lab.request()["id"] != desktop["id"]
    with lab.client.app.state.session_factory() as database:
        events = list(
            database.scalars(select(AuditEvent).where(AuditEvent.target_id == desktop["id"]))
        )
    assert {event.event_type for event in events} == {"desktop.requested", "desktop.denied"}
    assert all("reason" not in event.details and "frame" not in event.details for event in events)


def test_session_is_owned_by_exact_login_not_same_admin(lab: Lab):
    desktop = lab.request()
    lab.client.cookies.clear()
    other = lab.client.post(
        "/api/v1/auth/login",
        json={"email": "admin@allsafe.local", "password": "Test-Admin-Password-1234"},
    )
    other_headers = {
        "Cookie": f"allsafe_session={other.cookies['allsafe_session']}; "
        f"allsafe_csrf={other.cookies['allsafe_csrf']}",
        "X-CSRF-Token": other.cookies["allsafe_csrf"],
    }
    assert lab.client.get(f"{ROOT}/{desktop['id']}", headers=other_headers).status_code == 404
    assert (
        lab.client.post(f"{ROOT}/{desktop['id']}/close", headers=other_headers).status_code == 404
    )
    assert (
        lab.client.post(f"{ROOT}/{desktop['id']}/close", headers=lab.headers).json()["status"]
        == "closed"
    )


def test_parallel_requests_reserve_one_device(lab: Lab):
    barrier = Barrier(2)

    def request():
        barrier.wait()
        return lab.client.post(
            ROOT,
            headers=lab.headers,
            json={"device_id": lab.device["device_id"], "reason": "Test reason", "mode": "view"},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: request(), range(2)))
    assert sorted(results) == [201, 409]


def test_expired_consent_cannot_be_approved_and_reservation_releases(lab: Lab):
    desktop = lab.request()
    with lab.client.app.state.session_factory.begin() as database:
        database.get(DesktopSession, desktop["id"]).expires_at = utc_now() - timedelta(seconds=1)
    assert lab.decide(desktop["id"]).json()["status"] == "expired"
    assert lab.state(desktop["id"])["closed_reason"] == "consent_timeout"
    assert lab.request()["status"] == "pending"


def test_wrong_device_cannot_read_or_decide(lab: Lab):
    desktop = lab.request()
    headers = {"Authorization": "Bearer " + "x" * 43}
    assert (
        lab.client.get(
            f"{AGENT}/pending", headers=headers, params={"device_id": lab.device["device_id"]}
        ).status_code
        == 401
    )
    assert (
        lab.client.post(
            f"{AGENT}/sessions/{desktop['id']}/decision",
            headers=headers,
            json={"device_id": lab.device["device_id"], "approved": True},
        ).status_code
        == 401
    )
    assert lab.state(desktop["id"])["status"] == "pending"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_viewer_requires_explicit_trusted_origin(lab: Lab, headers):
    desktop = lab.request()
    assert lab.decide(desktop["id"]).status_code == 200
    with (
        pytest.raises(WebSocketDisconnect),
        lab.client.websocket_connect(
            f"{ROOT}/{desktop['id']}/viewer", headers={**lab.headers, **headers}
        ),
    ):
        pass


@pytest.mark.parametrize(
    "hello",
    [
        {"type": "hello", "csrf": "x" * 43},
        {"type": "hello", "csrf": "short"},
        {"type": "hello", "csrf": "x" * 43, "extra": True},
    ],
)
def test_viewer_rejects_bad_first_hello(lab: Lab, hello):
    desktop = lab.request()
    assert lab.decide(desktop["id"]).status_code == 200
    with lab.client.websocket_connect(
        f"{ROOT}/{desktop['id']}/viewer", headers=lab.viewer_headers
    ) as viewer:
        viewer.send_json(hello)
        with pytest.raises(WebSocketDisconnect):
            viewer.receive_json()


def test_agent_rejects_browser_origin_and_url_token(lab: Lab):
    desktop = lab.request()
    assert lab.decide(desktop["id"]).status_code == 200
    for path, headers in [
        (f"{AGENT}/sessions/{desktop['id']}/stream", {**lab.agent_headers, "Origin": ORIGIN}),
        (f"{AGENT}/sessions/{desktop['id']}/stream?token=forbidden", lab.agent_headers),
    ]:
        with (
            pytest.raises(WebSocketDisconnect),
            lab.client.websocket_connect(path, headers=headers),
        ):
            pass


def test_agent_cannot_stream_before_local_consent(lab: Lab):
    desktop = lab.request()
    with (
        pytest.raises(WebSocketDisconnect),
        lab.client.websocket_connect(
            f"{AGENT}/sessions/{desktop['id']}/stream", headers=lab.agent_headers
        ),
    ):
        pass
    assert lab.state(desktop["id"])["status"] == "pending"


def test_bidirectional_relay_close_and_metadata_only_audit(lab: Lab):
    with connected(lab) as (session_id, viewer, agent):
        assert lab.state(session_id)["status"] == "active"
        display = {"type": "display", "width": 1280, "height": 720}
        agent.send_json(display)
        assert viewer.receive_json() == display
        agent.send_bytes(JPEG)
        assert viewer.receive_bytes() == JPEG
        for event in [
            {"type": "pointer", "action": "move", "x": 0.25, "y": 0.75, "button": "left"},
            {"type": "wheel", "delta": -120},
            {"type": "key", "action": "down", "code": "KeyA"},
            {"type": "key", "action": "up", "code": "KeyA"},
            {"type": "release"},
        ]:
            viewer.send_json(event)
            assert agent.receive_json() == event
        assert (
            lab.client.post(f"{ROOT}/{session_id}/close", headers=lab.headers).json()["status"]
            == "closed"
        )
        assert viewer.receive_json()["type"] == "closed"
    with lab.client.app.state.session_factory() as database:
        events = list(
            database.scalars(select(AuditEvent).where(AuditEvent.target_id == session_id))
        )
    assert {event.event_type for event in events} == {
        "desktop.requested",
        "desktop.approved",
        "desktop.started",
        "desktop.closed",
    }
    assert all(set(event.details) == {"device_id", "mode", "closed_reason"} for event in events)


def test_view_mode_disallows_input(lab: Lab):
    with connected(lab, "view") as (session_id, viewer, agent):
        viewer.send_json({"type": "key", "action": "down", "code": "KeyA"})
        assert viewer.receive_json()["type"] == "closed"
        assert lab.state(session_id)["closed_reason"] == "protocol_violation"


@pytest.mark.parametrize(
    "event",
    [
        {"type": "key", "action": "down", "code": "MetaLeft"},
        {"type": "key", "action": "down", "code": "KeyA", "shell": "forbidden"},
        {"type": "pointer", "action": "move", "x": 2, "y": 0.5, "button": "left"},
        {"type": "wheel", "delta": 1201},
        {"type": "wheel", "delta": True},
        {"type": "clipboard", "text": "forbidden"},
    ],
)
def test_invalid_input_terminates_session(lab: Lab, event):
    with connected(lab) as (session_id, viewer, agent):
        viewer.send_json(event)
        assert viewer.receive_json()["type"] == "closed"
        assert lab.state(session_id)["closed_reason"] == "protocol_violation"


@pytest.mark.parametrize("kind", ["no_display", "oversized", "not_jpeg", "display_bounds"])
def test_frame_protocol_bounds(lab: Lab, kind):
    with connected(lab) as (session_id, viewer, agent):
        if kind == "display_bounds":
            agent.send_json({"type": "display", "width": 1921, "height": 1080})
        else:
            if kind != "no_display":
                agent.send_json({"type": "display", "width": 1920, "height": 1080})
                assert viewer.receive_json()["type"] == "display"
            frame = (
                b"\xff\xd8" + b"x" * MAX_FRAME_BYTES + b"\xff\xd9"
                if kind == "oversized"
                else b"invalid"
                if kind == "not_jpeg"
                else JPEG
            )
            agent.send_bytes(frame)
        assert viewer.receive_json()["type"] == "closed"
        assert lab.state(session_id)["closed_reason"] == "protocol_violation"


def test_frame_rate_is_bounded(lab: Lab):
    with connected(lab) as (session_id, viewer, agent):
        agent.send_json({"type": "display", "width": 1920, "height": 1080})
        assert viewer.receive_json()["type"] == "display"
        for _ in range(5):
            agent.send_bytes(jpeg(1920, 1080))
            assert viewer.receive_bytes() == jpeg(1920, 1080)
        agent.send_bytes(jpeg(1920, 1080))
        assert viewer.receive_json()["type"] == "closed"


@pytest.mark.parametrize("change", ["rotate", "revoke", "logout", "role", "expiry"])
def test_live_session_closes_on_authorization_or_expiry_change(lab: Lab, change):
    with connected(lab) as (session_id, viewer, agent):
        if change in {"rotate", "revoke"}:
            action = "rotate-token" if change == "rotate" else "revoke"
            assert (
                lab.client.post(
                    f"/api/v1/devices/{lab.device['device_id']}/{action}", headers=lab.headers
                ).status_code
                == 200
            )
        elif change == "logout":
            assert lab.client.post("/api/v1/auth/logout", headers=lab.headers).status_code == 204
        else:
            with lab.client.app.state.session_factory.begin() as database:
                desktop = database.get(DesktopSession, session_id)
                if change == "expiry":
                    desktop.expires_at = utc_now() - timedelta(seconds=1)
                else:
                    database.get(User, desktop.operator_id).role = "analyst"
        assert viewer.receive_json()["type"] == "closed"
        with lab.client.app.state.session_factory() as database:
            assert database.get(DesktopSession, session_id).status in {"closed", "expired"}


def test_revalidate_before_forwarding_input(lab: Lab):
    with connected(lab) as (session_id, viewer, agent):
        with lab.client.app.state.session_factory.begin() as database:
            database.get(Device, lab.device["device_id"]).agent_token_hash = hash_token("changed")
        viewer.send_json({"type": "key", "action": "down", "code": "KeyA"})
        # The agent receives closure, never the input under the old credential.
        assert agent.receive_json()["type"] == "closed"


def test_local_stop_and_reconnect_replay_rejected(lab: Lab):
    with connected(lab) as (session_id, viewer, agent):
        agent.send_json({"type": "stop"})
        assert viewer.receive_json() == {"type": "closed", "reason": "local_user_stopped"}
        assert lab.state(session_id)["closed_reason"] == "local_user_stopped"
    with (
        pytest.raises(WebSocketDisconnect),
        lab.client.websocket_connect(f"{ROOT}/{session_id}/viewer", headers=lab.viewer_headers),
    ):
        pass


def test_duplicate_viewer_cannot_replace_existing_peer(lab: Lab):
    with connected(lab) as (session_id, viewer, agent):
        with lab.client.websocket_connect(
            f"{ROOT}/{session_id}/viewer", headers=lab.viewer_headers
        ) as duplicate:
            duplicate.send_json({"type": "hello", "csrf": lab.csrf})
            with pytest.raises(WebSocketDisconnect):
                duplicate.receive_json()
        assert lab.state(session_id)["status"] == "active"
        agent.send_json({"type": "display", "width": 800, "height": 600})
        assert viewer.receive_json()["type"] == "display"


def test_peer_disconnect_closes_and_releases_reservation(lab: Lab):
    with connected(lab) as (session_id, viewer, agent):
        viewer.close()
        assert agent.receive_json()["type"] == "closed"
    assert lab.state(session_id)["status"] == "closed"
    assert lab.request()["status"] == "pending"


def test_restart_invalidates_pending_or_approved_consent(lab: Lab, identity_settings):
    desktop = lab.request()
    assert lab.decide(desktop["id"]).json()["status"] == "approved"
    with TestClient(create_app(identity_settings)) as restarted:
        response = restarted.get(f"{ROOT}/{desktop['id']}", headers=lab.headers)
        assert response.json()["status"] == "closed"
        assert response.json()["closed_reason"] == "server_restart"


def test_unauthed_websockets_rejected_before_accept(lab: Lab):
    desktop = lab.request()
    assert lab.decide(desktop["id"]).status_code == 200
    lab.client.cookies.clear()
    for path, headers in [
        (f"{ROOT}/{desktop['id']}/viewer", {"Origin": ORIGIN}),
        (f"{AGENT}/sessions/{desktop['id']}/stream", {"Authorization": "Bearer " + "x" * 43}),
    ]:
        with (
            pytest.raises(WebSocketDisconnect),
            lab.client.websocket_connect(path, headers=headers),
        ):
            pytest.fail("Unauthenticated socket was accepted")
    assert lab.state(desktop["id"])["status"] == "approved"


def test_authenticated_hello_has_deadline(lab: Lab, monkeypatch):
    monkeypatch.setattr(relay_module, "HELLO_TIMEOUT", 0.02)
    desktop = lab.request()
    assert lab.decide(desktop["id"]).status_code == 200
    with lab.client.websocket_connect(
        f"{ROOT}/{desktop['id']}/viewer", headers=lab.viewer_headers
    ) as viewer:
        with pytest.raises(WebSocketDisconnect):
            viewer.receive_json()


def test_first_peer_disconnect_and_local_stop_before_pair(lab: Lab):
    for stop in (True, False):
        desktop = lab.request()
        assert lab.decide(desktop["id"]).status_code == 200
        with lab.client.websocket_connect(
            f"{AGENT}/sessions/{desktop['id']}/stream", headers=lab.agent_headers
        ) as agent:
            agent.send_json({"type": "hello", "device_id": lab.device["device_id"]})
            if stop:
                agent.send_json({"type": "stop"})
                assert agent.receive_json()["reason"] == "local_user_stopped"
            else:
                agent.close()
        for _ in range(40):
            if lab.state(desktop["id"])["status"] == "closed":
                break
            time.sleep(0.05)
        assert lab.state(desktop["id"])["status"] == "closed"


def test_input_rate_is_bounded(lab: Lab, monkeypatch):
    from types import SimpleNamespace

    # Freeze only the relay's traffic window, without changing asyncio's clock.
    monkeypatch.setattr(relay_module, "time", SimpleNamespace(monotonic=lambda: 10.0))
    with connected(lab) as (session_id, viewer, agent):
        for _ in range(100):
            viewer.send_json({"type": "release"})
            assert agent.receive_json() == {"type": "release"}
        viewer.send_json({"type": "release"})
        assert viewer.receive_json()["type"] == "closed"
        assert lab.state(session_id)["closed_reason"] == "protocol_violation"


def test_rotation_invalidates_approved_grant_before_agent_joins(lab: Lab):
    desktop = lab.request()
    assert lab.decide(desktop["id"]).status_code == 200
    assert (
        lab.client.post(
            f"/api/v1/devices/{lab.device['device_id']}/rotate-token", headers=lab.headers
        ).status_code
        == 200
    )
    assert lab.state(desktop["id"])["status"] == "closed"
    assert lab.state(desktop["id"])["closed_reason"] == "device_credentials_changed"


@pytest.mark.parametrize("width,height", [(1280, 720), (65535, 65535)])
def test_jpeg_dimensions_must_match_display_and_limits(lab: Lab, width, height):
    with connected(lab) as (session_id, viewer, agent):
        agent.send_json({"type": "display", "width": 1920, "height": 1080})
        assert viewer.receive_json()["type"] == "display"
        agent.send_bytes(jpeg(width, height))
        assert viewer.receive_json()["type"] == "closed"
        assert lab.state(session_id)["closed_reason"] == "protocol_violation"


def test_authorization_database_failure_closes_transport(lab: Lab, monkeypatch):
    with connected(lab) as (session_id, viewer, agent):

        def unavailable(*args, **kwargs):
            raise SQLAlchemyError("No private connection details should be logged")

        monkeypatch.setattr(lab.client.app.state.desktop_relay, "validate", unavailable)
        viewer.send_json({"type": "key", "action": "down", "code": "KeyA"})
        assert agent.receive_json() == {"type": "closed", "reason": "state_unavailable"}
        assert viewer.receive_json()["type"] == "closed"


def test_persistence_failure_does_not_leave_transport_open(lab: Lab, monkeypatch, caplog):
    with connected(lab) as (session_id, viewer, agent):

        def unavailable(*args, **kwargs):
            raise SQLAlchemyError("sensitive-value-must-not-be-logged")

        monkeypatch.setattr(lab.client.app.state.desktop_relay, "finish_sql", unavailable)
        agent.send_json({"type": "stop"})
        assert viewer.receive_json()["type"] == "closed"
        assert agent.receive_json()["type"] == "closed"
        assert "sensitive-value-must-not-be-logged" not in caplog.text
