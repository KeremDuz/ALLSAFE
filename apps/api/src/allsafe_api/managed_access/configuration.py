"""Read-only local administrator mappings. No browser-controlled connection targets."""

import hashlib
import ipaddress
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ConfigurationError(Exception):
    """The configured mapping is unavailable; never expose local paths or file content."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SSHProfile(StrictModel):
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    client_key_file: str = Field(min_length=1, max_length=1024)
    known_hosts_file: str = Field(min_length=1, max_length=1024)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9_.@\\-]{1,120}", value):
            raise ValueError("Invalid account name")
        return value


class RDPProfile(StrictModel):
    port: int = Field(default=3389, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str | None) -> str | None:
        return SSHProfile.valid_username(value) if value is not None else None


class DeviceProfile(StrictModel):
    device_id: str
    host: str = Field(min_length=1, max_length=253)
    ssh: SSHProfile | None = None
    rdp: RDPProfile | None = None

    @field_validator("device_id")
    @classmethod
    def valid_device_id(cls, value: str) -> str:
        return str(UUID(value))

    @field_validator("host")
    @classmethod
    def valid_host(cls, value: str) -> str:
        try:
            address = ipaddress.ip_address(value)
            if "%" in value:
                raise ValueError("Scoped IPv6 is not supported")
            return str(address)
        except ValueError:
            if len(value) > 253 or any(
                not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                for label in value.rstrip(".").split(".")
            ):
                raise ValueError("Host must be a DNS name or IP address") from None
            return value.lower().rstrip(".")

    @model_validator(mode="after")
    def has_service(self) -> "DeviceProfile":
        if self.ssh is None and self.rdp is None:
            raise ValueError("At least one access service is required")
        return self


class Configuration(StrictModel):
    version: Literal[1]
    devices: list[DeviceProfile] = Field(max_length=512)

    @field_validator("version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Configuration version must be an integer")
        return value

    @model_validator(mode="after")
    def unique_devices(self) -> "Configuration":
        if len({profile.device_id for profile in self.devices}) != len(self.devices):
            raise ValueError("Duplicate device mapping")
        return self


@dataclass(frozen=True)
class ResolvedProfile:
    profile: DeviceProfile
    fingerprint: str
    key: bytes | None
    known_hosts: bytes | None


def read_local(path: Path, maximum: int, *, secret: bool = False) -> bytes:
    # These are administrator-owned local configuration files, not uploads. On
    # Windows deployment ACLs are provisioned by the administrator/preflight.
    if str(path).startswith(("\\\\", "//")) or any(
        ancestor.is_symlink() or ancestor.is_junction() for ancestor in (path, *path.parents)
    ):
        raise ConfigurationError
    with path.open("rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ConfigurationError
        if os.name != "nt" and (
            info.st_uid not in {0, os.geteuid()}
            or info.st_mode & 0o022
            or (secret and info.st_mode & 0o077)
        ):
            raise ConfigurationError
        data = stream.read(maximum + 1)
        if not data or len(data) > maximum:
            raise ConfigurationError
        return data


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ConfigurationError
        result[key] = value
    return result


def resolve_profile(config_file: str | None, device_id: str) -> ResolvedProfile | None:
    if not config_file:
        return None
    try:
        path = Path(config_file).absolute()
        content = read_local(path, 128 * 1024)
        configuration = Configuration.model_validate(
            json.loads(content, object_pairs_hook=no_duplicates)
        )
        profile = next((p for p in configuration.devices if p.device_id == device_id), None)
        if profile is None:
            return None
        key = known_hosts = None
        if profile.ssh:
            key = read_local(path.parent / profile.ssh.client_key_file, 32 * 1024, secret=True)
            known_hosts = read_local(path.parent / profile.ssh.known_hosts_file, 128 * 1024)
            if not key.strip() or not known_hosts.strip():
                raise ConfigurationError
        fingerprint = hashlib.sha256(content + (key or b"") + (known_hosts or b"")).hexdigest()
        return ResolvedProfile(profile, fingerprint, key, known_hosts)
    except (OSError, ValueError, TypeError, RecursionError):
        raise ConfigurationError from None
