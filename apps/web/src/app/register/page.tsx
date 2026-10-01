"use client";

import { AuthCard } from "@/components/auth/AuthCard";
import { AuthHeader } from "@/components/auth/AuthHeader";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { RegisterForm } from "@/components/auth/RegisterForm";
import { GuestRoute } from "@/components/auth/RouteGuards";

export default function RegisterPage() {
  return (
    <GuestRoute>
      <AuthLayout>
        <AuthCard>
          <AuthHeader
            title="Create account"
            subtitle="Create your Agentic CDD workspace."
          />
          <RegisterForm />
        </AuthCard>
      </AuthLayout>
    </GuestRoute>
  );
}
