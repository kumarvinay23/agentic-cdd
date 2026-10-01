"""FastAPI application — Agentic CDD /api/v1."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agetic_cdd_api import __version__
from agetic_cdd_api.db import Base, SessionLocal, engine, ensure_schema
from agetic_cdd_api.deps import AuthContext, get_current_auth
from agetic_cdd_api.permissions import ALL_PERMISSIONS
from agetic_cdd_api.routers_auth import router as auth_router
from agetic_cdd_api.routers_dealroom import router as dealroom_router
from agetic_cdd_api.routers_deals import router as deals_router
from agetic_cdd_api.routers_documents import router as documents_router
from agetic_cdd_api.routers_pipeline import router as pipeline_router
from agetic_cdd_api.routers_reports import router as reports_router
import agetic_cdd_api.report_ops_dashboard as _ops_dashboard  # noqa: F401  register builder
import agetic_cdd_api.report_strategy as _strategy_report  # noqa: F401  register builder
import agetic_cdd_api.report_ic_memo as _ic_memo  # noqa: F401  register builder
import agetic_cdd_api.report_market_deck as _market_deck  # noqa: F401  register builder
import agetic_cdd_api.report_cdd_deck as _cdd_deck  # noqa: F401  register builder
from agetic_cdd_api.seed import seed_admin
from agetic_cdd_api.settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = SessionLocal()
    try:
        seed_admin(db)
    finally:
        db.close()
    yield


app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

# Explicit origin allowlist. In development, also match any loopback port so
# alternate Next.js ports (e.g. :3001) work without widening production CORS.
_cors_kwargs: dict = {
    "allow_origins": settings.cors_origin_list,
    "allow_credentials": True,
    "allow_methods": ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    "allow_headers": ["Authorization", "Content-Type", "Accept"],
}
if settings.cors_origin_regex:
    _cors_kwargs["allow_origin_regex"] = settings.cors_origin_regex
app.add_middleware(CORSMiddleware, **_cors_kwargs)

app.include_router(auth_router, prefix=settings.api_prefix)
app.include_router(deals_router, prefix=settings.api_prefix)
app.include_router(dealroom_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(pipeline_router, prefix=settings.api_prefix)
app.include_router(reports_router, prefix=settings.api_prefix)


@app.get("/api/v1/health")
async def health() -> dict:
    return {
        "ok": True,
        "service": "agetic-cdd-api",
        "version": __version__,
        "product": "Agentic CDD",
        "wave": "W5",
    }


@app.get("/api/v1/organizations")
def organizations(auth: AuthContext = Depends(get_current_auth)) -> dict:
    org = auth.organization
    return {
        "success": True,
        "data": {"_id": org.id, "id": org.id, "name": org.name, "slug": org.slug},
    }


@app.get("/api/v1/organizations/permissions")
def list_permissions(_auth: AuthContext = Depends(get_current_auth)) -> dict:
    return {"success": True, "data": list(ALL_PERMISSIONS)}


@app.get("/")
async def root() -> dict:
    return {
        "product": "Agentic CDD",
        "api": settings.api_prefix,
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }
