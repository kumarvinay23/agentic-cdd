export type AuthUser = {
  email: string;
  firstName: string;
  lastName: string;
  full_name: string;
  profile_image: string | null;
};

export type AuthOrganization = {
  id: string;
  _id?: string;
  name: string;
  slug: string;
};

export type AuthMember = {
  id: string;
  uuid: string;
  email: string;
  firstName: string;
  lastName: string;
  name: string;
  role: string;
  roles: string[];
  permissions: string[];
  access: string;
  lastActive?: string | null;
};

export type AuthTokens = {
  accessToken: string;
  refreshToken: string;
};

export type AuthPayload = {
  user: AuthUser;
  organization: AuthOrganization;
  member: AuthMember;
  permissions: string[];
  roles?: string[];
  tokens?: AuthTokens;
};

export type ApiSuccess<T> = {
  success: boolean;
  data: T;
};
