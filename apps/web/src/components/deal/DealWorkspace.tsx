"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { DealDatabook } from "@/components/deal/DealDatabook";
import { DataQualityReview } from "@/components/deal/DataQualityReview";
import { DealDocumentWorkspace } from "@/components/deal/DealDocumentWorkspace";
import { DealReports } from "@/components/deal/DealReports";
import { DealWorkflow } from "@/components/deal/DealWorkflow";
import {
  ApiError,
  databookAcceptConflictRequest,
  databookRescanRequest,
  dataQualityRequest,
  dealDashboardRequest,
  formatBytes,
  type DashboardPayload,
  type DataQualityCandidate,
  type DataQualityItem,
  type DataQualityPayload,
  type IngestionStatus,
  usageRequest,
  type VdrDoc,
  vdrDeleteRequest,
  vdrDownloadRequest,
  vdrEvidenceAnalyzeRequest,
  vdrListRequest,
  vdrSyncRequest,
  vdrUploadRequest,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { product } from "@/lib/config";
import type { UsageStats } from "@/lib/deal-types";

type DealView = "dashboard" | "vdr" | "workflow" | "documents" | "reports" | "databook";
type VdrCategory = "All" | "General" | "Financial" | "Legal" | "Technical";

const emptyUsage: UsageStats = { agent_runs: 0, vdr_files: 0, vdr_bytes: 0 };
const emptyIngestion: IngestionStatus = {
  running: false,
  completed: false,
  processed_chunks: 0,
};

const DEAL_NAV: Array<
  | { id: DealView; label: string; icon: string; disabled?: false }
  | { id: string; label: string; icon: string; disabled: true }
> = [
  { id: "dashboard", label: "Deal dashboard", icon: "grid" },
  { id: "vdr", label: "Deal room (VDR)", icon: "folder" },
  { id: "workflow", label: "Workflow", icon: "flow" },
  { id: "documents", label: "Document workspace", icon: "doc" },
  { id: "reports", label: "Reports", icon: "doc" },
  { id: "databook", label: "Databook", icon: "chart" },
  { id: "chat", label: "Deal chat", icon: "chat", disabled: true },
  { id: "team", label: "Team & access", icon: "users", disabled: true },
  { id: "config", label: "Deal config", icon: "gear", disabled: true },
];

function formatDocDate(iso?: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  return date.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function statusLabel(status?: string): { label: string; tone: "ready" | "progress" | "error" | "neutral" } {
  switch (status) {
    case "ready":
      return { label: "Ready", tone: "ready" };
    case "parsing":
    case "classified":
      return { label: "Processing", tone: "progress" };
    case "error":
      return { label: "Error", tone: "error" };
    case "uploaded":
      return { label: "Uploaded", tone: "neutral" };
    default:
      return { label: "Pending", tone: "neutral" };
  }
}

function statusClasses(tone: ReturnType<typeof statusLabel>["tone"]): string {
  if (tone === "ready") return "bg-[#ecfdf3] text-[#15803d]";
  if (tone === "progress") return "bg-[#eff6ff] text-[#1d4ed8]";
  if (tone === "error") return "bg-[#fef2f2] text-[#dc2626]";
  return "bg-[#eef0f3] text-[#4b5563]";
}

function NavIcon({ name }: { name: string }) {
  const props = { viewBox: "0 0 24 24", width: 16, height: 16, fill: "none", stroke: "currentColor", strokeWidth: 1.8 };
  switch (name) {
    case "grid":
      return (
        <svg {...props}>
          <rect x="3" y="3" width="7" height="7" rx="1.2" />
          <rect x="14" y="3" width="7" height="7" rx="1.2" />
          <rect x="3" y="14" width="7" height="7" rx="1.2" />
          <rect x="14" y="14" width="7" height="7" rx="1.2" />
        </svg>
      );
    case "folder":
      return (
        <svg {...props}>
          <path d="M3 7h6l2 2h10v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />
        </svg>
      );
    case "flow":
      return (
        <svg {...props}>
          <circle cx="6" cy="6" r="2.5" />
          <circle cx="18" cy="12" r="2.5" />
          <circle cx="6" cy="18" r="2.5" />
          <path d="M8.5 7.5 15.5 10.5M8.5 16.5 15.5 13.5" />
        </svg>
      );
    case "doc":
      return (
        <svg {...props}>
          <path d="M8 3h8l4 4v14H8V3z" />
          <path d="M16 3v5h5" />
        </svg>
      );
    case "chart":
      return (
        <svg {...props}>
          <path d="M4 19V5" />
          <path d="M4 19h16" />
          <path d="M8 15v-4M12 15V8M16 15v-6" />
        </svg>
      );
    case "chat":
      return (
        <svg {...props}>
          <path d="M4 5h16v10H8l-4 4V5z" />
        </svg>
      );
    case "users":
      return (
        <svg {...props}>
          <circle cx="9" cy="8" r="3" />
          <circle cx="17" cy="9" r="2.5" />
          <path d="M3 19c0-3 3-5 6-5s6 2 6 5" />
          <path d="M15 19c0-2 1.5-3.5 3.5-3.5" />
        </svg>
      );
    default:
      return (
        <svg {...props}>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      );
  }
}

function PdfIcon() {
  return (
    <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
      <rect x="4" y="2" width="14" height="18" rx="1.5" fill="#fee2e2" stroke="#fca5a5" />
      <text x="7" y="14" fontSize="6" fontWeight="700" fill="#dc2626">
        PDF
      </text>
    </svg>
  );
}

export function DealWorkspace({ dealId }: { dealId: string }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { tokens, logout, user } = useAuth();
  const initialView =
    searchParams.get("view") === "vdr"
      ? "vdr"
      : searchParams.get("view") === "workflow"
        ? "workflow"
        : searchParams.get("view") === "documents"
          ? "documents"
          : searchParams.get("view") === "reports"
            ? "reports"
            : searchParams.get("view") === "databook"
              ? "databook"
              : "dashboard";
  const [view, setView] = useState<DealView>(initialView);
  const [agentKey, setAgentKey] = useState<string | null>(
    searchParams.get("agent")?.trim() || null,
  );
  const [data, setData] = useState<DashboardPayload | null>(null);
  const [docs, setDocs] = useState<VdrDoc[]>([]);
  const [ingestion, setIngestion] = useState<IngestionStatus>(emptyIngestion);
  const [usage, setUsage] = useState<UsageStats>(emptyUsage);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [category, setCategory] = useState<VdrCategory>("All");
  const [search, setSearch] = useState("");
  const [quality, setQuality] = useState<DataQualityPayload | null>(null);
  const [qualityBusy, setQualityBusy] = useState(false);
  const [qualityLoading, setQualityLoading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

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
      const [dash, vdr, usageRes] = await Promise.all([
        dealDashboardRequest(tokens.accessToken, dealId),
        vdrListRequest(tokens.accessToken, dealId),
        usageRequest(tokens.accessToken),
      ]);
      setData(dash.data);
      setDocs(vdr.data || []);
      setIngestion(vdr.ingestion || emptyIngestion);
      setUsage(usageRes.data || emptyUsage);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load deal");
    } finally {
      setLoading(false);
    }
  }, [dealId, tokens?.accessToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const refreshQuality = useCallback(async () => {
    if (!tokens?.accessToken) return;
    setQualityLoading(true);
    try {
      const dq = await dataQualityRequest(tokens.accessToken, dealId);
      setQuality(dq);
    } catch {
      setQuality(null);
    } finally {
      setQualityLoading(false);
    }
  }, [dealId, tokens?.accessToken]);

  useEffect(() => {
    if (view === "vdr") void refreshQuality();
  }, [view, refreshQuality]);

  const onDatabookRescanFromVdr = async () => {
    if (!tokens?.accessToken) return;
    setQualityBusy(true);
    setError(null);
    try {
      await databookRescanRequest(tokens.accessToken, dealId);
      await refreshQuality();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Databook Rescan failed");
    } finally {
      setQualityBusy(false);
    }
  };

  const onAcceptQualityConflict = async (
    item: Extract<DataQualityItem, { kind: "conflict" }>,
    cand?: DataQualityCandidate,
  ) => {
    if (!tokens?.accessToken) return;
    const chosen = cand || (item.candidates || []).find((c) => c.chosen) || item.candidates?.[0];
    if (!chosen || item.fiscal_year == null) {
      setError("Pick a candidate value to accept.");
      return;
    }
    setQualityBusy(true);
    setError(null);
    try {
      await databookAcceptConflictRequest(tokens.accessToken, dealId, {
        reason: "Accepted from VDR Data quality review",
        metric_key: item.metric,
        fiscal_year: item.fiscal_year,
        value: chosen.value,
        row_id: chosen.row_ids?.[0],
      });
      await refreshQuality();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Accept failed");
    } finally {
      setQualityBusy(false);
    }
  };

  useEffect(() => {
    const params = new URLSearchParams();
    if (view !== "dashboard") params.set("view", view);
    if (agentKey && view === "documents") params.set("agent", agentKey);
    const qs = params.toString();
    const next = qs ? `?${qs}` : "?";
    const current = searchParams.toString() ? `?${searchParams.toString()}` : "?";
    if (next !== current) {
      router.replace(next, { scroll: false });
    }
  }, [view, agentKey, router, searchParams]);

  const refreshVdr = useCallback(async () => {
    if (!tokens?.accessToken) return;
    try {
      const vdr = await vdrListRequest(tokens.accessToken, dealId);
      setDocs(vdr.data || []);
      setIngestion(vdr.ingestion || emptyIngestion);
    } catch {
      /* polling should not surface transient errors */
    }
  }, [dealId, tokens?.accessToken]);

  useEffect(() => {
    if (!ingestion.running || !tokens?.accessToken) return;
    const timer = window.setInterval(() => {
      void refreshVdr();
    }, 1500);
    return () => window.clearInterval(timer);
  }, [ingestion.running, refreshVdr, tokens?.accessToken]);

  useEffect(() => {
    if (!ingestion.running && ingestion.completed) {
      void refresh();
    }
  }, [ingestion.completed, ingestion.running, refresh]);

  async function onSync() {
    if (!tokens?.accessToken) return;
    setSyncing(true);
    setError(null);
    try {
      await vdrSyncRequest(tokens.accessToken, dealId);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function onUpload(files: FileList | null) {
    if (!files?.length || !tokens?.accessToken) return;
    setUploading(true);
    setError(null);
    try {
      for (const file of Array.from(files)) {
        await vdrUploadRequest(tokens.accessToken, dealId, file);
      }
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onAnalyze() {
    if (!tokens?.accessToken || docs.length === 0) return;
    setAnalyzing(true);
    setError(null);
    try {
      await vdrEvidenceAnalyzeRequest(tokens.accessToken, dealId);
      router.push(`/deals/${dealId}/coverage`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Analyze failed");
      setAnalyzing(false);
    }
  }

  async function onDownload(filename: string) {
    if (!tokens?.accessToken) return;
    setError(null);
    try {
      await vdrDownloadRequest(tokens.accessToken, dealId, filename);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Download failed");
    }
  }

  async function onDelete(filename: string) {
    if (!tokens?.accessToken) return;
    if (!window.confirm(`Remove ${filename} from the data room?`)) return;
    try {
      await vdrDeleteRequest(tokens.accessToken, dealId, filename);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Delete failed");
    }
  }

  const room = data?.dealRoom;
  const completion = data?.workflowCompletion;
  const dataRoom = data?.dataRoomStatus;
  const dealName = room?.name || "Dealroom";

  const docsWithMeta = useMemo(
    () =>
      docs.map((doc) => ({
        ...doc,
        category: (doc.category || "General") as Exclude<VdrCategory, "All">,
      })),
    [docs],
  );

  const readyCount = docs.filter((d) => d.status === "ready").length;

  const categoryCounts = useMemo(() => {
    const counts: Record<Exclude<VdrCategory, "All">, number> = {
      General: 0,
      Financial: 0,
      Legal: 0,
      Technical: 0,
    };
    for (const doc of docsWithMeta) counts[doc.category] += 1;
    return counts;
  }, [docsWithMeta]);

  const filteredDocs = useMemo(() => {
    const q = search.trim().toLowerCase();
    return docsWithMeta.filter((doc) => {
      if (category !== "All" && doc.category !== category) return false;
      if (q && !doc.filename.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [category, docsWithMeta, search]);

  const totalBytes = docs.reduce((sum, d) => sum + (d.size || 0), 0) || dataRoom?.totalSizeBytes || 0;

  return (
    <div className="flex min-h-screen flex-col bg-[#f3f4f6]">
      <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-border-primary bg-white/95 px-3 backdrop-blur">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-2">
            <span className="inline-grid h-7 w-7 place-items-center rounded-lg bg-[#1e3a5f] text-white">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M13 2 4.5 13.5h6L11 22l8.5-11.5h-6L13 2z" />
              </svg>
            </span>
            <span className="text-[15px] font-bold tracking-tight text-text-primary">{product.name}</span>
          </div>
          <span className="mx-1 h-[18px] w-px bg-border-secondary" />
          <Link href="/" className="text-[13px] font-medium text-text-secondary hover:text-text-primary">
            Portfolio
          </Link>
          <span className="text-text-secondary">/</span>
          <span className="truncate text-[13px] font-medium text-text-primary">{dealName}</span>
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
        <aside className="hidden w-[240px] shrink-0 border-r border-border-primary bg-[#f5f6f8] p-4 md:block">
          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Global</p>
          <Link
            href="/"
            className="mb-5 flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] font-medium text-text-secondary hover:bg-white hover:text-text-primary"
          >
            <NavIcon name="grid" />
            Portfolio
          </Link>

          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Deal</p>
          <div className="mb-2 flex items-center gap-2 px-3 py-1.5 text-[13px] font-semibold text-text-primary">
            <NavIcon name="folder" />
            <span className="truncate">{dealName}</span>
          </div>
          <nav className="mb-6 space-y-0.5">
            {DEAL_NAV.map((item) => {
              const active = !item.disabled && item.id === view;
              if (item.disabled) {
                return (
                  <div
                    key={item.label}
                    className="flex cursor-not-allowed items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-[#9ca3af]"
                    title="Coming soon"
                  >
                    <NavIcon name={item.icon} />
                    {item.label}
                  </div>
                );
              }
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    if (item.id !== "documents") setAgentKey(null);
                    setView(item.id);
                  }}
                  className={`flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-[13px] ${
                    active
                      ? "bg-white font-medium text-text-primary ring-1 ring-border-primary"
                      : "text-text-secondary hover:bg-white/70 hover:text-text-primary"
                  }`}
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </button>
              );
            })}
          </nav>

          <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">Usage</p>
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

        <main className="min-w-0 flex-1 p-5 md:p-7">
          {error ? <p className="mb-4 text-[13px] text-text-danger">{error}</p> : null}
          {loading && !data ? (
            <p className="text-[13px] text-text-secondary">Loading dealroom…</p>
          ) : null}

          {view === "dashboard" && data ? (
            <div className="space-y-6">
              <div>
                <h1 className="text-[22px] font-semibold tracking-tight text-text-primary">Deal dashboard</h1>
                <p className="mt-1 text-[13px] text-text-secondary">Pipeline and workflow for {dealName}</p>
              </div>
              <section className="grid gap-3 sm:grid-cols-3">
                <article className="rounded-[10px] border border-border-primary bg-white px-4 py-3">
                  <p className="text-[12px] text-text-secondary">Pipeline completion</p>
                  <p className="mt-1 text-[22px] font-semibold text-text-primary">
                    {completion?.completionPercentage ?? 0}%
                  </p>
                  <p className="text-[11px] text-text-secondary">
                    {completion?.completedAgents ?? 0} / {completion?.totalAgents ?? 43} agents
                  </p>
                </article>
                <article className="rounded-[10px] border border-border-primary bg-white px-4 py-3">
                  <p className="text-[12px] text-text-secondary">Data room</p>
                  <p className="mt-1 text-[22px] font-semibold text-text-primary">
                    {dataRoom?.totalDocuments ?? 0}
                  </p>
                  <p className="text-[11px] text-text-secondary">{formatBytes(dataRoom?.totalSizeBytes || 0)} uploaded</p>
                </article>
                <article className="rounded-[10px] border border-border-primary bg-white px-4 py-3">
                  <p className="text-[12px] text-text-secondary">Status</p>
                  <p className="mt-1 text-[16px] font-semibold uppercase tracking-wide text-text-primary">
                    {(room?.status || "not-started").replace(/-/g, " ")}
                  </p>
                  <p className="text-[11px] text-text-secondary">Sector: {room?.sector || data.deal.sector}</p>
                </article>
              </section>

              <section>
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-[15px] font-semibold text-text-primary">Workflow roadmap</h2>
                  <p className="text-[11px] text-text-secondary">Run phases from the Workflow tab</p>
                </div>
                <div className="space-y-3">
                  {data.workflowRoadmap.map((phase) => (
                    <details
                      key={phase.phaseUuid}
                      className="rounded-[10px] border border-border-primary bg-white"
                      open={phase.order <= 2}
                    >
                      <summary className="cursor-pointer list-none px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-[13px] font-semibold text-text-primary">
                              Phase {phase.order}: {phase.phaseName}
                            </p>
                            <p className="text-[11px] text-text-secondary">
                              {phase.completedAgents}/{phase.totalAgents} agents · {phase.status}
                            </p>
                          </div>
                          <span className="rounded-full bg-[#eef0f3] px-2 py-0.5 text-[10px] font-semibold uppercase text-[#4b5563]">
                            {phase.status}
                          </span>
                        </div>
                      </summary>
                      <div className="space-y-4 border-t border-border-primary px-4 py-3">
                        {phase.stages.map((stage) => (
                          <div key={stage.stageKey}>
                            <p className="text-[12px] font-medium text-text-primary">{stage.stageTitle}</p>
                            {stage.description ? (
                              <p className="mt-0.5 text-[11px] text-text-secondary">{stage.description}</p>
                            ) : null}
                            <ul className="mt-2 space-y-1.5">
                              {stage.agents.map((agent) => (
                                <li
                                  key={agent.agent_key}
                                  className="flex items-start justify-between gap-2 rounded-md bg-[#f8f9fb] px-2.5 py-2"
                                >
                                  <div>
                                    <p className="text-[12px] font-medium text-text-primary">{agent.agentName}</p>
                                    {agent.description ? (
                                      <p className="text-[11px] text-text-secondary">{agent.description}</p>
                                    ) : null}
                                  </div>
                                  <span className="shrink-0 text-[10px] font-semibold uppercase text-text-secondary">
                                    {agent.status}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </div>
                        ))}
                      </div>
                    </details>
                  ))}
                </div>
              </section>
            </div>
          ) : null}

          {view === "vdr" ? (
            <div className="space-y-5">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h1 className="text-[22px] font-semibold tracking-tight text-text-primary">Virtual Data Room</h1>
                  <p className="mt-1 text-[13px] text-text-secondary">
                    Documents scoped to <span className="font-medium text-text-primary">{dealName}</span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-label="Refresh"
                    disabled={syncing}
                    onClick={() => void onSync()}
                    className="inline-grid h-[34px] w-[34px] place-items-center rounded-lg border border-border-primary bg-white text-text-secondary hover:bg-[#fafafa] disabled:opacity-60"
                  >
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M21 12a9 9 0 1 1-2.6-6.3" />
                      <path d="M21 4v5h-5" />
                    </svg>
                  </button>
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(e) => void onUpload(e.target.files)}
                  />
                  <button
                    type="button"
                    disabled={uploading}
                    onClick={() => fileRef.current?.click()}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white hover:bg-[#16304f] disabled:opacity-60"
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 16V8" />
                      <path d="m8.5 11.5 3.5-3.5 3.5 3.5" />
                      <path d="M5 20h14" />
                    </svg>
                    {uploading ? "Uploading…" : "Upload documents"}
                  </button>
                  <button
                    type="button"
                    disabled={analyzing || docs.length === 0}
                    onClick={() => void onAnalyze()}
                    className="inline-flex items-center gap-1.5 rounded-lg border border-border-primary bg-white px-3 py-2 text-[13px] font-medium text-text-primary hover:bg-[#fafafa] disabled:opacity-60"
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5L12 3z" />
                      <path d="M5 19h14" />
                    </svg>
                    {analyzing ? "Analyzing…" : "Analyze documents"}
                  </button>
                  <Link
                    href={`/deals/${dealId}/coverage`}
                    className="inline-flex items-center rounded-lg px-3 py-2 text-[13px] font-medium text-text-secondary hover:bg-[#fafafa] hover:text-text-primary"
                  >
                    Evidence coverage
                  </Link>
                </div>
              </div>

              <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-label="VDR metrics">
                {[
                  ["Active repository", dealName],
                  ["Live documents", String(docs.length)],
                  ["Storage consumed", formatBytes(totalBytes)],
                  ["Processed chunks", `${ingestion.processed_chunks} indexed chunks`],
                ].map(([label, value]) => (
                  <article
                    key={label}
                    className="rounded-[10px] border border-border-primary bg-white px-4 py-3 shadow-[0_1px_2px_rgba(0,0,0,0.04)]"
                  >
                    <p className="text-[10px] font-semibold uppercase tracking-[0.06em] text-text-secondary">
                      {label}
                    </p>
                    <p className="mt-1 truncate text-[18px] font-semibold tracking-tight text-text-primary">{value}</p>
                  </article>
                ))}
              </section>

              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-[12px] text-text-secondary">
                    {qualityLoading
                      ? "Loading data-quality…"
                      : quality
                        ? `${quality.summary.needs_review} issue(s) need review`
                        : "Data-quality not loaded yet"}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      disabled={qualityBusy || !tokens?.accessToken}
                      onClick={() => void onDatabookRescanFromVdr()}
                      className="rounded-lg border border-border-primary bg-white px-3 py-1.5 text-[12px] font-medium text-text-primary hover:bg-[#fafafa] disabled:opacity-60"
                    >
                      {qualityBusy ? "Rescanning…" : "Rescan Databook"}
                    </button>
                    <button
                      type="button"
                      onClick={() => setView("databook")}
                      className="rounded-lg border border-border-primary bg-white px-3 py-1.5 text-[12px] font-medium text-[#1e3a5f] hover:bg-[#f8fafc]"
                    >
                      Open Databook
                    </button>
                  </div>
                </div>
                <DataQualityReview
                  quality={quality}
                  busy={qualityBusy}
                  onAcceptConflict={(item, cand) => void onAcceptQualityConflict(item, cand)}
                  showActions
                />
              </div>

              <section className="rounded-[10px] border border-border-primary bg-white px-4 py-3">
                <div className="mb-3 flex items-center gap-2 text-[13px] font-medium text-text-primary">
                  <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                    <path d="M4 6h16M7 12h10M10 18h4" />
                  </svg>
                  Filter by Category
                </div>
                <div className="flex flex-wrap gap-2">
                  {(["All", "General", "Financial", "Legal", "Technical"] as VdrCategory[]).map((cat) => {
                    const count = cat === "All" ? docs.length : categoryCounts[cat];
                    const active = category === cat;
                    return (
                      <button
                        key={cat}
                        type="button"
                        onClick={() => setCategory(cat)}
                        className={`rounded-full px-3 py-1.5 text-[12px] font-medium ${
                          active
                            ? "bg-[#1e3a5f] text-white"
                            : "bg-[#eef0f3] text-text-primary hover:bg-[#e5e7eb]"
                        }`}
                      >
                        {cat}: {count}
                      </button>
                    );
                  })}
                </div>
              </section>

              <section className="overflow-hidden rounded-[10px] border border-border-primary bg-white">
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-primary px-4 py-3">
                  <p className="text-[13px] font-medium text-text-primary">
                    {readyCount} resolved document{readyCount === 1 ? "" : "s"}
                  </p>
                  <div className="flex items-center gap-2">
                    <label className="relative">
                      <span className="sr-only">Search file name</span>
                      <input
                        type="search"
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        placeholder="Search file name..."
                        className="h-[34px] w-[220px] rounded-lg border border-border-primary bg-[#fafafa] pl-9 pr-3 text-[12px] text-text-primary outline-none focus:border-[#1e3a5f]"
                      />
                      <svg
                        className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-text-secondary"
                        viewBox="0 0 24 24"
                        width="14"
                        height="14"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                      >
                        <circle cx="11" cy="11" r="7" />
                        <path d="M20 20l-3-3" />
                      </svg>
                    </label>
                    <button
                      type="button"
                      aria-label="Filter options"
                      className="inline-grid h-[34px] w-[34px] place-items-center rounded-lg border border-border-primary text-text-secondary hover:bg-[#fafafa]"
                    >
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <path d="M4 6h16M7 12h10M10 18h4" />
                      </svg>
                    </button>
                  </div>
                </div>

                {filteredDocs.length === 0 ? (
                  <div className="px-6 py-14 text-center">
                    <p className="text-[14px] font-medium text-text-primary">No documents yet</p>
                    <p className="mt-1 text-[13px] text-text-secondary">
                      Upload CIM, financials, and market packs into this data room.
                    </p>
                    <button
                      type="button"
                      onClick={() => fileRef.current?.click()}
                      className="mt-4 rounded-lg bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white"
                    >
                      Upload documents
                    </button>
                  </div>
                ) : (
                  <ul className="divide-y divide-border-primary">
                    {filteredDocs.map((doc) => {
                      const status = statusLabel(doc.status);
                      return (
                      <li
                        key={doc.filename}
                        className="flex flex-wrap items-center gap-3 px-4 py-3 hover:bg-[#fafafa]"
                      >
                        <div className="flex min-w-0 flex-1 items-center gap-3">
                          <PdfIcon />
                          <div className="min-w-0">
                            <p className="truncate text-[13px] font-semibold text-text-primary">
                              {doc.name}{" "}
                              <span className="font-normal text-text-secondary">({formatBytes(doc.size || 0)})</span>
                            </p>
                          </div>
                        </div>
                        <span className="rounded border border-border-primary bg-[#f8f9fb] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#4b5563]">
                          {doc.category}
                        </span>
                        <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${statusClasses(status.tone)}`}>
                          {status.tone === "ready" ? (
                            <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5">
                              <path d="M5 12l4 4 10-10" />
                            </svg>
                          ) : null}
                          {status.label}
                        </span>
                        <span className="w-[88px] text-[12px] text-text-secondary">
                          {formatDocDate(doc.classified_at || doc.uploaded_at)}
                        </span>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            aria-label={`View ${doc.filename}`}
                            className="inline-grid h-8 w-8 place-items-center rounded-md text-text-secondary hover:bg-[#eef0f3] hover:text-text-primary"
                            title="Preview coming soon"
                          >
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                              <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
                              <circle cx="12" cy="12" r="3" />
                            </svg>
                          </button>
                          <button
                            type="button"
                            aria-label={`Download ${doc.filename}`}
                            onClick={() => void onDownload(doc.filename)}
                            className="inline-grid h-8 w-8 place-items-center rounded-md text-text-secondary hover:bg-[#eef0f3] hover:text-text-primary"
                            title="Download"
                          >
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                              <path d="M12 16V8" />
                              <path d="m8.5 11.5 3.5 3.5 3.5-3.5" />
                              <path d="M5 20h14" />
                            </svg>
                          </button>
                          <button
                            type="button"
                            aria-label={`Remove ${doc.filename}`}
                            onClick={() => void onDelete(doc.filename)}
                            className="inline-grid h-8 w-8 place-items-center rounded-md text-text-danger hover:bg-[#fef2f2]"
                            title="Remove"
                          >
                            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                              <path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14" />
                            </svg>
                          </button>
                        </div>
                      </li>
                    );
                    })}
                  </ul>
                )}
              </section>
            </div>
          ) : null}

          {view === "workflow" ? (
            <DealWorkflow
              dealId={dealId}
              accessToken={tokens?.accessToken}
              onError={setError}
              onOpenDocuments={() => {
                setAgentKey(null);
                setView("documents");
              }}
              onOpenAgentDocument={(key) => {
                setAgentKey(key);
                setView("documents");
                // Push URL immediately so soft-nav / remounts keep agent context.
                router.replace(`?view=documents&agent=${encodeURIComponent(key)}`, { scroll: false });
              }}
            />
          ) : null}

          {view === "documents" ? (
            <DealDocumentWorkspace
              dealId={dealId}
              dealName={dealName}
              accessToken={tokens?.accessToken}
              onError={setError}
              agentKey={agentKey}
            />
          ) : null}

          {view === "reports" ? (
            <DealReports
              dealId={dealId}
              dealName={dealName}
              accessToken={tokens?.accessToken}
              onError={setError}
            />
          ) : null}

          {view === "databook" ? (
            <DealDatabook
              dealId={dealId}
              accessToken={tokens?.accessToken}
              onError={setError}
            />
          ) : null}
        </main>
      </div>
    </div>
  );
}
