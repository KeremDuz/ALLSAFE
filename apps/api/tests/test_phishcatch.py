"""Human scan ownership, bounded integration and independent training approval."""

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from test_identity import USER_PASSWORD, create_user, login
from test_mobile_identity import mobile_login

from allsafe_api.config import Settings
from allsafe_api.main import create_app

BASE = "/api/v1/phishcatch"
INTEGRATION_KEY = "fake-phishcatch-integration-key-aaaaaaaaaaaaaaaa"
BOOTSTRAP_KEY = "fake-phishcatch-bootstrap-key"
URL = "https://example.org/login?employee=private-query-value#private-fragment-value"


def upstream_result() -> dict[str, Any]:
    return {
        "analysis": {
            "contract_version": "2",
            "observation_id": 1,
            "scan_status": "complete",
            "final_verdict": "malicious",
            "confidence": 0.9,
            "risk_score": 0.9,
            "malicious_probability": 0.9,
            "clean_probability": 0.1,
            "decided_by": "MlScanner",
            "stages": [
                {
                    "scanner": "MlScanner",
                    "verdict": "malicious",
                    "status": "completed",
                    "confidence": 0.9,
                }
            ],
        },
        "features": {"url.UrlLength": 42, "url.NoHttps": 0},
        "feature_version": "phishcatch-v1",
    }


@dataclass
class Upstream:
    result: dict[str, Any] = field(default_factory=upstream_result)
    requests: list[httpx.Request] = field(default_factory=list)
    failure: str | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"contract_version": "2", "status": "ok"})
        self.requests.append(request)
        if self.failure == "timeout":
            raise httpx.ReadTimeout("private upstream diagnostic value", request=request)
        if self.failure == "http":
            return httpx.Response(503, text="private upstream diagnostic value")
        if self.failure == "json":
            return httpx.Response(200, text="private upstream diagnostic value")
        return httpx.Response(200, json=self.result)


@pytest.fixture
def upstream() -> Upstream:
    return Upstream()


@pytest.fixture
def integrated_client(identity_settings: Settings, upstream: Upstream) -> Iterator[TestClient]:
    configured = identity_settings.model_dump(
        exclude={"phishcatch_url", "phishcatch_integration_key", "bootstrap_admin_token"}
    )
    settings = Settings(
        _env_file=None,
        **configured,
        phishcatch_url="https://phishcatch.example",
        phishcatch_integration_key=SecretStr(INTEGRATION_KEY),
        bootstrap_admin_token=SecretStr(BOOTSTRAP_KEY),
    )
    app = create_app(settings)
    app.state.phishcatch_transport = httpx.MockTransport(upstream.handle)
    with TestClient(app) as client:
        yield client


def submit(
    client: TestClient,
    headers: dict[str, str],
    *,
    request_id: str | None = None,
    url: str = URL,
    source: str = "qr",
) -> httpx.Response:
    return client.post(
        f"{BASE}/scans",
        headers=headers,
        json={"url": url, "source": source, "client_request_id": request_id or str(uuid4())},
    )


def scan_id(client: TestClient, headers: dict[str, str]) -> str:
    response = submit(client, headers)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def review(
    client: TestClient, headers: dict[str, str], target: str, label: str, notes: str = ""
) -> None:
    response = client.post(
        f"{BASE}/scans/{target}/reviews", headers=headers, json={"label": label, "notes": notes}
    )
    assert response.status_code in {200, 201}, response.text


def test_real_contract_uses_fixed_connector_and_sanitizes_scan_response(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    actor = login(integrated_client)
    response = submit(integrated_client, actor.headers())
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["user_id"] == actor.user["id"] and record["source"] == "qr"
    assert record["url"] == "https://example.org/login"
    assert (
        record["scan_status"] == "complete" and record["analysis"]["final_verdict"] == "malicious"
    )
    assert record["verified_label"] is None and record["training_approved"] is False
    assert record["feature_count"] == 2
    for secret in ("private-query-value", "private-fragment-value", INTEGRATION_KEY):
        assert secret not in response.text
    request = upstream.requests[0]
    assert (
        request.method == "POST"
        and str(request.url) == "https://phishcatch.example/api/v1/integrations/allsafe/analyze"
    )
    assert request.headers["X-Integration-Key"] == INTEGRATION_KEY
    assert "authorization" not in request.headers
    assert json.loads(request.content) == {"url": URL}


def test_idempotency_is_scoped_to_exact_user_payload(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    actor = login(integrated_client)
    request_id = str(uuid4())
    first = submit(integrated_client, actor.headers(), request_id=request_id)
    repeated = submit(integrated_client, actor.headers(), request_id=request_id)
    assert first.status_code == repeated.status_code == 201
    assert first.json()["id"] == repeated.json()["id"] and len(upstream.requests) == 1
    for changes in (
        {"source": "url"},
        {"url": URL.replace("private-query-value", "different-private-value")},
    ):
        assert (
            submit(integrated_client, actor.headers(), request_id=request_id, **changes).status_code
            == 409
        )
    assert len(upstream.requests) == 1


def test_employee_records_are_private_but_analyst_can_read_organization(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    administrator = login(integrated_client)
    first = create_user(integrated_client, administrator, email="first@allsafe.local")
    second = create_user(integrated_client, administrator, email="second@allsafe.local")
    analyst = create_user(
        integrated_client, administrator, role="analyst", email="analyst@allsafe.local"
    )
    first_headers = mobile_login(integrated_client, first["email"], USER_PASSWORD)
    second_headers = mobile_login(integrated_client, second["email"], USER_PASSWORD)
    shared_request_id = str(uuid4())
    own = submit(integrated_client, first_headers, request_id=shared_request_id).json()["id"]
    other = submit(
        integrated_client,
        second_headers,
        request_id=shared_request_id,
        url="https://other.example/",
    ).json()["id"]
    assert own != other and len(upstream.requests) == 2
    records = integrated_client.get(f"{BASE}/scans", headers=first_headers)
    assert [record["id"] for record in records.json()] == [own]
    assert integrated_client.get(f"{BASE}/scans/{other}", headers=first_headers).status_code == 404
    assert (
        integrated_client.post(
            f"{BASE}/scans/{other}/reviews", headers=first_headers, json={"label": "clean"}
        ).status_code
        == 403
    )
    analyst_headers = mobile_login(integrated_client, analyst["email"], USER_PASSWORD)
    assert {
        record["id"]
        for record in integrated_client.get(f"{BASE}/scans", headers=analyst_headers).json()
    } == {own, other}
    assert (
        integrated_client.get(f"{BASE}/scans/{other}", headers=analyst_headers).status_code == 200
    )


def test_device_and_legacy_bootstrap_cannot_impersonate_scan_users(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    actor = login(integrated_client)
    invitation = integrated_client.post(
        "/api/v1/enrollment-tokens", headers=actor.headers(), json={"label": "Scan token isolation"}
    )
    device = integrated_client.post(
        "/api/v1/agent/enroll",
        json={
            "enrollment_token": invitation.json()["enrollment_token"],
            "hostname": "test-device",
            "platform": "windows",
            "agent_version": "0.1.0",
        },
    ).json()
    integrated_client.cookies.clear()
    bootstrap = {"Authorization": f"Bearer {BOOTSTRAP_KEY}"}
    assert integrated_client.get("/api/v1/devices", headers=bootstrap).status_code == 200
    for headers in (bootstrap, {"Authorization": f"Bearer {device['agent_token']}"}, {}):
        assert submit(integrated_client, headers).status_code in {401, 403}
        assert integrated_client.get(f"{BASE}/scans", headers=headers).status_code in {401, 403}
    assert not upstream.requests


@pytest.mark.parametrize(
    "spoofed",
    [
        {"user_id": str(uuid4())},
        {"verified_label": "clean"},
        {"training_approved": True},
        {"analysis": {"final_verdict": "clean"}},
    ],
)
def test_clients_cannot_submit_identity_labels_or_prediction(
    integrated_client: TestClient, upstream: Upstream, spoofed: dict[str, Any]
) -> None:
    actor = login(integrated_client)
    response = integrated_client.post(
        f"{BASE}/scans",
        headers=actor.headers(),
        json={"url": URL, "source": "url", "client_request_id": str(uuid4()), **spoofed},
    )
    assert response.status_code == 422 and not upstream.requests


def test_browser_scan_mutation_requires_csrf_while_mobile_bearer_works(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    actor = login(integrated_client)
    assert submit(integrated_client, actor.headers(csrf=False)).status_code == 403
    assert (
        submit(
            integrated_client, actor.headers() | {"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert not upstream.requests
    assert submit(integrated_client, mobile_login(integrated_client)).status_code == 201


@pytest.mark.parametrize("failure", ["timeout", "http", "json", "version", "probability"])
def test_upstream_failure_or_invalid_contract_persists_failed_scan(
    integrated_client: TestClient, upstream: Upstream, failure: str
) -> None:
    actor = login(integrated_client)
    if failure == "version":
        upstream.result["analysis"]["contract_version"] = "1"
    elif failure == "probability":
        upstream.result["analysis"]["clean_probability"] = 2
    else:
        upstream.failure = failure
    response = submit(integrated_client, actor.headers())
    assert response.status_code == 201, response.text
    record = response.json()
    assert record["scan_status"] == "failed" and record["analysis"] is None
    assert record["error_code"] and record["feature_count"] == 0
    assert record["verified_label"] is None and record["training_approved"] is False
    assert (
        "private upstream diagnostic" not in response.text
        and "private-query-value" not in response.text
    )
    fetched = integrated_client.get(f"{BASE}/scans/{record['id']}", headers=actor.headers())
    assert fetched.status_code == 200 and fetched.json()["scan_status"] == "failed"


def test_incomplete_clean_analysis_is_preserved_as_unknown(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    actor = login(integrated_client)
    upstream.result["analysis"].update(
        scan_status="partial",
        final_verdict="clean",
        clean_probability=0.9,
        malicious_probability=0.1,
    )
    upstream.result["analysis"]["stages"] = [
        {"scanner": "ThreatIntelScanner", "verdict": "unknown", "status": "completed"},
        {"scanner": "MlScanner", "verdict": "clean", "status": "unavailable"},
    ]
    response = submit(integrated_client, actor.headers())
    assert response.status_code == 201
    record = response.json()
    assert record["scan_status"] == "partial" and record["analysis"]["final_verdict"] == "unknown"
    assert (
        record["analysis"]["clean_probability"] is None
        and record["analysis"]["malicious_probability"] is None
    )
    assert record["verified_label"] is None and record["training_approved"] is False


@pytest.mark.parametrize(
    ("stages", "expected_status", "expected_verdict"),
    [
        (
            [
                {"scanner": "ThreatIntelScanner", "verdict": "clean", "status": "completed"},
                {"scanner": "MlScanner", "verdict": "unknown", "status": "unavailable"},
            ],
            "partial",
            "unknown",
        ),
        ([{"scanner": "MlScanner", "verdict": "unknown", "status": "failed"}], "failed", "unknown"),
        ([], "failed", "unknown"),
        (
            [
                {"scanner": "MlScanner", "verdict": "clean", "status": "completed"},
                {"scanner": "HtmlScanner", "verdict": "unknown", "status": "skipped"},
            ],
            "partial",
            "unknown",
        ),
        (
            [
                {"scanner": "MlScanner", "verdict": "clean", "status": "completed"},
                {"scanner": "HtmlScanner", "verdict": "clean", "status": "completed"},
            ],
            "complete",
            "clean",
        ),
    ],
)
def test_stage_evidence_overrides_contradictory_complete_claim(
    integrated_client: TestClient,
    upstream: Upstream,
    stages: list[dict[str, str]],
    expected_status: str,
    expected_verdict: str,
) -> None:
    actor = login(integrated_client)
    upstream.result["analysis"].update(
        final_verdict="clean", clean_probability=0.9, malicious_probability=0.1, stages=stages
    )
    response = submit(integrated_client, actor.headers())
    assert response.status_code == 201
    record = response.json()
    assert (
        record["scan_status"] == expected_status
        and record["analysis"]["final_verdict"] == expected_verdict
    )
    if expected_verdict == "unknown":
        assert record["analysis"]["confidence"] is None
        assert (
            record["analysis"]["clean_probability"] is None
            and record["analysis"]["malicious_probability"] is None
        )


def test_prediction_review_and_approval_remain_three_operations(
    integrated_client: TestClient,
) -> None:
    actor = login(integrated_client)
    target = scan_id(integrated_client, actor.headers())
    assert (
        integrated_client.post(
            f"{BASE}/scans/{target}/training-approval", headers=actor.headers()
        ).status_code
        == 409
    )
    review(integrated_client, actor.headers(), target, "clean", "Independent verified review")
    record = integrated_client.get(f"{BASE}/scans/{target}", headers=actor.headers()).json()
    assert (
        record["analysis"]["final_verdict"] == "malicious" and record["verified_label"] == "clean"
    )
    assert record["review_id"] and record["training_approved"] is False
    assert (
        integrated_client.get(f"{BASE}/training-export", headers=actor.headers()).json()["samples"]
        == []
    )
    approved = integrated_client.post(
        f"{BASE}/scans/{target}/training-approval", headers=actor.headers()
    )
    assert approved.status_code in {200, 204}, approved.text
    assert (
        integrated_client.get(f"{BASE}/scans/{target}", headers=actor.headers()).json()[
            "training_approved"
        ]
        is True
    )
    review(integrated_client, actor.headers(), target, "malicious", "Updated evidence")
    assert (
        integrated_client.get(f"{BASE}/scans/{target}", headers=actor.headers()).json()[
            "training_approved"
        ]
        is False
    )
    assert (
        integrated_client.get(f"{BASE}/training-export", headers=actor.headers()).json()["samples"]
        == []
    )


def test_uncertain_or_featureless_review_cannot_be_approved(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    actor = login(integrated_client)
    target = scan_id(integrated_client, actor.headers())
    review(integrated_client, actor.headers(), target, "uncertain")
    assert (
        integrated_client.post(
            f"{BASE}/scans/{target}/training-approval", headers=actor.headers()
        ).status_code
        == 409
    )
    upstream.result["features"] = {}
    featureless = scan_id(integrated_client, actor.headers())
    review(integrated_client, actor.headers(), featureless, "clean")
    assert (
        integrated_client.post(
            f"{BASE}/scans/{featureless}/training-approval", headers=actor.headers()
        ).status_code
        == 409
    )


def test_reviewer_role_does_not_grant_training_approval(integrated_client: TestClient) -> None:
    administrator = login(integrated_client)
    analyst = create_user(
        integrated_client, administrator, role="analyst", training_permission=False
    )
    target = scan_id(integrated_client, administrator.headers())
    headers = mobile_login(integrated_client, analyst["email"], USER_PASSWORD)
    review(integrated_client, headers, target, "clean")
    assert (
        integrated_client.post(
            f"{BASE}/scans/{target}/training-approval", headers=headers
        ).status_code
        == 403
    )
    assert (
        integrated_client.delete(
            f"{BASE}/scans/{target}/training-approval", headers=headers
        ).status_code
        == 403
    )
    assert integrated_client.get(f"{BASE}/training-export", headers=headers).status_code == 403


def test_training_export_contains_only_approved_features_and_label(
    integrated_client: TestClient, upstream: Upstream
) -> None:
    actor = login(integrated_client)
    upstream.result["features"]["employee.email"] = 99
    target = scan_id(integrated_client, actor.headers())
    review(
        integrated_client,
        actor.headers(),
        target,
        "clean",
        "private-review-notes employee@allsafe.local",
    )
    assert integrated_client.post(
        f"{BASE}/scans/{target}/training-approval", headers=actor.headers()
    ).status_code in {200, 204}
    response = integrated_client.get(f"{BASE}/training-export", headers=actor.headers())
    assert response.status_code == 200
    exported = response.json()
    assert (
        set(exported) == {"feature_version", "samples"}
        and exported["feature_version"] == "phishcatch-v1"
    )
    assert exported["samples"] == [
        {"label": 0, "features": {"url.UrlLength": 42, "url.NoHttps": 0}}
    ]
    for forbidden in (
        target,
        actor.user["id"],
        "example.org",
        "private-query-value",
        "private-review-notes",
        "employee.email",
        "employee@allsafe.local",
    ):
        assert forbidden not in response.text
    assert integrated_client.delete(
        f"{BASE}/scans/{target}/training-approval", headers=actor.headers()
    ).status_code in {200, 204}
    assert (
        integrated_client.get(f"{BASE}/training-export", headers=actor.headers()).json()["samples"]
        == []
    )
