"""FastAPI dependencies."""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from agetic_cdd_api.db import get_db
from agetic_cdd_api.models import Member, Organization, User
from agetic_cdd_api.security import decode_access_token

bearer = HTTPBearer(auto_error=False)

_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


@dataclass
class AuthContext:
    user: User
    organization: Organization
    member: Member


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers=_WWW_AUTHENTICATE,
    )


def get_current_auth(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthContext:
    if not creds or creds.scheme.lower() != "bearer":
        raise _unauthorized("Not authenticated")
    try:
        payload = decode_access_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired token") from exc

    if payload.get("type") != "access":
        raise _unauthorized("Invalid token type")

    user_id = payload.get("sub")
    member_id = payload.get("member")
    org_id = payload.get("org")
    if not isinstance(user_id, str) or not isinstance(member_id, str) or not isinstance(org_id, str):
        raise _unauthorized("Invalid session context")

    # Single round-trip: member must bind this user to this org (blocks cross-tenant claim mix).
    member = db.scalar(
        select(Member)
        .options(joinedload(Member.user), joinedload(Member.organization))
        .where(
            Member.id == member_id,
            Member.user_id == user_id,
            Member.organization_id == org_id,
        )
    )
    if not member or not member.user or not member.organization:
        raise _unauthorized("Session no longer valid")

    return AuthContext(user=member.user, organization=member.organization, member=member)
