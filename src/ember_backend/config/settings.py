from __future__ import annotations

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    store_to_sql: bool = Field(default=True, alias="STORE_TO_SQL")

    sqlserver_host: str = Field(default="127.0.0.1", alias="SQLSERVER_HOST")
    sqlserver_port: int = Field(default=1433, alias="SQLSERVER_PORT")
    sqlserver_database: str = Field(default="Ember", alias="SQLSERVER_DATABASE")
    sqlserver_user: str = Field(default="sa", alias="SQLSERVER_USER")
    sqlserver_password: str = Field(default="", alias="SQLSERVER_PASSWORD")
    sqlserver_trust_server_cert: bool = Field(default=True, alias="SQLSERVER_TRUST_SERVER_CERT")

    database_url: str | None = Field(default=None, alias="DATABASE_URL")

    jwt_secret: str = Field(default="ember-dev-secret-change-me-please-rotate-32-bytes", alias="JWT_SECRET")
    jwt_issuer: str = Field(default="ember-backend", alias="JWT_ISSUER")
    jwt_ttl_minutes: int = Field(default=45, alias="JWT_TTL_MINUTES")

    webauthn_rp_id: str = Field(default="example.com", alias="WEBAUTHN_RP_ID")
    webauthn_allowed_origins: str = Field(default="https://example.com", alias="WEBAUTHN_ALLOWED_ORIGINS")
    webauthn_mode: str = Field(default="strict", alias="WEBAUTHN_MODE")
    challenge_ttl_seconds: int = Field(default=300, alias="CHALLENGE_TTL_SECONDS")
    aasa_app_ids: str = Field(default="", alias="AASA_APP_IDS")

    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    suggested_sync_after_seconds: int = Field(default=21600, alias="SUGGESTED_SYNC_AFTER_SECONDS")

    @property
    def allowed_origins(self) -> set[str]:
        return {x.strip() for x in self.webauthn_allowed_origins.split(",") if x.strip()}

    @property
    def apple_app_site_association_app_ids(self) -> list[str]:
        return [x.strip() for x in self.aasa_app_ids.split(",") if x.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        if not self.store_to_sql:
            return "sqlite:///./ember.db"

        password = quote_plus(self.sqlserver_password)
        trust = "yes" if self.sqlserver_trust_server_cert else "no"
        return (
            "mssql+pyodbc://"
            f"{self.sqlserver_user}:{password}@{self.sqlserver_host}:{self.sqlserver_port}/{self.sqlserver_database}"
            "?driver=ODBC+Driver+18+for+SQL+Server"
            f"&TrustServerCertificate={trust}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
