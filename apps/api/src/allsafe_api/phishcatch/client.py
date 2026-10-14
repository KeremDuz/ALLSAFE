"""Bounded server-to-server analysis, with no employee credentials upstream."""

import json
from time import monotonic
from typing import Any

import httpx
from pydantic import ValidationError

from allsafe_api.config import Settings
from allsafe_api.phishcatch.schemas import IntegrationResponse


class ConnectorFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class PhishCatchClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    @property
    def configured(self) -> bool:
        return bool(self.settings.phishcatch_url and self.settings.phishcatch_integration_key)

    def _request(
        self, method: str, path: str, body: dict[str, str] | None, timeout: int
    ) -> dict[str, Any]:
        if not self.configured:
            raise ConnectorFailure("connector_unconfigured")
        deadline = monotonic() + timeout
        key = self.settings.phishcatch_integration_key.get_secret_value()
        try:
            with (
                httpx.Client(
                    base_url=self.settings.phishcatch_url.rstrip("/"),
                    headers={"X-Integration-Key": key},
                    timeout=httpx.Timeout(timeout, connect=min(timeout, 5)),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self.transport,
                ) as client,
                client.stream(method, path, json=body) as response,
            ):
                if response.status_code != 200:
                    raise ConnectorFailure(
                        "upstream_rejected"
                        if response.status_code < 500
                        else "upstream_unavailable"
                    )
                chunks = bytearray()
                for chunk in response.iter_bytes():
                    if monotonic() > deadline:
                        raise ConnectorFailure("upstream_timeout")
                    chunks.extend(chunk)
                    if len(chunks) > 512 * 1024:
                        raise ConnectorFailure("invalid_upstream_response")
                data = json.loads(chunks)
                if not isinstance(data, dict):
                    raise ConnectorFailure("invalid_upstream_response")
                return data
        except httpx.TimeoutException as problem:
            raise ConnectorFailure("upstream_timeout") from problem
        except (httpx.HTTPError, OSError) as problem:
            raise ConnectorFailure("upstream_unavailable") from problem
        except (ValueError, UnicodeError) as problem:
            raise ConnectorFailure("invalid_upstream_response") from problem

    def analyze(self, url: str) -> IntegrationResponse:
        data = self._request(
            "POST",
            "/api/v1/integrations/allsafe/analyze",
            {"url": url},
            self.settings.phishcatch_timeout_seconds,
        )
        try:
            return IntegrationResponse.model_validate(data)
        except ValidationError as problem:
            raise ConnectorFailure("invalid_upstream_response") from problem

    def status(self) -> dict[str, Any]:
        if not self.configured:
            return {
                "configured": False,
                "reachable": False,
                "url_model_available": None,
                "html_model_available": None,
                "error_code": "connector_unconfigured",
            }
        try:
            report = self._request("GET", "/api/v1/integrations/allsafe/health", None, 5)
            if report.get("contract_version") != "2" or report.get("status") != "ok":
                raise ConnectorFailure("invalid_upstream_response")
            return {
                "configured": True,
                "reachable": True,
                "url_model_available": report.get("url_model_available") is True,
                "html_model_available": report.get("html_model_available") is True,
                "error_code": None,
            }
        except ConnectorFailure as problem:
            return {
                "configured": True,
                "reachable": False,
                "url_model_available": None,
                "html_model_available": None,
                "error_code": problem.code,
            }
