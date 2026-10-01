"use client";

import { Suspense, use } from "react";
import { DealWorkspace } from "@/components/deal/DealWorkspace";
import { ProtectedRoute } from "@/components/auth/RouteGuards";

export default function DealPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <ProtectedRoute>
      <Suspense fallback={<p className="p-6 text-[13px] text-text-secondary">Loading dealroom…</p>}>
        <DealWorkspace dealId={id} />
      </Suspense>
    </ProtectedRoute>
  );
}
