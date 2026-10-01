"""Seed default admin workspace on startup."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from agetic_cdd_api.models import User
from agetic_cdd_api.services_auth import register_user
from agetic_cdd_api.settings import settings


def seed_admin(db: Session) -> None:
    email = settings.seed_admin_email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        return
    register_user(
        db,
        email=email,
        password=settings.seed_admin_password,
        first_name=settings.seed_admin_name,
        last_name="",
        organization_name=settings.seed_org_name,
    )
