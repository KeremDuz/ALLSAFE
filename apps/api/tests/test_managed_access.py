"""Real ephemeral SSH transport with synthetic PTY data; no OS commands or services."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from threading import Barrier
from typing import Any

import asyncssh
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from starlette.websockets import WebSocketDisconnect

from allsafe_api.main import create_app
from allsafe_api.managed_access import transport
from allsafe_api.managed_access.configuration import ConfigurationError, resolve_profile
from allsafe_api.managed_access.models import TerminalSession
from allsafe_api.models import AuditEvent, Device, User, UserSession, utc_now

ROOT = "/api/v1/managed-access"
ORIGIN = "http://127.0.0.1:5173"


@dataclass
class SyntheticHost:
    client_key: Any = field(default_factory=lambda: asyncssh.generate_private_key("ssh-ed25519"))
    host_key: Any = field(default_factory=lambda: asyncssh.generate_private_key("ssh-ed25519"))
    inputs: list[str] = field(default_factory=list)
    sizes: list[tuple[int, int]] = field(default_factory=list)
    sessions: list[Any] = field(default_factory=list)
    disconnected: list[bool] = field(default_factory=list)
    banner: str = "Synthetic SSH ready\r\n"


class SyntheticSession(asyncssh.SSHServerSession[str]):
    def __init__(self, host: SyntheticHost):
        self.host = host
        self.channel: Any = None

    def connection_made(self, channel: Any) -> None:
        self.channel = channel
        self.host.sessions.append(self)

    def pty_requested(self, term_type: str, term_size: Any, term_modes: Any) -> bool:
        assert term_type == "xterm-256color"
        self.host.sizes.append(term_size[:2])
        return True

    def terminal_size_changed(self, width: int, height: int, pixwidth: int, pixheight: int) -> None:
        self.host.sizes.append((width, height))

    def shell_requested(self) -> bool:
        return True

    def session_started(self) -> None:
        self.channel.write(self.host.banner)

    def data_received(self, data: str, datatype: int | None) -> None:
        self.host.inputs.append(data)
        if data == "finish\r":
            self.channel.write("Final output before exit\r\n")
            self.channel.exit(0)
        else:
            self.channel.write(f"echo:{data}")

    def connection_lost(self, exc: Exception | None) -> None:
        self.host.disconnected.append(True)


class SyntheticServer(asyncssh.SSHServer):
    def __init__(self, host: SyntheticHost):
        self.host = host

    def begin_auth(self, username: str) -> bool:
        return True

    def public_key_auth_supported(self) -> bool:
        return True

    def validate_public_key(self, username: str, key: Any) -> bool:
        return username == "lab-admin" and key == self.host.client_key.convert_to_public()

    def session_requested(self) -> SyntheticSession:
        return SyntheticSession(self.host)


@dataclass
class Lab:
    client: TestClient
    device: dict[str, str]
    token: str
    csrf: str
    config_file: Path
    host: SyntheticHost
    server: Any

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Cookie": f"allsafe_session={self.token}; allsafe_csrf={self.csrf}",
            "X-CSRF-Token": self.csrf,
        }

    @property
    def stream_headers(self) -> dict[str, str]:
        return {**self.headers, "Origin": ORIGIN}

    def request(self, **overrides: Any) -> dict[str, Any]:
        payload = {"device_id": self.device["device_id"], "reason": "Repair stopped lab agent"}
        response = self.client.post(
            f"{ROOT}/terminal-sessions", headers=self.headers, json={**payload, **overrides}
        )
        assert response.status_code == 201, response.text
        return response.json()

    def state(self, session_id: str) -> dict[str, Any]:
        return self.client.get(
            f"{ROOT}/terminal-sessions/{session_id}", headers=self.headers
        ).json()

    def output(self, ws: Any) -> str:
        event = ws.receive_json()
        assert event["type"] == "output", event
        assert len(event["data"].encode("utf-8")) <= 16 * 1024
        ws.send_json({"type": "ack", "sequence": event["sequence"]})
        return event["data"]


@pytest.fixture
def lab(identity_settings, tmp_path: Path):
    config_file = tmp_path / "access.json"
    identity_settings.managed_access_config_file = str(config_file)
    with TestClient(create_app(identity_settings)) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={
                "email": "admin@allsafe.local",
                "password": "Test-Admin-Password-1234",
            },
        )
        assert login.status_code == 200
        token, csrf = login.cookies["allsafe_session"], login.cookies["allsafe_csrf"]
        invitation = client.post(
            "/api/v1/enrollment-tokens",
            headers={"X-CSRF-Token": csrf},
            json={"label": "ssh-lab", "ttl_seconds": 900},
        ).json()
        device = client.post(
            "/api/v1/agent/enroll",
            json={
                "enrollment_token": invitation["enrollment_token"],
                "hostname": "ssh-lab",
                "platform": "windows",
                "agent_version": "0.1.0",
            },
        ).json()
        host = SyntheticHost()

        async def start():
            return await asyncssh.create_server(
                lambda: SyntheticServer(host),
                "127.0.0.1",
                0,
                server_host_keys=[host.host_key],
                line_editor=False,
            )

        server = client.portal.call(start)
        port = server.get_port()
        (tmp_path / "client-key").write_bytes(host.client_key.export_private_key())
        (tmp_path / "client-key").chmod(0o600)
        (tmp_path / "known_hosts").write_bytes(
            f"[127.0.0.1]:{port} ".encode() + host.host_key.export_public_key()
        )
        config_file.write_text(
            json.dumps(
                {
                    "version": 1,
                    "devices": [
                        {
                            "device_id": device["device_id"],
                            "host": "127.0.0.1",
                            "ssh": {
                                "port": port,
                                "username": "lab-admin",
                                "client_key_file": "client-key",
                                "known_hosts_file": "known_hosts",
                            },
                            "rdp": {"port": 3389, "username": "LAB\\admin"},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        try:
            yield Lab(client, device, token, csrf, config_file, host, server)
        finally:

            async def stop():
                server.close()
                await server.wait_closed()

            client.portal.call(stop)


@contextmanager
def connected(lab: Lab, **options: Any):
    terminal = lab.request(**options)
    with lab.client.websocket_connect(
        f"{ROOT}/terminal-sessions/{terminal['id']}/stream", headers=lab.stream_headers
    ) as ws:
        ws.send_json({"type": "hello", "csrf": lab.csrf})
        assert ws.receive_json() == {"type": "ready"}
        yield terminal["id"], ws


def test_real_pinned_key_pty_input_resize_and_final_output(lab: Lab):
    with connected(lab, cols=110, rows=35) as (session_id, ws):
        assert lab.output(ws) == lab.host.banner
        assert lab.host.sizes == [(110, 35)]
        ws.send_json({"type": "resize", "cols": 120, "rows": 40})
        ws.send_json({"type": "input", "data": "whoami\r"})
        assert lab.output(ws) == "echo:whoami\r"
        assert lab.host.sizes[-1] == (120, 40)
        assert lab.state(session_id)["status"] == "active"
        ws.send_json({"type": "input", "data": "finish\r"})
        assert lab.output(ws) == "Final output before exit\r\n"
        assert ws.receive_json()["type"] == "closed"
    assert lab.state(session_id)["status"] == "closed"
    with lab.client.app.state.session_factory() as database:
        events = list(
            database.scalars(
                select(AuditEvent).where(AuditEvent.event_type.like("managed_access.terminal.%"))
            )
        )
        assert [event.event_type.rsplit(".", 1)[-1] for event in events] == [
            "requested",
            "started",
            "closed",
        ]
        assert "whoami" not in repr([event.details for event in events])
        assert "Final output" not in repr([event.details for event in events])


def test_host_key_mismatch_fails_before_shell(lab: Lab):
    other = asyncssh.generate_private_key("ssh-ed25519")
    (lab.config_file.parent / "known_hosts").write_bytes(
        f"[127.0.0.1]:{lab.server.get_port()} ".encode() + other.export_public_key()
    )
    terminal = lab.request()
    with lab.client.websocket_connect(
        f"{ROOT}/terminal-sessions/{terminal['id']}/stream", headers=lab.stream_headers
    ) as ws:
        ws.send_json({"type": "hello", "csrf": lab.csrf})
        assert ws.receive_json() == {"type": "closed", "reason": "connection_failed"}
    assert not lab.host.sessions
    assert lab.state(terminal["id"])["status"] == "closed"


def test_status_is_configuration_not_connectivity_and_offline_device_allowed(lab: Lab):
    response = lab.client.get(f"{ROOT}/devices/{lab.device['device_id']}", headers=lab.headers)
    assert response.json() == {
        "device_id": lab.device["device_id"],
        "terminal": {"configured": True, "account": "lab-admin"},
        "rdp": {"configured": True, "account": "LAB\\admin"},
        "error_code": None,
    }
    assert response.headers["cache-control"] == "no-store"
    assert not lab.host.sessions
    terminal = lab.request()  # No agent heartbeat was sent.
    assert terminal["status"] == "pending"
    assert lab.state(terminal["id"])["expires_at"].endswith("Z")


def test_browser_cannot_override_target_account_or_command(lab: Lab):
    for extra in (
        {"host": "evil.example"},
        {"username": "Administrator"},
        {"command": "cmd"},
        {"cols": True},
        {"rows": "30"},
        {"reason": "\n\n"},
    ):
        response = lab.client.post(
            f"{ROOT}/terminal-sessions",
            headers=lab.headers,
            json={
                "device_id": lab.device["device_id"],
                "reason": "Lab repair",
                **extra,
            },
        )
        assert response.status_code == 422, response.text


def test_auth_csrf_origin_mobile_and_analyst_denied(lab: Lab):
    payload = {"device_id": lab.device["device_id"], "reason": "Lab repair"}
    lab.client.cookies.clear()
    assert lab.client.post(f"{ROOT}/terminal-sessions", json=payload).status_code == 401
    assert (
        lab.client.post(
            f"{ROOT}/terminal-sessions",
            json=payload,
            headers={
                "Cookie": f"allsafe_session={lab.token}",
            },
        ).status_code
        == 403
    )
    assert (
        lab.client.post(
            f"{ROOT}/terminal-sessions",
            json=payload,
            headers={
                **lab.headers,
                "Origin": "https://evil.example",
            },
        ).status_code
        == 403
    )
    mobile = lab.client.post(
        "/api/v1/auth/mobile/login",
        json={
            "email": "admin@allsafe.local",
            "password": "Test-Admin-Password-1234",
        },
    ).json()
    assert (
        lab.client.post(
            f"{ROOT}/terminal-sessions",
            json=payload,
            headers={
                "Authorization": f"Bearer {mobile['access_token']}",
            },
        ).status_code
        == 403
    )
    with lab.client.app.state.session_factory.begin() as database:
        user = database.scalar(select(User).where(User.email == "admin@allsafe.local"))
        user.role = "analyst"
    assert (
        lab.client.get(f"{ROOT}/devices/{lab.device['device_id']}", headers=lab.headers).status_code
        == 403
    )


def test_bootstrap_not_allowed(client, admin_headers):
    assert (
        client.get(
            f"{ROOT}/devices/00000000-0000-0000-0000-000000000001", headers=admin_headers
        ).status_code
        == 403
    )


def test_exact_login_ownership_even_same_admin(lab: Lab):
    terminal = lab.request()
    login = lab.client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@allsafe.local",
            "password": "Test-Admin-Password-1234",
        },
    )
    csrf = login.cookies["allsafe_csrf"]
    assert lab.client.get(f"{ROOT}/terminal-sessions/{terminal['id']}").status_code == 404
    assert (
        lab.client.post(
            f"{ROOT}/terminal-sessions/{terminal['id']}/close", headers={"X-CSRF-Token": csrf}
        ).status_code
        == 404
    )


@pytest.mark.parametrize("change", ["revoke", "rotate", "logout", "role", "expiry", "profile"])
def test_live_session_terminates_on_authorization_or_configuration_change(lab: Lab, change: str):
    with connected(lab) as (session_id, ws):
        lab.output(ws)
        with lab.client.app.state.session_factory.begin() as database:
            device = database.get(Device, lab.device["device_id"])
            terminal = database.get(TerminalSession, session_id)
            if change == "revoke":
                device.revoked_at = utc_now()
            elif change == "rotate":
                device.agent_token_hash = "f" * 64
            elif change == "logout":
                database.get(UserSession, terminal.requester_session_id).revoked_at = utc_now()
            elif change == "role":
                database.get(User, terminal.operator_id).role = "analyst"
            elif change == "expiry":
                terminal.expires_at = utc_now() - timedelta(seconds=1)
            else:
                lab.config_file.write_text('{"version":1,"devices":[]}', encoding="utf-8")
        assert ws.receive_json()["type"] == "closed"
    assert lab.host.disconnected
    assert not lab.client.app.state.terminal_relay.connections


def test_duplicate_connection_does_not_stop_original(lab: Lab):
    with connected(lab) as (session_id, ws):
        lab.output(ws)
        with lab.client.websocket_connect(
            f"{ROOT}/terminal-sessions/{session_id}/stream", headers=lab.stream_headers
        ) as duplicate:
            duplicate.send_json({"type": "hello", "csrf": lab.csrf})
            with pytest.raises(WebSocketDisconnect):
                duplicate.receive_json()
        ws.send_json({"type": "input", "data": "still-connected"})
        assert lab.output(ws) == "echo:still-connected"
        assert len(lab.host.sessions) == 1


@pytest.mark.parametrize(
    "bad",
    [
        '{"type":"input","data":"a","data":"b"}',
        '{"type":"input","data":"a","command":"cmd"}',
        '{"type":"resize","cols":true,"rows":20}',
        '{"type":"ack","sequence":12345}',
        json.dumps({"type": "input", "data": "ü" * 4097}),
        "[1,2]",
    ],
)
def test_invalid_protocol_closes_without_forwarding(lab: Lab, bad: str):
    with connected(lab) as (_, ws):
        lab.output(ws)
        ws.send_text(bad)
        assert ws.receive_json() == {"type": "closed", "reason": "protocol_violation"}
    assert not lab.host.inputs


def test_missing_ack_closes_without_buffering_flood(lab: Lab, monkeypatch):
    monkeypatch.setattr(transport, "ACK_TIMEOUT", 0.1)
    with connected(lab) as (_, ws):
        event = ws.receive_json()
        assert event["type"] == "output"
        # Additional server output must wait for the first browser rendering ACK.
        lab.client.portal.call(lab.host.sessions[0].channel.write, "unacknowledged")
        assert ws.receive_json() == {"type": "closed", "reason": "connection_failed"}


def test_database_failure_closes_transport_and_does_not_log_commands(lab: Lab, monkeypatch, caplog):
    with connected(lab) as (_, ws):
        lab.output(ws)

        def unavailable(*_):
            raise SQLAlchemyError("sensitive SQL details")

        monkeypatch.setattr(lab.client.app.state.terminal_relay, "check", unavailable)
        monkeypatch.setattr(lab.client.app.state.terminal_relay, "finish_sql", unavailable)
        ws.send_json({"type": "input", "data": "secret-command-never-forwarded"})
        assert ws.receive_json() == {"type": "closed", "reason": "state_unavailable"}
    assert not lab.host.inputs
    assert lab.host.disconnected
    assert "secret-command" not in caplog.text and "sensitive SQL" not in caplog.text


def test_pending_expiry_and_restart_reservation_cleanup(lab: Lab):
    terminal = lab.request()
    with lab.client.app.state.session_factory.begin() as database:
        database.get(TerminalSession, terminal["id"]).expires_at = utc_now() - timedelta(seconds=1)
    assert lab.state(terminal["id"])["status"] == "expired"
    next_session = lab.request()
    from allsafe_api.managed_access.service import close_stale_sessions

    close_stale_sessions(lab.client.app)
    assert lab.state(next_session["id"])["closed_reason"] == "server_restart"
    assert lab.request()["status"] == "pending"


def test_simultaneous_reservations_only_one_wins(lab: Lab):
    gate = Barrier(2)

    def request():
        gate.wait()
        return lab.client.post(
            f"{ROOT}/terminal-sessions",
            headers=lab.headers,
            json={
                "device_id": lab.device["device_id"],
                "reason": "Parallel repair",
            },
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: request(), range(2))) == [201, 409]


def test_native_rdp_download_is_safe_csrf_audited_handoff(lab: Lab):
    response = lab.client.post(
        f"{ROOT}/devices/{lab.device['device_id']}/rdp-profile",
        headers=lab.headers,
        json={"reason": "Lab desktop repair"},
    )
    assert response.status_code == 200
    content = response.content.decode("utf-16")
    assert "full address:s:127.0.0.1:3389\r\n" in content
    assert "authentication level:i:1\r\n" in content
    assert "enablecredsspsupport:i:1\r\n" in content
    assert "redirectclipboard:i:0\r\n" in content
    assert "drivestoredirect:s:\r\n" in content
    assert "password" not in content.lower()
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].endswith('.rdp"')
    with lab.client.app.state.session_factory() as database:
        event = database.scalar(
            select(AuditEvent).where(
                AuditEvent.event_type == "managed_access.rdp.profile_downloaded"
            )
        )
        assert event is not None
    assert not lab.host.sessions


@pytest.mark.parametrize("mutation", ["duplicate", "host", "unknown", "missing_key", "empty_hosts"])
def test_invalid_local_configuration_fails_closed_without_leaking_paths(lab: Lab, mutation: str):
    config = json.loads(lab.config_file.read_text())
    if mutation == "duplicate":
        config["devices"].append(config["devices"][0])
    elif mutation == "host":
        config["devices"][0]["host"] = "127.0.0.1\r\npassword 51:b:bad"
    elif mutation == "unknown":
        config["devices"][0]["ssh"]["command"] = "cmd.exe"
    elif mutation == "missing_key":
        config["devices"][0]["ssh"]["client_key_file"] = "no-such-secret-path"
    else:
        (lab.config_file.parent / "known_hosts").write_text("")
    lab.config_file.write_text(json.dumps(config))
    response = lab.client.get(f"{ROOT}/devices/{lab.device['device_id']}", headers=lab.headers)
    assert response.json()["error_code"] == "configuration_unavailable"
    assert str(lab.config_file.parent) not in response.text
    response = lab.client.post(
        f"{ROOT}/terminal-sessions",
        headers=lab.headers,
        json={
            "device_id": lab.device["device_id"],
            "reason": "Lab repair",
        },
    )
    assert response.status_code == 503
    with pytest.raises(ConfigurationError):
        resolve_profile(str(lab.config_file), lab.device["device_id"])


@pytest.mark.parametrize(
    "header_change",
    [
        {"Origin": "https://evil.example"},
        {"Origin": ""},
        {"Authorization": "Bearer ignored"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_websocket_rejects_untrusted_handshake_before_ssh(lab: Lab, header_change: dict):
    terminal = lab.request()
    with pytest.raises(WebSocketDisconnect):
        with lab.client.websocket_connect(
            f"{ROOT}/terminal-sessions/{terminal['id']}/stream",
            headers={**lab.stream_headers, **header_change},
        ):
            pytest.fail("Untrusted websocket was accepted")
    assert not lab.host.sessions


def test_wrong_csrf_cannot_claim_or_open_ssh(lab: Lab):
    terminal = lab.request()
    with lab.client.websocket_connect(
        f"{ROOT}/terminal-sessions/{terminal['id']}/stream",
        headers=lab.stream_headers,
    ) as ws:
        ws.send_json({"type": "hello", "csrf": "x" * 43})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert not lab.host.sessions


def test_total_input_budget_is_enforced_before_forwarding(lab: Lab, monkeypatch):
    monkeypatch.setattr(transport, "MAX_INPUT_BYTES", 4)
    with connected(lab) as (_, ws):
        lab.output(ws)
        ws.send_json({"type": "input", "data": "12345"})
        assert ws.receive_json() == {"type": "closed", "reason": "protocol_violation"}
    assert not lab.host.inputs


def test_explicit_close_prevents_input_and_reconnect(lab: Lab):
    with connected(lab) as (session_id, ws):
        lab.output(ws)
        response = lab.client.post(
            f"{ROOT}/terminal-sessions/{session_id}/close", headers=lab.headers
        )
        assert response.json()["closed_reason"] == "operator_closed"
        ws.send_json({"type": "input", "data": "after-close"})
        assert ws.receive_json()["type"] == "closed"
    assert not lab.host.inputs
    with lab.client.websocket_connect(
        f"{ROOT}/terminal-sessions/{session_id}/stream",
        headers=lab.stream_headers,
    ) as ws:
        ws.send_json({"type": "hello", "csrf": lab.csrf})
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()
    assert len(lab.host.sessions) == 1


def test_native_rdp_requires_csrf_and_rejects_revoked_device(lab: Lab):
    route = f"{ROOT}/devices/{lab.device['device_id']}/rdp-profile"
    assert (
        lab.client.post(
            route,
            headers={"Cookie": f"allsafe_session={lab.token}"},
            json={"reason": "Lab desktop"},
        ).status_code
        == 403
    )
    with lab.client.app.state.session_factory.begin() as database:
        database.get(Device, lab.device["device_id"]).revoked_at = utc_now()
    assert (
        lab.client.post(route, headers=lab.headers, json={"reason": "Lab desktop"}).status_code
        == 409
    )


def test_large_unicode_output_is_bounded_and_acknowledged_in_order(lab: Lab):
    lab.host.banner = "ü😀" * 5000
    with connected(lab) as (_, ws):
        result = ""
        sequence = 0
        while len(result) < len(lab.host.banner):
            event = ws.receive_json()
            assert event["type"] == "output"
            sequence += 1
            assert event["sequence"] == sequence
            assert len(event["data"].encode("utf-8")) <= 16 * 1024
            result += event["data"]
            ws.send_json({"type": "ack", "sequence": sequence})
        assert result == lab.host.banner
