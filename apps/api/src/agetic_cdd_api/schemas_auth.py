"""Pydantic schemas for auth."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)
    organizationId: str | None = None
    organization_id: str | None = None

    def resolved_organization_id(self) -> str | None:
        return self.organizationId or self.organization_id


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    firstName: str = Field(default="", max_length=120)
    lastName: str = Field(default="", max_length=120)
    organizationName: str = Field(default="", max_length=255)


class RefreshRequest(BaseModel):
    refresh_token: str | None = None
    refreshToken: str | None = None

    def token_value(self) -> str | None:
        return self.refresh_token or self.refreshToken


class UserOut(BaseModel):
    email: EmailStr
    firstName: str
    lastName: str
    full_name: str
    profile_image: str | None = None


class OrganizationOut(BaseModel):
    model_config = {"extra": "allow"}

    id: str
    name: str
    slug: str

    def model_dump(self, **kwargs):  # type: ignore[override]
        data = super().model_dump(**kwargs)
        data["_id"] = self.id
        return data


class MemberOut(BaseModel):
    id: str
    uuid: str
    email: EmailStr
    firstName: str
    lastName: str
    name: str
    role: str
    roles: list[str]
    permissions: list[str]
    access: str
    lastActive: str | None = None


class TokensOut(BaseModel):
    accessToken: str
    refreshToken: str


class AuthData(BaseModel):
    user: UserOut
    organization: OrganizationOut
    member: MemberOut
    permissions: list[str]
    tokens: TokensOut | None = None
    roles: list[str] | None = None


class ApiSuccess(BaseModel):
    success: bool = True
    data: AuthData
