"use client";

import { useEffect, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { AUTH_ROUTES } from "@/lib/config";
import { useAuth } from "@/lib/auth-store";

export function GuestRoute({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { status, isHydrated } = useAuth();

  useEffect(() => {
    if (isHydrated && status === "authenticated") {
      router.replace(AUTH_ROUTES.DASHBOARD);
    }
  }, [isHydrated, status, router]);

  if (!isHydrated || status === "loading" || status === "idle") {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background-tertiary">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-border-secondary border-t-text-info" />
      </div>
    );
  }

  if (status === "authenticated") {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background-tertiary">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-border-secondary border-t-text-info" />
      </div>
    );
  }

  return <>{children}</>;
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { status, isHydrated } = useAuth();

  useEffect(() => {
    if (isHydrated && status === "unauthenticated") {
      router.replace(AUTH_ROUTES.LOGIN);
    }
  }, [isHydrated, status, router]);

  if (!isHydrated || status === "loading" || status === "idle") {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background-tertiary">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-border-secondary border-t-text-info" />
      </div>
    );
  }

  if (status !== "authenticated") {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background-tertiary">
        <div className="h-5 w-5 animate-spin rounded-full border-2 border-border-secondary border-t-text-info" />
      </div>
    );
  }

  return <>{children}</>;
}
