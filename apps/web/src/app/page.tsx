"use client";

import { PortfolioShell } from "@/components/portfolio/PortfolioShell";
import { ProtectedRoute } from "@/components/auth/RouteGuards";

export default function HomePage() {
  return (
    <ProtectedRoute>
      <PortfolioShell />
    </ProtectedRoute>
  );
}
