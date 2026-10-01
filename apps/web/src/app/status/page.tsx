import type { Metadata } from "next";
import { API_BASE_URL, ENDPOINTS, product } from "@/lib/config";

export const metadata: Metadata = {
  title: "Status",
};

type Health = {
  ok: boolean;
  service: string;
  version: string;
  product: string;
  wave: string;
};

async function loadHealth(): Promise<{ ok: boolean; data?: Health; error?: string }> {
  try {
    const res = await fetch(`${API_BASE_URL}${ENDPOINTS.HEALTH}`, {
      cache: "no-store",
    });
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` };
    }
    return { ok: true, data: (await res.json()) as Health };
  } catch (err) {
    return {
      ok: false,
      error: err instanceof Error ? err.message : "Unreachable",
    };
  }
}

export default async function StatusPage() {
  const health = await loadHealth();

  return (
    <main className="mx-auto flex min-h-screen max-w-lg flex-col justify-center gap-4 px-4">
      <h1 className="text-[20px] font-semibold text-text-primary">
        {product.name} · W0 status
      </h1>
      <div className="rounded-[var(--radius-lg)] border border-border-primary bg-background-secondary p-5 text-[13px]">
        <p className="text-text-secondary">API base</p>
        <p className="font-mono text-text-primary">{API_BASE_URL}</p>
        <p className="mt-4 text-text-secondary">Health</p>
        {health.ok && health.data ? (
          <pre className="mt-1 overflow-auto rounded-md bg-background-tertiary p-3 text-[12px]">
            {JSON.stringify(health.data, null, 2)}
          </pre>
        ) : (
          <p className="mt-1 text-text-danger">
            Unreachable — start the API on :4600. {health.error}
          </p>
        )}
      </div>
      <a href="/login" className="text-[13px] text-text-info hover:underline">
        Open sign in
      </a>
    </main>
  );
}
