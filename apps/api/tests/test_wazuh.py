"""Explicit device bindings and honest, bounded Wazuh read integration."""

import base64
import copy
import json
import ssl
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from test_identity import USER_PASSWORD, create_user, login
from test_mobile_identity import mobile_login

from allsafe_api.config import Settings
from allsafe_api.main import create_app

BASE = "/api/v1/wazuh"
SERVER = "https://wazuh-server.example:55000"
INDEXER = "https://wazuh-indexer.example:9200"
SERVER_PASSWORD = "test-only-server-password-private"
INDEXER_PASSWORD = "test-only-indexer-password-private"
JWT = "test-only-wazuh-jwt-private"
BOOTSTRAP = "test-only-wazuh-bootstrap-private"
DIAGNOSTIC = "private upstream diagnostic with employee data"


def manager_payload() -> dict[str, Any]:
    return {
        "error": 0,
        "data": {
            "affected_items": [
                {"id": "000", "name": "wazuh-manager", "status": "active"},
                {
                    "id": "001",
                    "name": "workstation-01",
                    "status": "active",
                    "version": "Wazuh v4.14.0",
                    "lastKeepAlive": "2026-10-14T12:00:00Z",
                    "os": {"name": "Microsoft Windows 11", "version": "11"},
                    "ip": "192.0.2.21",
                },
                {"id": "007", "name": "never-connected", "status": "never_connected"},
            ],
            "total_affected_items": 3,
            "total_failed_items": 0,
            "failed_items": [],
        },
    }


def indexer_payload() -> dict[str, Any]:
    return {
        "timed_out": False,
        "_shards": {"total": 1, "successful": 1, "skipped": 0, "failed": 0},
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_index": "wazuh-alerts-4.x-2026.10.14",
                    "_id": "test-alert-1",
                    "_source": {
                        "timestamp": "2026-10-14T12:00:00Z",
                        "agent": {"id": "001", "name": "workstation-01", "ip": "192.0.2.21"},
                        "rule": {
                            "id": "5710",
                            "level": 5,
                            "description": "Test failed authentication event",
                            "groups": ["authentication_failed"],
                        },
                        "full_log": DIAGNOSTIC,
                    },
                }
            ],
        },
    }


@dataclass
class WazuhUpstream:
    manager: dict[str, Any] = field(default_factory=manager_payload)
    indexer: dict[str, Any] = field(default_factory=indexer_payload)
    server_requests: list[httpx.Request] = field(default_factory=list)
    indexer_requests: list[httpx.Request] = field(default_factory=list)
    server_failure: str | None = None
    indexer_failure: str | None = None

    @staticmethod
    def fail(kind: str | None, request: httpx.Request) -> httpx.Response | None:
        if kind == "timeout":
            raise httpx.ReadTimeout(DIAGNOSTIC, request=request)
        if kind == "redirect":
            return httpx.Response(302, headers={"Location": "https://untrusted.example/collect"})
        if kind == "missing_index":
            return httpx.Response(404, json={"error": {"type": "index_not_found_exception"}})
        if kind == "http":
            return httpx.Response(503, text=DIAGNOSTIC)
        if kind == "invalid_json":
            return httpx.Response(200, text=DIAGNOSTIC)
        return None

    def handle_server(self, request: httpx.Request) -> httpx.Response:
        self.server_requests.append(request)
        failed = self.fail(self.server_failure, request)
        if failed is not None:
            return failed
        if request.url.path == "/security/user/authenticate":
            assert request.method == "POST"
            return httpx.Response(200, json={"error": 0, "data": {"token": JWT}})
        assert request.url.path == "/agents" and request.method == "GET"
        payload = copy.deepcopy(self.manager)
        if payload.get("error") in {0, 2} and isinstance(payload.get("data"), dict):
            items = payload["data"].get("affected_items")
            if isinstance(items, list):
                selected = request.url.params.get("agents_list")
                if selected is not None:
                    identifiers = selected.split(",")
                    items = [item for item in items if item["id"] in identifiers]
                    payload["data"]["total_affected_items"] = len(items)
                limit = int(request.url.params.get("limit", "100"))
                offset = int(request.url.params.get("offset", "0"))
                payload["data"]["affected_items"] = items[offset : offset + limit]
        return httpx.Response(200, json=payload)

    def handle_indexer(self, request: httpx.Request) -> httpx.Response:
        self.indexer_requests.append(request)
        failed = self.fail(self.indexer_failure, request)
        if failed is None and request.method == "GET" and request.url.path == "/":
            return httpx.Response(200, json={"version": {"number": "2.19.0"}})
        return failed if failed is not None else httpx.Response(200, json=self.indexer)


@pytest.fixture
def wazuh_upstream() -> WazuhUpstream:
    return WazuhUpstream()


@pytest.fixture
def wazuh_settings(identity_settings: Settings) -> Settings:
    configured = identity_settings.model_dump(
        exclude={
            "bootstrap_admin_token",
            "wazuh_server_url",
            "wazuh_server_username",
            "wazuh_server_password",
            "wazuh_indexer_url",
            "wazuh_indexer_username",
            "wazuh_indexer_password",
        }
    )
    return Settings(
        _env_file=None,
        **configured,
        bootstrap_admin_token=SecretStr(BOOTSTRAP),
        wazuh_server_url=SERVER,
        wazuh_server_username="test-server-user",
        wazuh_server_password=SecretStr(SERVER_PASSWORD),
        wazuh_indexer_url=INDEXER,
        wazuh_indexer_username="test-indexer-user",
        wazuh_indexer_password=SecretStr(INDEXER_PASSWORD),
    )


@pytest.fixture
def wazuh_client(wazuh_settings: Settings, wazuh_upstream: WazuhUpstream) -> Iterator[TestClient]:
    app = create_app(wazuh_settings)
    app.state.wazuh_server_transport = httpx.MockTransport(wazuh_upstream.handle_server)
    app.state.wazuh_indexer_transport = httpx.MockTransport(wazuh_upstream.handle_indexer)
    with TestClient(app) as client:
        yield client


def enroll_identity(
    client: TestClient, headers: dict[str, str], hostname: str = "workstation-01"
) -> dict[str, str]:
    invitation = client.post("/api/v1/enrollment-tokens", headers=headers, json={"label": hostname})
    assert invitation.status_code == 201, invitation.text
    response = client.post(
        "/api/v1/agent/enroll",
        json={
            "enrollment_token": invitation.json()["enrollment_token"],
            "hostname": hostname,
            "platform": "windows",
            "agent_version": "0.1.0",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def enroll(client: TestClient, headers: dict[str, str], hostname: str = "workstation-01") -> str:
    return enroll_identity(client, headers, hostname)["device_id"]


def bind(
    client: TestClient, headers: dict[str, str], device_id: str, agent_id: str
) -> httpx.Response:
    return client.post(
        f"{BASE}/mappings", headers=headers, json={"device_id": device_id, "agent_id": agent_id}
    )


def assert_checked(payload: dict[str, Any]) -> None:
    assert datetime.fromisoformat(payload["checked_at"].replace("Z", "+00:00")).tzinfo is not None


def assert_no_diagnostics(response: httpx.Response) -> None:
    for secret in (SERVER_PASSWORD, INDEXER_PASSWORD, JWT, DIAGNOSTIC, "192.0.2.21"):
        assert secret not in response.text


def test_unconfigured_is_unknown_not_an_empty_verified_result(identity_client: TestClient) -> None:
    headers = mobile_login(identity_client)
    status = identity_client.get(f"{BASE}/status", headers=headers)
    assert status.status_code == 200
    for name in ("server", "indexer"):
        assert status.json()[name]["state"] == "unconfigured"
        assert_checked(status.json()[name])
    for path in ("agents", "alerts"):
        response = identity_client.get(f"{BASE}/{path}", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "unconfigured" and data["items"] is None
        assert data["total"] is None and data["total_relation"] is None
        assert_checked(data)


def test_components_use_distinct_credentials_and_preserve_agent_identifiers(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    headers = mobile_login(wazuh_client)
    response = wazuh_client.get(f"{BASE}/agents", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["state"] == "connected" and data["partial"] is False
    assert data["total"] == 3 and data["total_relation"] == "eq"
    never = next(item for item in data["items"] if item["agent_id"] == "007")
    assert never["status"] == "never_connected"
    assert never["version"] is None and never["last_keepalive"] is None
    assert never["os"] == {"name": None, "version": None, "platform": None, "arch": None}
    assert all(item["device_id"] is None for item in data["items"])
    auth, agents = wazuh_upstream.server_requests
    encoded = base64.b64encode(f"test-server-user:{SERVER_PASSWORD}".encode()).decode()
    assert auth.headers["Authorization"] == f"Basic {encoded}"
    assert auth.url.params.get("raw", "false") == "false" and auth.method == "POST"
    assert agents.headers["Authorization"] == f"Bearer {JWT}"
    assert SERVER_PASSWORD.encode() not in agents.content
    assert_no_diagnostics(response)
    status = wazuh_client.get(f"{BASE}/status", headers=headers)
    assert status.status_code == 200
    assert status.json()["server"]["state"] == status.json()["indexer"]["state"] == "connected"
    for component in status.json().values():
        assert_checked(component)
    wazuh_upstream.server_failure = "timeout"
    independent = wazuh_client.get(f"{BASE}/status", headers=headers).json()
    assert independent["server"]["state"] == "error"
    assert independent["indexer"]["state"] == "connected"


def test_indexer_uses_bounded_native_timestamp_search_and_minimal_projection(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    response = wazuh_client.get(
        f"{BASE}/alerts?limit=20&hours=6", headers=mobile_login(wazuh_client)
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "connected" and response.json()["total"] == 1
    request = wazuh_upstream.indexer_requests[0]
    assert request.method == "POST"
    assert request.url.scheme == "https" and request.url.host == "wazuh-indexer.example"
    assert request.url.port == 9200 and request.url.path == "/wazuh-alerts-*/_search"
    assert dict(request.url.params) == {"allow_no_indices": "false", "ignore_unavailable": "false"}
    encoded = base64.b64encode(f"test-indexer-user:{INDEXER_PASSWORD}".encode()).decode()
    assert request.headers["Authorization"] == f"Basic {encoded}"
    query = json.loads(request.content)
    assert query["size"] == 20 and query["track_total_hits"] is True
    assert "timestamp" in json.dumps(query["query"]) and "now-6h" in json.dumps(query["query"])
    assert "@timestamp" not in json.dumps(query)
    assert set(query["_source"]) == {
        "timestamp",
        "agent.id",
        "agent.name",
        "rule.id",
        "rule.level",
        "rule.description",
        "rule.groups",
    }
    alert = response.json()["items"][0]
    assert alert["agent_id"] == "001" and alert["alert_id"] == "test-alert-1"
    assert alert["level"] == 5 and alert["device_id"] is None
    assert_no_diagnostics(response)


@pytest.mark.parametrize("path", ["agents", "alerts"])
def test_verified_empty_collection_can_report_zero(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream, path: str
) -> None:
    wazuh_upstream.manager["data"]["affected_items"] = []
    wazuh_upstream.manager["data"]["total_affected_items"] = 0
    wazuh_upstream.indexer["hits"] = {"total": {"value": 0, "relation": "eq"}, "hits": []}
    response = wazuh_client.get(f"{BASE}/{path}", headers=mobile_login(wazuh_client))
    assert response.status_code == 200
    assert response.json()["state"] == "connected"
    assert response.json()["items"] == [] and response.json()["total"] == 0
    assert response.json()["partial"] is False


@pytest.mark.parametrize("failure", ["timeout", "redirect", "http", "invalid_json"])
def test_transport_failures_never_report_connected_zero_or_leak_diagnostics(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream, failure: str
) -> None:
    headers = mobile_login(wazuh_client)
    wazuh_upstream.server_failure = failure
    wazuh_upstream.indexer_failure = failure
    for path in ("agents", "alerts"):
        response = wazuh_client.get(f"{BASE}/{path}", headers=headers)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["state"] == "error" and data["items"] is None and data["total"] is None
        assert data["error_code"] is not None
        assert_no_diagnostics(response)
    assert all(
        request.url.host == "wazuh-server.example" for request in wazuh_upstream.server_requests
    )
    assert all(
        request.url.host == "wazuh-indexer.example" for request in wazuh_upstream.indexer_requests
    )


def test_nonzero_manager_error_is_not_success(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    wazuh_upstream.manager["error"] = 1000
    wazuh_upstream.manager["message"] = DIAGNOSTIC
    response = wazuh_client.get(f"{BASE}/agents", headers=mobile_login(wazuh_client))
    assert response.json()["state"] == "error" and response.json()["total"] is None
    assert_no_diagnostics(response)


def test_manager_partial_results_retain_valid_items_without_claiming_exact_count(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    wazuh_upstream.manager["error"] = 2
    wazuh_upstream.manager["data"]["total_failed_items"] = 1
    wazuh_upstream.manager["data"]["failed_items"] = [
        {"error": {"code": 1, "message": DIAGNOSTIC}, "id": ["009"]}
    ]
    response = wazuh_client.get(f"{BASE}/agents", headers=mobile_login(wazuh_client))
    data = response.json()
    assert data["state"] == "partial" and data["partial"] is True and data["total"] is None
    assert any(item["agent_id"] == "001" for item in data["items"])
    assert_no_diagnostics(response)


@pytest.mark.parametrize("failure", ["timeout", "shards", "lower_bound"])
def test_indexer_partial_search_does_not_claim_exact_total(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream, failure: str
) -> None:
    if failure == "timeout":
        wazuh_upstream.indexer["timed_out"] = True
    elif failure == "shards":
        wazuh_upstream.indexer["_shards"] = {"total": 2, "successful": 1, "skipped": 0, "failed": 1}
    else:
        wazuh_upstream.indexer["hits"]["total"] = {"value": 10000, "relation": "gte"}
    response = wazuh_client.get(f"{BASE}/alerts", headers=mobile_login(wazuh_client))
    data = response.json()
    assert data["state"] == "partial" and data["partial"] is True and data["total"] is None
    assert data["items"][0]["alert_id"] == "test-alert-1"
    if failure == "lower_bound":
        assert data["total_relation"] == "gte"


@pytest.mark.parametrize("component", ["manager", "indexer"])
def test_invalid_response_shape_is_not_a_verified_empty_result(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream, component: str
) -> None:
    if component == "manager":
        wazuh_upstream.manager = {"error": 0, "data": {"affected_items": "invalid"}}
    else:
        wazuh_upstream.indexer = {
            "hits": {"total": {"value": 0, "relation": "eq"}, "hits": "invalid"}
        }
    path = "agents" if component == "manager" else "alerts"
    data = wazuh_client.get(f"{BASE}/{path}", headers=mobile_login(wazuh_client)).json()
    assert data["state"] == "error" and data["items"] is None and data["total"] is None


def test_missing_alert_index_is_distinct_from_zero_alerts(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    wazuh_upstream.indexer_failure = "missing_index"
    response = wazuh_client.get(f"{BASE}/alerts", headers=mobile_login(wazuh_client))
    assert response.json()["state"] == "error" and response.json()["items"] is None
    assert (
        response.json()["total"] is None and response.json()["error_code"] == "alerts_index_missing"
    )


@pytest.mark.parametrize("component", ["manager", "indexer"])
def test_duplicate_upstream_identities_are_not_usable_evidence(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream, component: str
) -> None:
    if component == "manager":
        items = wazuh_upstream.manager["data"]["affected_items"]
        items.append(copy.deepcopy(items[1]))
        wazuh_upstream.manager["data"]["total_affected_items"] = len(items)
        path = "agents"
    else:
        items = wazuh_upstream.indexer["hits"]["hits"]
        items.append(copy.deepcopy(items[0]))
        wazuh_upstream.indexer["hits"]["total"]["value"] = len(items)
        path = "alerts"
    data = wazuh_client.get(f"{BASE}/{path}", headers=mobile_login(wazuh_client)).json()
    assert data["state"] == "error" and data["error_code"] == "invalid_upstream_response"
    assert data["items"] is None and data["total"] is None


def test_identical_alert_ids_in_different_indices_remain_distinct(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    repeated = copy.deepcopy(wazuh_upstream.indexer["hits"]["hits"][0])
    repeated["_index"] = "wazuh-alerts-4.x-2026.10.15"
    wazuh_upstream.indexer["hits"]["hits"].append(repeated)
    wazuh_upstream.indexer["hits"]["total"]["value"] = 2
    data = wazuh_client.get(f"{BASE}/alerts", headers=mobile_login(wazuh_client)).json()
    assert data["state"] == "connected" and data["total"] == 2
    assert len(data["items"]) == 2


@pytest.mark.parametrize("returned_items", [0, 1])
def test_complete_alert_search_cannot_report_missing_hits_as_a_verified_result(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream, returned_items: int
) -> None:
    wazuh_upstream.indexer["hits"]["total"]["value"] = 3
    wazuh_upstream.indexer["hits"]["hits"] = wazuh_upstream.indexer["hits"]["hits"][:returned_items]
    data = wazuh_client.get(f"{BASE}/alerts", headers=mobile_login(wazuh_client)).json()
    assert data["state"] == "error" and data["error_code"] == "invalid_upstream_response"
    assert data["items"] is None and data["total"] is None


def test_partial_alert_search_can_retain_empty_items_without_claiming_zero_total(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    wazuh_upstream.indexer["timed_out"] = True
    wazuh_upstream.indexer["hits"]["hits"] = []
    data = wazuh_client.get(f"{BASE}/alerts", headers=mobile_login(wazuh_client)).json()
    assert data["state"] == "partial" and data["items"] == [] and data["total"] is None


def test_only_human_admin_and_analyst_can_read_and_only_admin_can_manage_mappings(
    wazuh_client: TestClient,
) -> None:
    administrator = login(wazuh_client)
    device = enroll_identity(wazuh_client, administrator.headers())
    employee = create_user(wazuh_client, administrator)
    analyst = create_user(
        wazuh_client, administrator, role="analyst", email="analyst@allsafe.local"
    )
    employee_headers = mobile_login(wazuh_client, employee["email"], USER_PASSWORD)
    analyst_headers = mobile_login(wazuh_client, analyst["email"], USER_PASSWORD)
    for path in ("status", "agents", "alerts"):
        assert wazuh_client.get(f"{BASE}/{path}", headers=analyst_headers).status_code == 200
        assert wazuh_client.get(f"{BASE}/{path}", headers=employee_headers).status_code == 403
        for nonhuman in (BOOTSTRAP, device["agent_token"]):
            assert wazuh_client.get(
                f"{BASE}/{path}", headers={"Authorization": f"Bearer {nonhuman}"}
            ).status_code in {401, 403}
    for headers in (employee_headers, analyst_headers):
        assert wazuh_client.get(f"{BASE}/mappings", headers=headers).status_code == 403
        assert bind(wazuh_client, headers, str(uuid4()), "001").status_code == 403
        assert wazuh_client.delete(f"{BASE}/mappings/{uuid4()}", headers=headers).status_code == 403
    wazuh_client.cookies.clear()
    assert wazuh_client.get(f"{BASE}/status").status_code == 401


def test_explicit_mapping_is_unique_verified_removable_and_never_guessed_by_name(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    headers = mobile_login(wazuh_client)
    device = enroll(wazuh_client, headers)
    other = enroll(wazuh_client, headers, "other-workstation")
    initial = wazuh_client.get(f"{BASE}/agents", headers=headers).json()["items"]
    assert next(item for item in initial if item["agent_id"] == "001")["device_id"] is None
    created = bind(wazuh_client, headers, device, "001")
    assert created.status_code == 201, created.text
    mapping = created.json()
    assert mapping["agent_id"] == "001" and mapping["device_id"] == device
    assert mapping["server_scope"] and SERVER not in mapping["server_scope"]
    verified_request = wazuh_upstream.server_requests[-1]
    assert verified_request.url.params["agents_list"] == "001"
    assert verified_request.url.params["limit"] == "1"
    repeated = bind(wazuh_client, headers, device, "001")
    assert repeated.status_code == 201 and repeated.json()["id"] == mapping["id"]
    assert bind(wazuh_client, headers, other, "001").status_code == 409
    assert bind(wazuh_client, headers, device, "007").status_code == 409
    assert bind(wazuh_client, headers, other, "000").status_code in {409, 422}
    assert bind(wazuh_client, headers, str(uuid4()), "007").status_code == 404
    assert bind(wazuh_client, headers, other, "999").status_code == 404
    assert wazuh_client.get(f"{BASE}/alerts?device_id={other}", headers=headers).status_code == 404
    wazuh_upstream.server_failure = "timeout"
    assert bind(wazuh_client, headers, other, "007").status_code == 503
    wazuh_upstream.server_failure = None
    alerts = wazuh_client.get(f"{BASE}/alerts", headers=headers).json()["items"]
    assert alerts[0]["device_id"] == device
    filtered = wazuh_client.get(f"{BASE}/alerts?device_id={device}", headers=headers)
    assert filtered.status_code == 200
    filter_query = json.loads(wazuh_upstream.indexer_requests[-1].content)["query"]["bool"][
        "filter"
    ]
    assert {"term": {"agent.id": "001"}} in filter_query
    deleted = wazuh_client.delete(f"{BASE}/mappings/{mapping['id']}", headers=headers)
    assert deleted.status_code == 204
    assert (
        wazuh_client.get(f"{BASE}/alerts", headers=headers).json()["items"][0]["device_id"] is None
    )
    events = wazuh_client.get("/api/v1/audit-events", headers=headers).json()
    for event_type in ("wazuh.mapping.created", "wazuh.mapping.removed"):
        recorded = [event for event in events if event["event_type"] == event_type]
        assert len(recorded) == 1
        assert recorded[0]["target_id"] == device
        assert recorded[0]["details"] == {"mapping_id": mapping["id"], "agent_id": "001"}


def test_mapping_from_another_server_origin_does_not_bind_reused_agent_id(
    wazuh_client: TestClient, wazuh_settings: Settings, wazuh_upstream: WazuhUpstream
) -> None:
    headers = mobile_login(wazuh_client)
    device = enroll(wazuh_client, headers)
    assert bind(wazuh_client, headers, device, "001").status_code == 201
    changed = wazuh_settings.model_copy(
        update={"wazuh_server_url": "https://replacement-server.example:55000"}
    )
    app = create_app(changed)
    app.state.wazuh_server_transport = httpx.MockTransport(wazuh_upstream.handle_server)
    app.state.wazuh_indexer_transport = httpx.MockTransport(wazuh_upstream.handle_indexer)
    with TestClient(app) as restarted:
        response = restarted.get(f"{BASE}/agents", headers=mobile_login(restarted))
        assert all(item["device_id"] is None for item in response.json()["items"])
        assert (
            restarted.get(f"{BASE}/alerts", headers=mobile_login(restarted)).json()["items"][0][
                "device_id"
            ]
            is None
        )


def test_query_bounds_and_unsafe_connection_configuration_are_rejected(
    wazuh_client: TestClient, wazuh_upstream: WazuhUpstream
) -> None:
    headers = mobile_login(wazuh_client)
    for query in (
        "agents?limit=0",
        "agents?limit=501",
        "agents?offset=-1",
        "agents?offset=10001",
        "alerts?limit=501",
        "alerts?hours=0",
        "alerts?hours=169",
        "alerts?device_id=not-a-uuid",
    ):
        assert wazuh_client.get(f"{BASE}/{query}", headers=headers).status_code == 422
    assert not wazuh_upstream.server_requests and not wazuh_upstream.indexer_requests
    for server in (
        "http://wazuh.example",
        "https://user:pass@wazuh.example",
        "https://wazuh.example/path",
        "https://wazuh.example?token=private",
    ):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, wazuh_server_url=server)


def test_outgoing_clients_verify_tls_and_disable_redirects_and_environment_proxy(
    wazuh_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from allsafe_api.wazuh import client as connector_module

    captured: list[dict[str, Any]] = []
    real_client = httpx.Client

    def capture(*args: Any, **kwargs: Any) -> httpx.Client:
        captured.append(kwargs)
        return real_client(*args, **kwargs)

    headers = mobile_login(wazuh_client)
    monkeypatch.setattr(connector_module.httpx, "Client", capture)
    assert wazuh_client.get(f"{BASE}/agents", headers=headers).status_code == 200
    assert wazuh_client.get(f"{BASE}/alerts", headers=headers).status_code == 200
    assert len(captured) >= 2
    for options in captured:
        context = options["verify"]
        assert isinstance(context, ssl.SSLContext)
        assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname is True
        assert options["follow_redirects"] is False and options["trust_env"] is False
    client_count = len(captured)
    wazuh_client.app.state.settings.wazuh_server_ca_file = str(tmp_path / "missing-private-ca.pem")
    rejected = wazuh_client.get(f"{BASE}/agents", headers=headers)
    assert rejected.json()["error_code"] == "invalid_ca_file"
    assert rejected.json()["state"] == "error" and rejected.json()["total"] is None
    assert len(captured) == client_count
    assert "missing-private-ca.pem" not in rejected.text
