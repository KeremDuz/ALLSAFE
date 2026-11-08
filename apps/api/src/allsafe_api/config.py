"""Typed settings for the laboratory API."""

from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read configuration from ALLSAFE_ variables (or an explicit constructor)."""

    model_config = SettingsConfigDict(env_prefix="ALLSAFE_", env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./data/allsafe.db"
    bootstrap_admin_token: SecretStr | None = None
    authentication_mode: Literal["local", "oidc"] = "local"
    initial_admin_email: str = "admin@allsafe.local"
    initial_admin_password: SecretStr | None = None
    user_session_ttl_seconds: int = Field(default=28800, ge=60, le=86400)
    dev_auto_login: bool = Field(
        default=False,
        description="Loopback development only: the panel signs in as the initial administrator.",
    )
    cookie_secure: bool = False
    frontend_url: str = "http://127.0.0.1:5173"
    api_url: str = "http://127.0.0.1:8000"
    session_signing_secret: SecretStr | None = None
    oidc_server_metadata_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: SecretStr | None = None
    oidc_redirect_uri: str = "http://127.0.0.1:8000/api/v1/auth/oidc/callback"
    initialize_schema: bool = Field(
        default=True,
        description="Create missing tables in development/test only; use Alembic otherwise.",
    )
    heartbeat_timeout_seconds: int = Field(default=120, ge=10, le=86400)
    phishcatch_url: str | None = None
    phishcatch_integration_key: SecretStr | None = None
    phishcatch_timeout_seconds: int = Field(default=45, ge=1, le=60)
    phishcatch_allow_loopback_http: bool = False
    wazuh_server_url: str | None = None
    wazuh_server_username: str | None = None
    wazuh_server_password: SecretStr | None = None
    wazuh_server_ca_file: str | None = None
    wazuh_indexer_url: str | None = None
    wazuh_indexer_username: str | None = None
    wazuh_indexer_password: SecretStr | None = None
    wazuh_indexer_ca_file: str | None = None
    wazuh_timeout_seconds: int = Field(default=5, ge=1, le=30)
    wazuh_allow_loopback_http: bool = False
    managed_access_config_file: str | None = None
    wazuh_alert_index: str = Field(
        default="wazuh-alerts-*", pattern=r"^wazuh-alerts-[a-zA-Z0-9.*_-]+$"
    )

    @field_validator(
        "bootstrap_admin_token",
        "initial_admin_password",
        "session_signing_secret",
        "oidc_client_secret",
        "phishcatch_integration_key",
        "wazuh_server_password",
        "wazuh_indexer_password",
        mode="before",
    )
    @classmethod
    def empty_token_is_unconfigured(cls, value: object) -> object:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str) and not raw.strip():
            return None
        return value

    @field_validator("initial_admin_email")
    @classmethod
    def normalize_admin_email(cls, value: str) -> str:
        return value.strip().lower()

    @model_validator(mode="after")
    def validate_identity_configuration(self) -> "Settings":
        if self.phishcatch_url:
            parsed = urlsplit(self.phishcatch_url)
            if (
                not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError(
                    "PhishCatch URL must be a server origin without credentials or a path"
                )
            if parsed.scheme != "https" and not (
                self.phishcatch_allow_loopback_http
                and parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            ):
                raise ValueError(
                    "PhishCatch requires HTTPS outside an explicitly enabled loopback lab"
                )
        if (
            self.phishcatch_integration_key
            and len(self.phishcatch_integration_key.get_secret_value()) < 32
        ):
            raise ValueError("PhishCatch integration key must contain at least 32 characters")
        if (
            self.initial_admin_password is not None
            and len(self.initial_admin_password.get_secret_value()) < 12
        ):
            raise ValueError("Initial administrator password must contain at least 12 characters")
        if self.dev_auto_login and (
            self.environment != "development"
            or self.authentication_mode != "local"
            or any(
                urlsplit(value).hostname not in {"127.0.0.1", "localhost", "::1"}
                for value in (self.frontend_url, self.api_url)
            )
        ):
            raise ValueError(
                "Development auto-login requires the development environment, local "
                "authentication and loopback panel/API URLs"
            )
        if self.authentication_mode == "oidc":
            if not all(
                (
                    self.oidc_server_metadata_url,
                    self.oidc_client_id,
                    self.oidc_client_secret,
                    self.session_signing_secret,
                )
            ):
                raise ValueError("OIDC requires metadata URL, client ID/secret and signing secret")
            if len(self.session_signing_secret.get_secret_value()) < 32:
                raise ValueError("OIDC signing secret must contain at least 32 characters")
            for value in (
                self.frontend_url,
                self.api_url,
                self.oidc_server_metadata_url,
                self.oidc_redirect_uri,
            ):
                parsed = urlsplit(value)
                if parsed.scheme != "https" and not (
                    parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                ):
                    raise ValueError("OIDC endpoints require HTTPS outside the loopback lab")
            # Browser cookies are bound to ALLSAFE, never to the provider's host.
            browser_urls = (self.frontend_url, self.api_url, self.oidc_redirect_uri)
            if not self.cookie_secure and any(
                urlsplit(value).hostname not in {"127.0.0.1", "localhost", "::1"}
                for value in browser_urls
            ):
                raise ValueError("OIDC outside loopback requires secure cookies")
        return self

    @field_validator(
        "wazuh_server_url",
        "wazuh_indexer_url",
        "wazuh_server_username",
        "wazuh_indexer_username",
        "wazuh_server_ca_file",
        "wazuh_indexer_ca_file",
        mode="before",
    )
    @classmethod
    def empty_wazuh_setting_is_unconfigured(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value

    @model_validator(mode="after")
    def validate_wazuh_origins(self) -> "Settings":
        for value in (self.wazuh_server_url, self.wazuh_indexer_url):
            if value is None:
                continue
            parsed = urlsplit(value)
            if (
                not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or parsed.path not in {"", "/"}
            ):
                raise ValueError(
                    "Wazuh endpoints must be server origins without embedded credentials"
                )
            _ = parsed.port
            if parsed.scheme != "https" and not (
                self.wazuh_allow_loopback_http
                and parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost", "::1"}
            ):
                raise ValueError("Wazuh requires HTTPS outside an explicitly enabled loopback lab")
        return self
