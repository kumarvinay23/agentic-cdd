"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { AuthPayload, AuthTokens } from "./auth-types";
import { logoutRequest, meRequest } from "./api";

const STORAGE_KEY = "agetic_cdd_auth_v1";

type AuthStatus = "idle" | "loading" | "authenticated" | "unauthenticated";

type StoredAuth = {
  user: AuthPayload["user"];
  organization: AuthPayload["organization"];
  member: AuthPayload["member"];
  permissions: string[];
  roles: string[];
  tokens: AuthTokens;
};

type AuthContextValue = {
  status: AuthStatus;
  isHydrated: boolean;
  user: StoredAuth["user"] | null;
  organization: StoredAuth["organization"] | null;
  member: StoredAuth["member"] | null;
  permissions: string[];
  tokens: AuthTokens | null;
  setAuth: (payload: AuthPayload) => void;
  clearAuth: () => void;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function readStore(): StoredAuth | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as StoredAuth;
  } catch {
    return null;
  }
}

function writeStore(value: StoredAuth | null) {
  if (typeof window === "undefined") return;
  if (!value) localStorage.removeItem(STORAGE_KEY);
  else localStorage.setItem(STORAGE_KEY, JSON.stringify(value));
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("idle");
  const [isHydrated, setHydrated] = useState(false);
  const [session, setSession] = useState<StoredAuth | null>(null);

  useEffect(() => {
    const stored = readStore();
    if (!stored?.tokens?.accessToken) {
      setSession(null);
      setStatus("unauthenticated");
      setHydrated(true);
      return;
    }
    setSession(stored);
    setStatus("loading");
    meRequest(stored.tokens.accessToken)
      .then((res) => {
        const next: StoredAuth = {
          user: res.data.user,
          organization: res.data.organization,
          member: res.data.member,
          permissions: res.data.permissions,
          roles: res.data.roles || res.data.member.roles || [],
          tokens: stored.tokens,
        };
        writeStore(next);
        setSession(next);
        setStatus("authenticated");
      })
      .catch(() => {
        writeStore(null);
        setSession(null);
        setStatus("unauthenticated");
      })
      .finally(() => setHydrated(true));
  }, []);

  const setAuth = useCallback((payload: AuthPayload) => {
    if (!payload.tokens) return;
    const next: StoredAuth = {
      user: payload.user,
      organization: payload.organization,
      member: payload.member,
      permissions: payload.permissions,
      roles: payload.roles || payload.member.roles || [],
      tokens: payload.tokens,
    };
    writeStore(next);
    setSession(next);
    setStatus("authenticated");
  }, []);

  const clearAuth = useCallback(() => {
    writeStore(null);
    setSession(null);
    setStatus("unauthenticated");
  }, []);

  const logout = useCallback(async () => {
    try {
      if (session?.tokens) {
        await logoutRequest(session.tokens.accessToken, session.tokens.refreshToken);
      }
    } catch {
      // ignore network errors on logout
    } finally {
      clearAuth();
    }
  }, [clearAuth, session]);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      isHydrated,
      user: session?.user ?? null,
      organization: session?.organization ?? null,
      member: session?.member ?? null,
      permissions: session?.permissions ?? [],
      tokens: session?.tokens ?? null,
      setAuth,
      clearAuth,
      logout,
    }),
    [status, isHydrated, session, setAuth, clearAuth, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
