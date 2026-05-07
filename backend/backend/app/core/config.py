"""
Application configuration.

Values are loaded from environment variables (12-factor).
In production, secrets are fetched from Azure Key Vault using
Managed Identity — no credentials stored in code or env files.
"""

from __future__ import annotations

import functools
from typing import Literal

from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from azure.keyvault.secrets import SecretClient
from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    app_name: str = "Machine Monitoring API"
    app_version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    log_level: str = "INFO"

    # ------------------------------------------------------------------ #
    # Azure Key Vault (production only)
    # Use Managed Identity in Container Apps — no client_id/secret needed.
    # ------------------------------------------------------------------ #
    key_vault_url: str = ""

    # ------------------------------------------------------------------ #
    # Azure SQL Database
    # In dev: set DB_* env vars directly.
    # In prod: fetched from Key Vault (see computed_field below).
    # ------------------------------------------------------------------ #
    db_server: str = ""
    db_name: str = ""
    db_user: str = ""
    db_password: str = ""
    db_driver: str = "ODBC Driver 18 for SQL Server"

    # Connection pool tuning
    db_pool_size: int = 20
    db_max_overflow: int = 40
    db_pool_recycle_seconds: int = 3600
    db_echo: bool = False          # set True only for local debugging

    # ------------------------------------------------------------------ #
    # Redis (Azure Cache for Redis)
    # ------------------------------------------------------------------ #
    redis_url: str = "redis://localhost:6379/0"

    # TTL strategy by query range
    redis_ttl_realtime_seconds: int = 5     # last-minute queries
    redis_ttl_short_seconds: int = 30       # 1-hour range
    redis_ttl_medium_seconds: int = 300     # 6–24 hour range
    redis_ttl_long_seconds: int = 1800      # 7-day range

    # ------------------------------------------------------------------ #
    # Azure AD / JWT authentication
    # ------------------------------------------------------------------ #
    azure_tenant_id: str = ""
    azure_client_id: str = ""       # app registration client id
    # Audience must match the app registration in Azure AD
    jwt_audience: str = Field(default="", alias="AZURE_CLIENT_ID")
    jwt_algorithm: str = "RS256"

    # ------------------------------------------------------------------ #
    # Azure Application Insights
    # ------------------------------------------------------------------ #
    appinsights_connection_string: str = ""

    # ------------------------------------------------------------------ #
    # WebSocket
    # ------------------------------------------------------------------ #
    ws_push_interval_seconds: float = 1.0
    ws_max_connections_per_machine: int = 50

    # ------------------------------------------------------------------ #
    # CORS
    # ------------------------------------------------------------------ #
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"]
    )

    # ------------------------------------------------------------------ #
    # Rate limiting
    # ------------------------------------------------------------------ #
    rate_limit_requests_per_minute: int = 300

    # ------------------------------------------------------------------ #
    # Computed fields — fetch secrets from Key Vault in production
    # ------------------------------------------------------------------ #

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        server, db, user, password = (
            self.db_server,
            self.db_name,
            self.db_user,
            self.db_password,
        )

        if self.environment == "production" and self.key_vault_url:
            server, db, user, password = self._fetch_db_secrets()

        dsn = (
            f"DRIVER={{{self.db_driver}}};"
            f"SERVER={server};"
            f"DATABASE={db};"
            f"UID={user};"
            f"PWD={password};"
            "Encrypt=yes;"
            "TrustServerCertificate=no;"
            "Connection Timeout=30;"
        )
        # aioodbc uses the ODBC DSN wrapped in the SQLAlchemy URL
        from urllib.parse import quote_plus
        return f"mssql+aioodbc:///?odbc_connect={quote_plus(dsn)}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sync_database_url(self) -> str:
        """Synchronous URL used by Alembic migrations."""
        return self.database_url.replace("mssql+aioodbc", "mssql+pyodbc")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def openid_config_url(self) -> str:
        return (
            f"https://login.microsoftonline.com/{self.azure_tenant_id}"
            "/v2.0/.well-known/openid-configuration"
        )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    # ------------------------------------------------------------------ #
    # Key Vault helpers
    # ------------------------------------------------------------------ #

    @functools.cached_property
    def _kv_client(self) -> SecretClient:
        credential = (
            ManagedIdentityCredential()
            if self.environment == "production"
            else DefaultAzureCredential()
        )
        return SecretClient(vault_url=self.key_vault_url, credential=credential)

    def _fetch_db_secrets(self) -> tuple[str, str, str, str]:
        client = self._kv_client
        return (
            client.get_secret("db-server").value or "",
            client.get_secret("db-name").value or "",
            client.get_secret("db-user").value or "",
            client.get_secret("db-password").value or "",
        )

    def get_secret(self, secret_name: str) -> str:
        """Generic Key Vault secret fetch — use for any non-DB secret."""
        return self._kv_client.get_secret(secret_name).value or ""


@functools.lru_cache
def get_settings() -> Settings:
    """
    Cached singleton — import and call this everywhere.

        from app.core.config import get_settings
        settings = get_settings()
    """
    return Settings()
