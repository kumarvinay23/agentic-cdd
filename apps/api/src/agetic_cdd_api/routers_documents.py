"""Document Workspace routes — DiligenceIQ-compatible /documents + /cdd/capabilities."""

from __future__ import annotations

import json
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from agetic_cdd_api.db import get_db
from agetic_cdd_api.deps import AuthContext, get_current_auth
from agetic_cdd_api.document_capabilities import list_capabilities
from agetic_cdd_api.services_deals import get_deal
from agetic_cdd_api.services_documents import (
    build_decision_chain,
    build_suggestions,
    export_document_bundle,
    get_document,
    iter_post_message_events,
    list_messages,
    post_message,
    put_document,
)
from agetic_cdd_api.services_agent_documents import (
    build_agent_decision_chain,
    build_agent_suggestions,
    get_agent_document,
    get_agent_version,
    iter_agent_post_message_events,
    list_agent_messages,
    list_agent_versions,
    post_agent_message,
    put_agent_document,
)

router = APIRouter(tags=["documents"])


class DocumentPutBody(BaseModel):
    document: str = Field(..., description="Full markdown CDD document body")


class DocumentMessageBody(BaseModel):
    content: str = Field(..., min_length=1, description="User prompt for the document copilot")
    capability_ids: list[str] | None = Field(
        default=None,
        description="Optional explicit capability ids from the catalog panel",
    )


def _sse_pack(event: dict) -> str:
    etype = str(event.get("type") or "message")
    return f"event: {etype}\ndata: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.get("/portfolios/{deal_id}/documents")
def get_deal_document(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return get_document(deal)


@router.put("/portfolios/{deal_id}/documents")
def update_deal_document(
    deal_id: str,
    body: DocumentPutBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return put_document(deal, document=body.document)


@router.get("/portfolios/{deal_id}/documents/messages")
def get_document_messages(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return list_messages(deal)


@router.post("/portfolios/{deal_id}/documents/messages")
def create_document_message(
    deal_id: str,
    body: DocumentMessageBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return post_message(
        deal,
        content=body.content,
        capability_ids=body.capability_ids,
        db=db,
    )


@router.post("/portfolios/{deal_id}/documents/messages/stream")
def stream_document_message(
    deal_id: str,
    body: DocumentMessageBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """SSE progress for document research (task running→done, then final turn)."""
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)

    def generate() -> Iterator[str]:
        for event in iter_post_message_events(
            deal,
            content=body.content,
            capability_ids=body.capability_ids,
            db=db,
        ):
            yield _sse_pack(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/portfolios/{deal_id}/documents/suggestions")
def get_document_suggestions(
    deal_id: str,
    after_prompt: str | None = Query(default=None, description="Contextual next steps after this prompt"),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return build_suggestions(deal, after_prompt=after_prompt)


@router.get("/portfolios/{deal_id}/documents/decision-chain")
def get_document_decision_chain(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return build_decision_chain(deal)


@router.get("/portfolios/{deal_id}/documents/export")
def get_document_export(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return export_document_bundle(deal)


@router.get("/portfolios/{deal_id}/cdd/capabilities")
def get_cdd_capabilities(
    deal_id: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> list:
    # Validate deal ownership; catalog itself is org-agnostic.
    get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return list_capabilities()


# ---------------------------------------------------------------------------
# Per-agent documents (Workflow agent click → Document copilot)
# ---------------------------------------------------------------------------


@router.get("/portfolios/{deal_id}/agents/{agent_key}/documents")
def get_agent_deal_document(
    deal_id: str,
    agent_key: str,
    refresh: bool = Query(default=False),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return get_agent_document(deal, agent_key, refresh=refresh)


@router.put("/portfolios/{deal_id}/agents/{agent_key}/documents")
def update_agent_deal_document(
    deal_id: str,
    agent_key: str,
    body: DocumentPutBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return put_agent_document(deal, agent_key, document=body.document)


@router.get("/portfolios/{deal_id}/agents/{agent_key}/documents/messages")
def get_agent_document_messages(
    deal_id: str,
    agent_key: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return list_agent_messages(deal, agent_key)


@router.post("/portfolios/{deal_id}/agents/{agent_key}/documents/messages")
def create_agent_document_message(
    deal_id: str,
    agent_key: str,
    body: DocumentMessageBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return post_agent_message(
        deal,
        agent_key,
        content=body.content,
        capability_ids=body.capability_ids,
        db=db,
    )


@router.post("/portfolios/{deal_id}/agents/{agent_key}/documents/messages/stream")
def stream_agent_document_message(
    deal_id: str,
    agent_key: str,
    body: DocumentMessageBody,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)

    def generate() -> Iterator[str]:
        for event in iter_agent_post_message_events(
            deal,
            agent_key,
            content=body.content,
            capability_ids=body.capability_ids,
            db=db,
        ):
            yield _sse_pack(event)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/portfolios/{deal_id}/agents/{agent_key}/documents/suggestions")
def get_agent_document_suggestions(
    deal_id: str,
    agent_key: str,
    after_prompt: str | None = Query(default=None),
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return build_agent_suggestions(deal, agent_key, after_prompt=after_prompt)


@router.get("/portfolios/{deal_id}/agents/{agent_key}/documents/decision-chain")
def get_agent_document_decision_chain(
    deal_id: str,
    agent_key: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return build_agent_decision_chain(deal, agent_key)


@router.get("/portfolios/{deal_id}/agents/{agent_key}/documents/versions")
def get_agent_document_versions(
    deal_id: str,
    agent_key: str,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return list_agent_versions(deal, agent_key)


@router.get("/portfolios/{deal_id}/agents/{agent_key}/documents/versions/{version_n}")
def get_agent_document_version(
    deal_id: str,
    agent_key: str,
    version_n: int,
    auth: AuthContext = Depends(get_current_auth),
    db: Session = Depends(get_db),
) -> dict:
    deal = get_deal(db, org_id=auth.organization.id, deal_id=deal_id)
    return get_agent_version(deal, agent_key, version_n)
