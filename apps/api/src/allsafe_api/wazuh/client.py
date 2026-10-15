"""Separate, verified Wazuh server and Indexer connections; no remote commands."""

import json
import re
import ssl
from datetime import UTC, datetime
from time import monotonic
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from allsafe_api.config import Settings
from allsafe_api.wazuh.schemas import (
    IndexerInfo,
    IndexerSearchEnvelope,
    ServerAgentsEnvelope,
    ServerTokenEnvelope,
)

Component = Literal["server", "indexer"]
MAXIMUM_RESPONSE_BYTES = 512 * 1024
AGENT_SELECT = "id,name,status,version,lastKeepAlive,os.name,os.version,os.platform,os.arch"
ALERT_FIELDS = [
    "timestamp",
    "rule.id",
    "rule.level",
    "rule.description",
    "rule.groups",
    "agent.id",
    "agent.name",
]


class WazuhFailure(Exception):
    """Only a public error code leaves the connection boundary."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def utc_string(value: datetime | None) -> str | None:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z") if value else None


def envelope(
    state: str,
    *,
    items: list[dict[str, Any]] | None = None,
    total: int | None = None,
    relation: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "state": state,
        "items": items,
        "total": total,
        "total_relation": relation,
        "partial": state == "partial",
        "checked_at": utc_string(datetime.now(UTC)),
        "error_code": error,
    }


class WazuhConnector:
    def __init__(
        self,
        settings: Settings,
        server_transport: httpx.BaseTransport | None = None,
        indexer_transport: httpx.BaseTransport | None = None,
    ):
        self.settings = settings
        self.server_transport = server_transport
        self.indexer_transport = indexer_transport

    def _credentials(self, component: Component) -> tuple[str, str, str]:
        url = getattr(self.settings, f"wazuh_{component}_url", None)
        username = getattr(self.settings, f"wazuh_{component}_username", None)
        secret = getattr(self.settings, f"wazuh_{component}_password", None)
        if not url or not username or not username.strip() or secret is None:
            raise WazuhFailure("connector_unconfigured")
        password = secret.get_secret_value()
        if not password.strip():
            raise WazuhFailure("connector_unconfigured")
        return url.rstrip("/"), username, password

    def _ssl_context(self, component: Component) -> ssl.SSLContext:
        ca_file = getattr(self.settings, f"wazuh_{component}_ca_file", None)
        try:
            return ssl.create_default_context(cafile=str(ca_file) if ca_file else None)
        except (OSError, ValueError, ssl.SSLError) as problem:
            raise WazuhFailure("invalid_ca_file") from problem

    def _request(
        self,
        component: Component,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        body: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        url, username, password = self._credentials(component)
        timeout = self.settings.wazuh_timeout_seconds
        deadline = monotonic() + timeout
        context = self._ssl_context(component)
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        auth: httpx.BasicAuth | None = None
        if token is not None:
            headers["Authorization"] = f"Bearer {token}"
        else:
            auth = httpx.BasicAuth(username, password)
        transport = self.server_transport if component == "server" else self.indexer_transport
        try:
            with (
                httpx.Client(
                    base_url=url,
                    auth=auth,
                    headers=headers,
                    verify=context,
                    follow_redirects=False,
                    trust_env=False,
                    timeout=httpx.Timeout(timeout, connect=min(timeout, 5)),
                    transport=transport,
                ) as client,
                client.stream(method, path, params=params, json=body) as response,
            ):
                if response.status_code != 200:
                    if (
                        component == "indexer"
                        and response.status_code == 404
                        and path.endswith("/_search")
                    ):
                        raise WazuhFailure("alerts_index_missing")
                    raise WazuhFailure(
                        "upstream_rejected"
                        if response.status_code < 500
                        else "upstream_unavailable"
                    )
                if response.headers.get("content-encoding", "identity").lower() not in {
                    "identity",
                    "",
                }:
                    raise WazuhFailure("invalid_upstream_response")
                declared = response.headers.get("content-length")
                if declared is not None and not 0 <= int(declared) <= MAXIMUM_RESPONSE_BYTES:
                    raise WazuhFailure("invalid_upstream_response")
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise WazuhFailure("upstream_timeout")
                response.request.extensions.setdefault("timeout", {})["read"] = remaining
                chunks = bytearray()
                # Preserve network chunk boundaries: buffering small chunks until
                # a target size would hide slow streams from the deadline checks.
                for chunk in response.iter_bytes():
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        raise WazuhFailure("upstream_timeout")
                    response.request.extensions.setdefault("timeout", {})["read"] = remaining
                    if len(chunks) + len(chunk) > MAXIMUM_RESPONSE_BYTES:
                        raise WazuhFailure("invalid_upstream_response")
                    chunks.extend(chunk)
                if monotonic() > deadline:
                    raise WazuhFailure("upstream_timeout")
                data = json.loads(chunks)
                if not isinstance(data, dict):
                    raise WazuhFailure("invalid_upstream_response")
                return data
        except httpx.TimeoutException as problem:
            raise WazuhFailure("upstream_timeout") from problem
        except (httpx.HTTPError, OSError) as problem:
            raise WazuhFailure("upstream_unavailable") from problem
        except (ValueError, UnicodeError) as problem:
            raise WazuhFailure("invalid_upstream_response") from problem

    @staticmethod
    def _failure(problem: WazuhFailure) -> dict[str, Any]:
        state = "unconfigured" if problem.code == "connector_unconfigured" else "error"
        return envelope(state, error=problem.code)

    @staticmethod
    def _limit(limit: int) -> None:
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 500:
            raise ValueError("Wazuh result limit must be between 1 and 500")

    @staticmethod
    def _agent_id(agent_id: str | None) -> None:
        if agent_id is not None and (
            not isinstance(agent_id, str) or not re.fullmatch(r"[0-9]{1,32}", agent_id)
        ):
            raise ValueError("A numeric Wazuh agent ID string is required")

    def agents(
        self, limit: int = 100, offset: int = 0, agent_id: str | None = None
    ) -> dict[str, Any]:
        self._limit(limit)
        self._agent_id(agent_id)
        if not isinstance(offset, int) or isinstance(offset, bool) or not 0 <= offset <= 10000:
            raise ValueError("Wazuh result offset must be between 0 and 10000")
        try:
            login = ServerTokenEnvelope.model_validate(
                self._request("server", "POST", "/security/user/authenticate")
            )
            if login.error != 0:
                raise WazuhFailure("upstream_api_error")
            token = login.data.token.get_secret_value()
            if not token or len(token) > 16384 or any(character.isspace() for character in token):
                raise WazuhFailure("invalid_upstream_response")
            params: dict[str, str | int] = {
                "limit": limit,
                "offset": offset,
                "sort": "id",
                "select": AGENT_SELECT,
            }
            if agent_id is not None:
                params["agents_list"] = agent_id
            response = ServerAgentsEnvelope.model_validate(
                self._request(
                    "server",
                    "GET",
                    "/agents",
                    token=token,
                    params=params,
                )
            )
            if response.error not in {0, 2}:
                raise WazuhFailure("upstream_api_error")
            items = [
                {
                    "agent_id": agent.id,
                    "name": agent.name,
                    "status": agent.status,
                    "version": agent.version,
                    "last_keepalive": utc_string(agent.last_keep_alive),
                    "os": {
                        name: getattr(agent.os, name, None)
                        for name in ("name", "version", "platform", "arch")
                    },
                }
                for agent in response.data.affected_items
            ]
            if (
                len(items) > limit
                or len({item["agent_id"] for item in items}) != len(items)
                or agent_id is not None
                and any(item["agent_id"] != agent_id for item in items)
                or response.data.total_affected_items < offset + len(items)
                and bool(items)
                or not items
                and offset < response.data.total_affected_items
            ):
                raise WazuhFailure("invalid_upstream_response")
            if (
                response.error != 0
                or response.data.total_failed_items
                or response.data.failed_items
            ):
                return envelope(
                    "partial" if items else "error",
                    items=items if items else None,
                    error="upstream_partial" if items else "upstream_api_error",
                )
            return envelope(
                "connected", items=items, total=response.data.total_affected_items, relation="eq"
            )
        except ValidationError:
            return self._failure(WazuhFailure("invalid_upstream_response"))
        except WazuhFailure as problem:
            return self._failure(problem)

    def alerts(
        self, limit: int = 100, hours: int = 24, agent_id: str | None = None
    ) -> dict[str, Any]:
        self._limit(limit)
        if not isinstance(hours, int) or isinstance(hours, bool) or not 1 <= hours <= 168:
            raise ValueError("Wazuh alert window must be between 1 and 168 hours")
        self._agent_id(agent_id)
        filters: list[dict[str, Any]] = [
            {"range": {"timestamp": {"gte": f"now-{hours}h", "lte": "now"}}}
        ]
        if agent_id is not None:
            filters.append({"term": {"agent.id": agent_id}})
        try:
            response = IndexerSearchEnvelope.model_validate(
                self._request(
                    "indexer",
                    "POST",
                    f"/{self.settings.wazuh_alert_index}/_search",
                    params={"allow_no_indices": "false", "ignore_unavailable": "false"},
                    body={
                        "size": limit,
                        "track_total_hits": True,
                        "timeout": f"{self.settings.wazuh_timeout_seconds}s",
                        "_source": ALERT_FIELDS,
                        "sort": [{"timestamp": {"order": "desc"}}],
                        "query": {"bool": {"filter": filters}},
                    },
                )
            )
            items = [
                {
                    "index": hit.index,
                    "alert_id": hit.id,
                    "timestamp": utc_string(hit.source.timestamp),
                    "agent_id": hit.source.agent.id if hit.source.agent else None,
                    "agent_name": hit.source.agent.name if hit.source.agent else None,
                    "rule_id": hit.source.rule.id,
                    "level": hit.source.rule.level,
                    "description": hit.source.rule.description,
                    "groups": hit.source.rule.groups,
                }
                for hit in response.hits.hits
            ]
            relation = response.hits.total.relation
            if (
                len(items) > limit
                or response.hits.total.value < len(items)
                or len({(item["index"], item["alert_id"]) for item in items}) != len(items)
            ):
                raise WazuhFailure("invalid_upstream_response")
            if response.shards.total == 0:
                raise WazuhFailure("invalid_upstream_response")
            if (
                response.timed_out
                or response.shards.failed
                or response.shards.successful != response.shards.total
                or relation == "gte"
            ):
                return envelope("partial", items=items, relation=relation, error="upstream_partial")
            if len(items) != min(limit, response.hits.total.value):
                raise WazuhFailure("invalid_upstream_response")
            return envelope(
                "connected", items=items, total=response.hits.total.value, relation=relation
            )
        except ValidationError:
            return self._failure(WazuhFailure("invalid_upstream_response"))
        except WazuhFailure as problem:
            return self._failure(problem)

    def status(self) -> dict[str, Any]:
        server = self.agents(limit=1)
        server.pop("items", None)
        try:
            IndexerInfo.model_validate(self._request("indexer", "GET", "/"))
            indexer = envelope("connected")
        except ValidationError:
            indexer = self._failure(WazuhFailure("invalid_upstream_response"))
        except WazuhFailure as problem:
            indexer = self._failure(problem)
        indexer.pop("items", None)
        return {"server": server, "indexer": indexer}
