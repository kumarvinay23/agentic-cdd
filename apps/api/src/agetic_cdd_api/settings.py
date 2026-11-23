"""Application settings."""

from pathlib import Path
from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_API_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DB = _API_ROOT / "data" / "agetic_cdd.db"
_DEFAULT_DEALS = _API_ROOT / "data" / "deals"

# Dev-only: any port on loopback. Never enabled when app_env=production.
_DEV_LOCALHOST_ORIGIN_RE = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


def _compose_databook_database_url(
    *,
    host: str,
    port: int,
    name: str,
    user: str,
    password: str,
) -> str:
    """Build a Postgres DSN from discrete deploy knobs."""
    host = (host or "").strip()
    name = (name or "").strip() or "agetic_cdd_databook"
    if not host:
        return ""
    user = (user or "").strip()
    password = password or ""
    auth = ""
    if user:
        auth = quote_plus(user)
        if password:
            auth = f"{auth}:{quote_plus(password)}"
        auth = f"{auth}@"
    return f"postgresql://{auth}{host}:{int(port)}/{name}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGETIC_CDD_",
        env_file=str(_API_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "DiligenceIQ API"
    api_prefix: str = "/api/v1"
    # development | production — controls localhost CORS regex and startup checks.
    app_env: str = "development"
    # Explicit allowlist. Extra local ports need not be listed in development
    # (loopback regex applies). In production, set only real HTTPS UI origins.
    cors_origins: str = "http://127.0.0.1:3000,http://localhost:3000"
    host: str = "127.0.0.1"
    port: int = 4600

    database_url: str = f"sqlite:///{_DEFAULT_DB}"
    # PostgreSQL databook DSN. Full URL wins when set (any env / secret manager).
    # Empty + discrete DATABOOK_DB_* knobs → composed DSN. Empty leaves ontology off.
    databook_database_url: str = ""
    # Discrete knobs for deploys that inject host/port/user/password separately.
    # Used only when databook_database_url is empty.
    databook_db_host: str = ""
    databook_db_port: int = 5433
    databook_db_name: str = "agetic_cdd_databook"
    databook_db_user: str = ""
    databook_db_password: str = ""
    # Series read path: ontology | file | dual. Phase 4 is in, so ontology is the default.
    # dual prefers ontology facts and may still mirror the file store on HITL.
    databook_ui_source: str = "ontology"
    deals_storage_path: str = str(_DEFAULT_DEALS)
    jwt_secret: str = "dev-only-change-me-agetic-cdd-jwt-secret-32b"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24
    refresh_token_days: int = 30

    seed_admin_email: str = "admin@ageticcdd.com"
    seed_admin_password: str = "adminpass"
    seed_admin_name: str = "Admin"
    seed_org_name: str = "Agentic CDD Workspace"

    # LLM provider for Document Workspace / Deep Dive / FIN discovery JSON calls.
    # gemini | openai | anthropic — switch without code changes; restart API after change.
    llm_provider: str = "gemini"
    # Optional model override for the active provider. Empty → provider default below.
    llm_model: str = ""
    # Optional generic key for the active provider. Provider-specific keys win when set.
    llm_api_key: str = ""

    # Gemini (default provider). Empty key → heuristic only when provider=gemini.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # OpenAI-compatible Chat Completions (provider=openai).
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = "https://api.openai.com/v1"

    # Anthropic Messages API (provider=anthropic).
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"

    # Master switch for Document Workspace LLM synthesis (all providers).
    document_synthesis_llm: bool = True

    # Deep Dive hybrid refine (Slice 3+ pilot: satisfaction / buying). Off by default;
    # heuristics always run first. Soak with scripts/run_deep_dive_llm_soak.py before
    # enabling for CDD insight A/B.
    deep_dive_llm: bool = False

    # Gate 2 miss only: LLM ranks likely FIN_* files then re-runs parsers.
    # Off by default — never on the hot path for deals that already ingest series.
    # Quality harden rejects/reverts zero-only or no-improvement promotes.
    fin_discovery_on_gate2_miss: bool = False

    # When true, FDD/CDD export fails if the databook contract is incomplete.
    # When false (default), export still writes the file but marks it unreliable
    # and watermarks PPTX with UNRELIABLE.
    report_contract_strict: bool = False

    @model_validator(mode="after")
    def _resolve_databook_database_url(self) -> "Settings":
        """Prefer full URL; otherwise compose from discrete deploy env vars."""
        if str(self.databook_database_url or "").strip():
            return self
        composed = _compose_databook_database_url(
            host=self.databook_db_host,
            port=self.databook_db_port,
            name=self.databook_db_name,
            user=self.databook_db_user,
            password=self.databook_db_password,
        )
        if composed:
            self.databook_database_url = composed
        return self

    @property
    def databook_source(self) -> str:
        """ontology | file | dual. Anything else stays on ontology."""
        value = str(self.databook_ui_source or "").strip().lower()
        if value in {"ontology", "file", "dual"}:
            return value
        return "ontology"

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
