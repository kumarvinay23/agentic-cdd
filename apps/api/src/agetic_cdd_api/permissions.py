"""Role → permission mapping (DiligenceIQ-compatible strings)."""

from __future__ import annotations

ALL_PERMISSIONS = [
    "organization.read",
    "organization.update",
    "members.read",
    "members.invite",
    "members.update",
    "members.delete",
    "billing.read",
    "billing.update",
    "portfolio.read",
    "portfolio.create",
    "portfolio.update",
    "portfolio.delete",
    "deals.read",
    "deals.create",
    "deals.update",
    "deals.delete",
    "pipeline.read",
    "pipeline.run",
    "pipeline.update",
    "reports.read",
    "reports.export",
    "audit.read",
]

ROLE_PERMISSIONS: dict[str, list[str]] = {
    "owner": list(ALL_PERMISSIONS),
    "admin": list(ALL_PERMISSIONS),
    "user": [
        "organization.read",
        "members.read",
        "billing.read",
        "portfolio.read",
        "portfolio.create",
        "portfolio.update",
        "deals.read",
        "deals.create",
        "deals.update",
        "pipeline.read",
        "pipeline.run",
        "reports.read",
        "reports.export",
    ],
}


def permissions_for_role(role: str) -> list[str]:
    return list(ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["user"]))


def roles_for_member(role: str) -> list[str]:
    if role == "owner":
        return ["admin", "owner", "user"]
    if role == "admin":
        return ["admin", "user"]
    return ["user"]
