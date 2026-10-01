"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CreateDealModal } from "@/components/portfolio/CreateDealModal";
import { DealCard } from "@/components/portfolio/DealCard";
import {
  ApiError,
  createDealRequest,
  formatBytes,
  listDealsRequest,
  sectorsRequest,
  usageRequest,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { product } from "@/lib/config";
import type { Deal, PortfolioMetrics, SectorOption, UsageStats } from "@/lib/deal-types";

const emptyMetrics: PortfolioMetrics = {
  active_deals: 0,
  agents_running_now: 0,
  reports_ready: 0,
  total_deals: 0,
};

const emptyUsage: UsageStats = { agent_runs: 0, vdr_files: 0, vdr_bytes: 0 };

export function PortfolioShell() {
  const router = useRouter();
  const { user, tokens, logout } = useAuth();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [metrics, setMetrics] = useState<PortfolioMetrics>(emptyMetrics);
  const [usage, setUsage] = useState<UsageStats>(emptyUsage);
  const [sectors, setSectors] = useState<SectorOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const initials = (user?.full_name || user?.email || "?")
    .split(/\s+/)
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  const refresh = useCallback(async () => {
    if (!tokens?.accessToken) return;
    setError(null);
    setLoading(true);
    try {
      const [dealsRes, usageRes, sectorsRes] = await Promise.all([
        listDealsRequest(tokens.accessToken),
        usageRequest(tokens.accessToken),
        sectorsRequest(tokens.accessToken),
      ]);
      setDeals(dealsRes.data || []);
      setMetrics(dealsRes.metrics || emptyMetrics);
      setUsage(usageRes.data || emptyUsage);
      setSectors(sectorsRes || []);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  }, [tokens?.accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function handleCreate(input: {
    name: string;
    slug: string;
    description: string;
    tags: string;
    industry: string;
  }) {
    if (!tokens?.accessToken) throw new Error("Not authenticated");
    await createDealRequest(tokens.accessToken, input);
    await refresh();
  }

  return (
    <div className="flex min-h-screen flex-col bg-[#f3f4f6]">
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border-primary bg-white/95 px-3 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            aria-label="Toggle navigation"
            onClick={() => setSidebarOpen((v) => !v)}
            className="inline-grid h-[34px] w-[34px] place-items-center rounded-lg border border-border-primary text-text-secondary hover:bg-[#fafafa]"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 7h16M4 12h16M4 17h16" />
            </svg>
          </button>
          <div className="flex items-center gap-2">
            <span className="inline-grid h-7 w-7 place-items-center rounded-lg bg-[#1e3a5f] text-white">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M13 2 4.5 13.5h6L11 22l8.5-11.5h-6L13 2z" />
              </svg>
            </span>
            <span className="text-[15px] font-bold tracking-tight text-text-primary">{product.name}</span>
          </div>
          <span className="mx-1 h-[18px] w-px bg-border-secondary" />
          <span className="text-[13px] font-medium text-text-secondary">Portfolio</span>
        </div>
        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() => void logout()}
            className="text-[12px] text-text-secondary hover:text-text-primary"
          >
            Sign out
          </button>
          <div className="grid h-[34px] w-[34px] place-items-center rounded-full bg-[#e8edf3] text-[11px] font-semibold text-[#1e3a5f]">
            {initials}
          </div>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {sidebarOpen ? (
          <aside className="hidden w-[240px] shrink-0 border-r border-border-primary bg-[#f5f6f8] p-4 md:block">
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
              Global
            </p>
            <Link
              href="/"
              className="mb-2 flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-[13px] font-medium text-text-primary ring-1 ring-border-primary"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <rect x="3" y="3" width="7" height="7" rx="1.2" />
                <rect x="14" y="3" width="7" height="7" rx="1.2" />
                <rect x="3" y="14" width="7" height="7" rx="1.2" />
                <rect x="14" y="14" width="7" height="7" rx="1.2" />
              </svg>
              Portfolio
            </Link>
            <p className="mb-6 text-[11px] leading-relaxed text-text-secondary">
              Select a deal from the portfolio to open its workspace.
            </p>

            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
              Usage
            </p>
            <div className="space-y-2 text-[12px]">
              <div className="flex items-center gap-2">
                <span className="text-[#1e3a5f]">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                    <path d="M13 2 4.5 13.5h6L11 22l8.5-11.5h-6L13 2z" />
                  </svg>
                </span>
                <span className="flex-1 text-text-secondary">Agent runs</span>
                <span className="font-medium text-text-primary">{usage.agent_runs}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-text-secondary">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <ellipse cx="12" cy="6" rx="7" ry="3" />
                    <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" />
                    <path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" />
                  </svg>
                </span>
                <span className="flex-1 text-text-secondary">VDR files</span>
                <span className="font-medium text-text-primary">{usage.vdr_files}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-text-secondary">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M12 16V7" />
                    <path d="m8.5 10.5 3.5-3.5 3.5 3.5" />
                    <path d="M5 18h14" />
                  </svg>
                </span>
                <span className="flex-1 text-text-secondary">Uploaded</span>
                <span className="font-medium text-text-primary">{formatBytes(usage.vdr_bytes)}</span>
              </div>
            </div>
          </aside>
        ) : null}

        <main className="min-w-0 flex-1 p-5 md:p-7">
          <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
            <div>
              <h1 className="text-[22px] font-semibold tracking-tight text-text-primary">
                Portfolio dashboard
              </h1>
              <p className="mt-1 max-w-2xl text-[13px] text-text-secondary">
                Global view of investment portfolios, active VDR rooms, and intelligence execution metrics.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                aria-label="Refresh"
                onClick={() => void refresh()}
                className="inline-grid h-[34px] w-[34px] place-items-center rounded-lg border border-border-primary bg-white text-text-secondary hover:bg-[#fafafa]"
              >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M21 12a9 9 0 1 1-2.6-6.3" />
                  <path d="M21 4v5h-5" />
                </svg>
              </button>
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                className="inline-flex items-center gap-1.5 rounded-lg bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white hover:bg-[#16304f]"
              >
                <span>+</span> Create Dealroom
              </button>
            </div>
          </div>

          <section className="mb-6 grid gap-3 sm:grid-cols-3" aria-label="Portfolio metrics">
            {[
              ["Active deals", metrics.active_deals],
              ["Agents running now", metrics.agents_running_now],
              ["Reports ready", metrics.reports_ready],
            ].map(([label, value]) => (
              <article
                key={label as string}
                className="rounded-[10px] border border-border-primary bg-white px-4 py-3"
              >
                <p className="text-[12px] text-text-secondary">{label}</p>
                <p className="mt-1 text-[22px] font-semibold tracking-tight text-text-primary">
                  {value as number}
                </p>
              </article>
            ))}
          </section>

          {error ? (
            <p className="mb-4 text-[13px] text-text-danger">{error}</p>
          ) : null}

          {loading ? (
            <p className="text-[13px] text-text-secondary">Loading deals…</p>
          ) : deals.length === 0 ? (
            <div className="rounded-[10px] border border-dashed border-border-secondary bg-white px-6 py-12 text-center">
              <p className="text-[14px] font-medium text-text-primary">No dealrooms yet</p>
              <p className="mt-1 text-[13px] text-text-secondary">
                Create your first investment portfolio to begin diligence.
              </p>
              <button
                type="button"
                onClick={() => setModalOpen(true)}
                className="mt-4 rounded-lg bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white"
              >
                Create Dealroom
              </button>
            </div>
          ) : (
            <section className="grid gap-3" aria-label="Dealrooms">
              {deals.map((deal) => (
                <DealCard
                  key={deal.id}
                  deal={deal}
                  onOpen={(d) => router.push(`/deals/${d.id}`)}
                />
              ))}
            </section>
          )}
        </main>
      </div>

      <CreateDealModal
        open={modalOpen}
        sectors={sectors}
        onClose={() => setModalOpen(false)}
        onSubmit={handleCreate}
      />
    </div>
  );
}
