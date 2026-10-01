"use client";

import { AuthCard } from "@/components/auth/AuthCard";
import { AuthHeader } from "@/components/auth/AuthHeader";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { LoginForm } from "@/components/auth/LoginForm";
import { GuestRoute } from "@/components/auth/RouteGuards";

export default function LoginPage() {
  return (
    <GuestRoute>
      <AuthLayout>
        <AuthCard>
          <AuthHeader
            title="Sign in"
            subtitle="Sign in to your Agentic CDD account."
          />
          <LoginForm />
        </AuthCard>
      </AuthLayout>
    </GuestRoute>
  );
}
