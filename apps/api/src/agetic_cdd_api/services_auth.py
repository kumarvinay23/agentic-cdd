"""Auth service — register, login, refresh, logout, session payload."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from agetic_cdd_api.models import Member, Organization, RefreshToken, User
from agetic_cdd_api.permissions import permissions_for_role, roles_for_member
from agetic_cdd_api.schemas_auth import (
    AuthData,
    MemberOut,
    OrganizationOut,
    TokensOut,
    UserOut,
)
from agetic_cdd_api.security import (
    create_access_token,
    create_refresh_token_value,
    hash_password,
    hash_token,
    new_id,
    verify_password,
)
from agetic_cdd_api.settings import settings

_MAX_ORG_SLUG_ATTEMPTS = 12


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "workspace"


def _next_org_slug_candidate(db: Session, base: str) -> str:
    """Best-effort free slug; UniqueConstraint is the source of truth under concurrency."""
    slug = _slugify(base)
    candidate = slug
    n = 1
    while db.scalar(select(Organization.id).where(Organization.slug == candidate)):
        n += 1
        candidate = f"{slug}-{n}"
    return candidate


def _user_out(user: User) -> UserOut:
    full = f"{user.first_name} {user.last_name}".strip() or user.email.split("@")[0]
    return UserOut(
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
        full_name=full,
        profile_image=None,
    )


def _org_out(org: Organization) -> OrganizationOut:
    return OrganizationOut(id=org.id, name=org.name, slug=org.slug)


def _member_out(member: Member, user: User) -> MemberOut:
    perms = permissions_for_role(member.role)
    roles = roles_for_member(member.role)
    last = member.last_active.isoformat().replace("+00:00", "Z") if member.last_active else None
    name = f"{user.first_name} {user.last_name}".strip() or user.email.split("@")[0]
    return MemberOut(
        id=member.id,
        uuid=member.id,
        email=user.email,
        firstName=user.first_name,
        lastName=user.last_name,
        name=name,
        role=member.role,
        roles=roles,
        permissions=perms,
        access=member.access,
        lastActive=last,
    )


def build_auth_data(
    *,
    user: User,
    org: Organization,
    member: Member,
    tokens: TokensOut | None = None,
) -> AuthData:
    member_out = _member_out(member, user)
    return AuthData(
        user=_user_out(user),
        organization=_org_out(org),
        member=member_out,
        permissions=member_out.permissions,
        roles=member_out.roles,
        tokens=tokens,
    )


def _resolve_membership(
    db: Session,
    *,
    user: User,
    organization_id: str | None,
) -> tuple[Member, Organization]:
    """Resolve the exact org membership for this session (no arbitrary first-row pick)."""
    if organization_id:
        member = db.scalar(
            select(Member).where(
                Member.user_id == user.id,
                Member.organization_id == organization_id,
            )
        )
        if not member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Not a member of the requested organization",
            )
    else:
        members = db.scalars(
            select(Member)
            .where(Member.user_id == user.id)
            .order_by(Member.last_active.desc().nulls_last(), Member.id.asc())
        ).all()
        if not members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization membership",
            )
        if len(members) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="organization_id is required when the user belongs to multiple organizations",
            )
        member = members[0]

    org = db.get(Organization, member.organization_id)
    if not org:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Organization missing")
    return member, org


def _revoke_all_refresh_tokens(db: Session, *, user_id: str) -> None:
    now = datetime.now(UTC)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    db.commit()


def _issue_tokens(db: Session, *, user: User, org: Organization, member: Member) -> TokensOut:
    access = create_access_token(user_id=user.id, org_id=org.id, member_id=member.id)
    refresh = create_refresh_token_value()
    db.add(
        RefreshToken(
            id=new_id(),
            user_id=user.id,
            organization_id=org.id,
            token_hash=hash_token(refresh),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    db.commit()
    return TokensOut(accessToken=access, refreshToken=refresh)


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    organization_name: str,
) -> AuthData:
    email_n = email.strip().lower()
    if db.scalar(select(User.id).where(User.email == email_n)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    org_name = organization_name.strip() or f"{first_name or email_n.split('@')[0]} Workspace"
    user_id = new_id("usr_")
    org_id = new_id("org_")
    member_id = new_id()
    password_hash = hash_password(password)
    first = first_name.strip()
    last = last_name.strip()

    last_error: Exception | None = None
    for attempt in range(_MAX_ORG_SLUG_ATTEMPTS):
        slug = (
            _next_org_slug_candidate(db, org_name)
            if attempt == 0
            else _next_org_slug_candidate(db, f"{_slugify(org_name)}-{attempt + 1}")
        )
        user = User(
            id=user_id,
            email=email_n,
            password_hash=password_hash,
            first_name=first,
            last_name=last,
        )
        org = Organization(id=org_id, name=org_name, slug=slug)
        member = Member(
            id=member_id,
            organization_id=org.id,
            user_id=user.id,
            role="owner",
            access="full",
            last_active=datetime.now(UTC),
        )
        try:
            db.add_all([user, org, member])
            db.commit()
            db.refresh(user)
            db.refresh(org)
            db.refresh(member)
            tokens = _issue_tokens(db, user=user, org=org, member=member)
            return build_auth_data(user=user, org=org, member=member, tokens=tokens)
        except IntegrityError as exc:
            db.rollback()
            last_error = exc
            if db.scalar(select(User.id).where(User.email == email_n)):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already registered",
                ) from exc
            continue

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Could not allocate a unique organization slug. Please try a different name.",
    ) from last_error


def login_user(
    db: Session,
    *,
    email: str,
    password: str,
    organization_id: str | None = None,
) -> AuthData:
    email_n = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email_n))
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials. Please try again.",
        )

    member, org = _resolve_membership(db, user=user, organization_id=organization_id)
    member.last_active = datetime.now(UTC)
    db.commit()
    db.refresh(member)

    tokens = _issue_tokens(db, user=user, org=org, member=member)
    return build_auth_data(user=user, org=org, member=member, tokens=tokens)


def refresh_session(db: Session, *, refresh_token: str) -> AuthData:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="refresh_token required")

    hashed = hash_token(refresh_token)
    row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hashed))
    if not row:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    # Reuse detection: presenting a revoked refresh token indicates possible theft.
    if row.revoked_at is not None:
        _revoke_all_refresh_tokens(db, user_id=row.user_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token reuse detected; all sessions revoked",
        )

    if row.expires_at < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    member, org = _resolve_membership(db, user=user, organization_id=row.organization_id)

    row.revoked_at = datetime.now(UTC)
    db.commit()
    tokens = _issue_tokens(db, user=user, org=org, member=member)
    return build_auth_data(user=user, org=org, member=member, tokens=tokens)


def logout_user(db: Session, *, refresh_token: str | None) -> None:
    if not refresh_token:
        return
    row = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(refresh_token))
    )
    if row and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        db.commit()


def get_session_for_user(
    db: Session,
    *,
    user_id: str,
    organization_id: str,
) -> AuthData:
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    member, org = _resolve_membership(db, user=user, organization_id=organization_id)
    member.last_active = datetime.now(UTC)
    db.commit()
    return build_auth_data(user=user, org=org, member=member, tokens=None)
