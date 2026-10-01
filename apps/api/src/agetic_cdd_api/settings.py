"""Application settings."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB = _API_ROOT / "data" / "agetic_cdd.db"
_DEFAULT_DEALS = _API_ROOT / "data" / "deals"

# Dev-only: any port on loopback. Never enabled when app_env=production.
_DEV_LOCALHOST_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGETIC_CDD_",
        env_file=str(_API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agentic CDD API"
    api_prefix: str = "/api/v1"
    # development | production — controls localhost CORS regex and startup checks.
    app_env: str = "development"
    # Explicit allowlist. Extra local ports need not be listed in development
    # (loopback regex applies). In production, set only real HTTPS UI origins.
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    host: str = "127.0.0.1"
    port: int = 4600

    database_url: str = f"sqlite:///{_DEFAULT_DB}"
    deals_storage_path: str = str(_DEFAULT_DEALS)
    jwt_secret: str = "dev-only-change-me-agetic-cdd-jwt-secret-32b"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    refresh_token_days: int = 30

    seed_admin_email: str = "admin@ageticcdd.com"
    seed_admin_password: str = "adminpass"
    seed_admin_name: str = "Admin"
    seed_org_name: str = "Agentic CDD Workspace"

    # Document Workspace LLM synthesis (Gemini). Empty key → heuristic only.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"
    document_synthesis_llm: bool = True

    # Deep Dive hybrid refine (Slice 3+). Off by default; heuristics always run first.
    deep_dive_llm: bool = False

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if any(o == "*" for o in origins):
            raise ValueError(
                "AGETIC_CDD_CORS_ORIGINS must not contain '*'. "
                "Use an explicit allowlist of UI origins."
            )
        if self.is_production:
            loopback = [
                o
                for o in origins
                if "localhost" in o.lower() or "127.0.0.1" in o or "0.0.0.0" in o
            ]
            if loopback:
                raise ValueError(
                    "Production CORS must not allow loopback origins "
                    f"({', '.join(loopback)}). Set AGETIC_CDD_CORS_ORIGINS to "
                    "your HTTPS UI origin(s)."
                )
            insecure = [o for o in origins if o.startswith("http://")]
            if insecure:
                raise ValueError(
                    "Production CORS origins must use HTTPS "
                    f"({', '.join(insecure)})."
                )
        return origins

    @property
    def cors_origin_regex(self) -> str | None:
        """Allow any localhost / 127.0.0.1 port only outside production."""
        if self.is_production:
            return None
        return _DEV_LOCALHOST_ORIGIN_RE


settings = Settings()
