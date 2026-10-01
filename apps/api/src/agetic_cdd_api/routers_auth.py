"""Auth routes — DiligenceIQ-compatible /api/v1/auth/*."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from agetic_cdd_api.db import get_db
from agetic_cdd_api.deps import AuthContext, bearer, get_current_auth
from agetic_cdd_api.schemas_auth import LoginRequest, RefreshRequest, RegisterRequest
from agetic_cdd_api.services_auth import (
    get_session_for_user,
    login_user,
    logout_user,
    refresh_session,
    register_user,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    data = register_user(
        db,
        email=str(body.email),
        password=body.password,
        first_name=body.firstName,
        last_name=body.lastName,
        organization_name=body.organizationName,
    )
    return {"success": True, "data": data.model_dump()}


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)) -> dict:
    data = login_user(
        db,
        email=str(body.email),
        password=body.password,
        organization_id=body.resolved_organization_id(),
    )
    return {"success": True, "data": data.model_dump()}


@router.post("/refresh")
def refresh(
    body: RefreshRequest | None = None,
    refresh_token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    token = (body.token_value() if body else None) or refresh_token
    data = refresh_session(db, refresh_token=token or "")
    return {"success": True, "data": data.model_dump()}


@router.post("/logout")
def logout(
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
    _creds: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> dict:
    token = body.token_value() if body else None
    logout_user(db, refresh_token=token)
    return {"success": True, "data": {"ok": True}}


@router.get("/me")
def me(auth: AuthContext = Depends(get_current_auth), db: Session = Depends(get_db)) -> dict:
    data = get_session_for_user(
        db,
        user_id=auth.user.id,
        organization_id=auth.organization.id,
    )
    return {"success": True, "data": data.model_dump()}
