"""ORM models for auth, tenancy, and deals."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from agetic_cdd_api.db import Base, UTCDateTime


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    members: Mapped[list[Member]] = relationship(back_populates="organization")
    deals: Mapped[list[Deal]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str] = mapped_column(String(120), default="")
    last_name: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    members: Mapped[list[Member]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user")


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("organization_id", "user_id", name="uq_org_user"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String(32), default="owner")
    access: Mapped[str] = mapped_column(String(32), default="full")
    last_active: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="members")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    organization_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("organizations.id"), nullable=True, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (UniqueConstraint("organization_id", "slug", name="uq_org_deal_slug"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    company: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    sector: Mapped[str] = mapped_column(String(64), default="generic")
    status: Mapped[str] = mapped_column(String(32), default="not-started")
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    vdr_docs_json: Mapped[str] = mapped_column(Text, default="[]")
    docs_count: Mapped[int] = mapped_column(Integer, default=0)
    agents_running: Mapped[int] = mapped_column(Integer, default=0)
    reports_ready: Mapped[int] = mapped_column(Integer, default=0)
    vdr_bytes: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, server_default=func.now())

    organization: Mapped[Organization] = relationship(back_populates="deals")
    pipeline_runs: Mapped[list[PipelineAgentRun]] = relationship(back_populates="deal")


class PipelineAgentRun(Base):
    __tablename__ = "pipeline_agent_runs"
    __table_args__ = (
        UniqueConstraint("deal_id", "agent_key", name="uq_deal_agent"),
        Index("ix_pipeline_runs_deal_status", "deal_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id"), index=True)
    agent_key: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[str] = mapped_column(Text, default="{}")

    deal: Mapped[Deal] = relationship(back_populates="pipeline_runs")
