"""FastAPI application for Agentic CDD Portfolio dashboard."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from agetic_cdd.data import create_deal, portfolio_payload

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Agentic CDD")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


class CreateDealRequest(BaseModel):
    name: str = Field(min_length=1)
    slug: str | None = None
    description: str = ""
    tags: str = ""
    industry: str = "Other / Generic"


@app.get("/", response_class=HTMLResponse)
async def portfolio_dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="portfolio.html",
        context=portfolio_payload(),
    )


@app.get("/api/portfolio")
async def portfolio_api() -> dict:
    return portfolio_payload()


@app.post("/api/deals")
async def create_deal_api(payload: CreateDealRequest) -> dict:
    tags = [part.strip() for part in payload.tags.split(",") if part.strip()]
    try:
        return create_deal(
            name=payload.name,
            slug=payload.slug,
            description=payload.description,
            tags=tags,
            industry=payload.industry,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
