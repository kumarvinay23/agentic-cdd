"use client";

import { Suspense, use, useCallback, useEffect, useState } from "react";
import { EvidenceCoverage } from "@/components/deal/EvidenceCoverage";
import { ProtectedRoute } from "@/components/auth/RouteGuards";
import { ApiError, vdrEvidenceAnalyzeRequest, vdrEvidenceGraphRequest } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import type { EvidenceAnalyzePayload } from "@/lib/evidence-types";

function CoverageBody({ dealId }: { dealId: string }) {
  const { tokens } = useAuth();
  const [payload, setPayload] = useState<EvidenceAnalyzePayload | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!tokens?.accessToken) return;
    setError(null);
    try {
      const graph = await vdrEvidenceGraphRequest(tokens.accessToken, dealId);
      setPayload(graph);
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setPayload(null);
        return;
      }
      setError(err instanceof ApiError ? err.message : "Failed to load evidence coverage");
    }
  }, [dealId, tokens?.accessToken]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onReanalyze() {
    if (!tokens?.accessToken) return;
    setAnalyzing(true);
    setError(null);
    try {
      const next = await vdrEvidenceAnalyzeRequest(tokens.accessToken, dealId);
      setPayload(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analyze failed");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <EvidenceCoverage
      dealId={dealId}
      payload={payload}
      analyzing={analyzing}
      error={error}
      onReanalyze={() => void onReanalyze()}
    />
  );
}

export default function CoveragePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  return (
    <ProtectedRoute>
      <Suspense fallback={<p className="p-6 text-[13px] text-text-secondary">Loading coverage…</p>}>
        <CoverageBody dealId={id} />
      </Suspense>
    </ProtectedRoute>
  );
}
