"""Bounded response contracts for the Wazuh server and indexer APIs."""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, SecretStr


def _utc_timestamp(value: object) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as problem:
            raise ValueError("An ISO 8601 timestamp is required") from problem
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("A timestamp with a timezone is required")
    return value.astimezone(UTC)


Timestamp = Annotated[datetime, BeforeValidator(_utc_timestamp)]
AgentId = Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[0-9]+$")]
NonNegativeInt = Annotated[int, Field(ge=0)]
AgentName = Annotated[str, Field(min_length=1, max_length=255)]
MetadataText = Annotated[str, Field(max_length=255)]
RuleGroup = Annotated[str, Field(min_length=1, max_length=128)]


class WazuhResponseModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True, populate_by_name=True)


class ServerTokenData(WazuhResponseModel):
    token: SecretStr


class ServerTokenEnvelope(WazuhResponseModel):
    error: int
    data: ServerTokenData


class ServerAgentOS(WazuhResponseModel):
    name: MetadataText | None = None
    version: MetadataText | None = None
    platform: MetadataText | None = None
    arch: MetadataText | None = None


class ServerAgent(WazuhResponseModel):
    id: AgentId
    name: AgentName | None = None
    status: Literal["active", "pending", "never_connected", "disconnected"] | None = None
    version: MetadataText | None = None
    last_keep_alive: Timestamp | None = Field(default=None, alias="lastKeepAlive")
    os: ServerAgentOS | None = None


class ServerAgentsData(WazuhResponseModel):
    affected_items: list[ServerAgent]
    total_affected_items: NonNegativeInt
    total_failed_items: NonNegativeInt
    failed_items: list[Any]


class ServerAgentsEnvelope(WazuhResponseModel):
    error: int
    message: Annotated[str, Field(max_length=2048)] | None = None
    data: ServerAgentsData


class IndexerVersion(WazuhResponseModel):
    number: Annotated[str, Field(min_length=1, max_length=80)]


class IndexerInfo(WazuhResponseModel):
    version: IndexerVersion
    cluster_name: MetadataText | None = None


IndexerRootResponse = IndexerInfo


class IndexerShards(WazuhResponseModel):
    total: NonNegativeInt
    successful: NonNegativeInt
    skipped: NonNegativeInt
    failed: NonNegativeInt


class IndexerHitsTotal(WazuhResponseModel):
    value: NonNegativeInt
    relation: Literal["eq", "gte"]


class IndexerAlertAgent(WazuhResponseModel):
    id: AgentId | None = None
    name: AgentName | None = None


class IndexerRule(WazuhResponseModel):
    id: Annotated[str, Field(min_length=1, max_length=80)]
    level: Annotated[int, Field(ge=0, le=16)] | None = None
    description: Annotated[str, Field(max_length=2048)] | None = None
    groups: list[RuleGroup] = Field(default_factory=list, max_length=100)


class IndexerAlertSource(WazuhResponseModel):
    timestamp: Timestamp
    agent: IndexerAlertAgent | None = None
    rule: IndexerRule


class IndexerSearchHit(WazuhResponseModel):
    index: Annotated[str, Field(min_length=1, max_length=255)] = Field(alias="_index")
    id: Annotated[str, Field(min_length=1, max_length=512)] = Field(alias="_id")
    source: IndexerAlertSource = Field(alias="_source")


class IndexerHits(WazuhResponseModel):
    total: IndexerHitsTotal
    hits: list[IndexerSearchHit]


class IndexerSearchEnvelope(WazuhResponseModel):
    timed_out: bool
    shards: IndexerShards = Field(alias="_shards")
    hits: IndexerHits
