"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  pipelineAgentOutputRequest,
  pipelinePhaseRunStream,
  pipelineRequest,
  pipelineRunRequest,
  type PipelinePayload,
  type PipelinePhase,
} from "@/lib/api";

function srcBadgeLabel(src?: string): string {
  if (!src) return "ALGO";
  if (src === "algo+web") return "ALGO+WEB";
  if (src === "report") return "REPORT";
  return src.toUpperCase();
}

function phaseBadge(status: string): string {
  if (status === "completed") return "bg-[#ecfdf3] text-[#15803d]";
  if (status === "in_progress" || status === "running") return "bg-[#eff6ff] text-[#1d4ed8]";
  return "bg-[#eef0f3] text-[#4b5563]";
}

function agentBadge(status: string): string {
  if (status === "completed") return "text-[#15803d]";
  if (status === "running") return "text-[#1d4ed8]";
  if (status === "failed") return "text-text-danger";
  return "text-text-secondary";
}


function specEntries(spec: Record<string, unknown>): [string, string][] {
  const rows: [string, string][] = [];
  for (const [key, value] of Object.entries(spec)) {
    if (
      key === "extractor" ||
      key === "role_code" ||
      key === "attractiveness_score" ||
      key === "org_risk_score" ||
      key === "investment_drivers" ||
      key === "must_be_true" ||
      key === "deal_breaker_risks" ||
      key === "risks" ||
      key === "c_suite" ||
      key === "workstreams" ||
      key === "dates" ||
      key === "coverage"
    ) {
      continue;
    }
    if (value == null || value === "") continue;
    if (Array.isArray(value)) {
      if (!value.length) continue;
      const preview = value
        .slice(0, 4)
        .map((item) => (typeof item === "object" && item ? JSON.stringify(item) : String(item)))
        .join(" · ");
      rows.push([key, preview]);
    } else if (typeof value === "object") {
      continue;
    } else {
      rows.push([key, String(value)]);
    }
  }
  return rows;
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => (typeof item === "string" ? item : JSON.stringify(item))).filter(Boolean);
}

function FoundationSpecPanel({ spec }: { spec: Record<string, unknown> }) {
  const score = spec.attractiveness_score ?? spec.org_risk_score;
  const drivers = asStringList(spec.investment_drivers);
  const mustBeTrue = asStringList(spec.must_be_true);
  const breakers = asStringList(spec.deal_breaker_risks);
  const risks = Array.isArray(spec.risks) ? spec.risks : [];
  const suite = Array.isArray(spec.c_suite) ? spec.c_suite : [];
  const workstreams = Array.isArray(spec.workstreams) ? spec.workstreams : [];
  const dates = Array.isArray(spec.dates) ? spec.dates : [];

  return (
    <div className="mb-3 space-y-3 text-[12px] text-text-primary">
      {typeof score === "number" ? (
        <div className="flex items-baseline gap-2">
          <p className="text-[28px] font-semibold tabular-nums">{score}</p>
          <p className="text-text-secondary">
            {spec.attractiveness_score != null ? "Attractiveness (1–10)" : "Org risk (1–10)"}
            {spec.thesis_framework ? ` · ${String(spec.thesis_framework)}` : ""}
            {spec.consumes_f01_score != null ? ` · uses F-01 ${String(spec.consumes_f01_score)}` : ""}
            {spec.consumes_f05 ? " · uses F-05 entity" : ""}
          </p>
        </div>
      ) : null}

      {drivers.length ? (
        <section>
          <p className="font-medium text-text-secondary">Investment drivers</p>
          <ul className="mt-1 list-disc pl-4">{drivers.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      ) : null}
      {mustBeTrue.length ? (
        <section>
          <p className="font-medium text-text-secondary">Must be true</p>
          <ul className="mt-1 list-disc pl-4">{mustBeTrue.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      ) : null}
      {breakers.length ? (
        <section>
          <p className="font-medium text-text-secondary">Deal-breaker risks</p>
          <ul className="mt-1 list-disc pl-4">{breakers.map((item) => <li key={item}>{item}</li>)}</ul>
        </section>
      ) : null}

      {workstreams.length ? (
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="text-text-secondary">
              <th className="pb-1 font-medium">Workstream</th>
              <th className="pb-1 font-medium">Priority</th>
            </tr>
          </thead>
          <tbody>
            {workstreams.map((row, i) => {
              const item = row as Record<string, unknown>;
              return (
                <tr key={i} className="border-t border-border-primary">
                  <td className="py-1">{String(item.name ?? "")}</td>
                  <td className="py-1">{String(item.priority ?? "")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}

      {dates.length ? (
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="text-text-secondary">
              <th className="pb-1 font-medium">Process date</th>
              <th className="pb-1 font-medium">Value</th>
            </tr>
          </thead>
          <tbody>
            {dates.map((row, i) => {
              const item = row as Record<string, unknown>;
              return (
                <tr key={i} className="border-t border-border-primary">
                  <td className="py-1">{String(item.label ?? "")}</td>
                  <td className="py-1">{String(item.value ?? "")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}

      {risks.length ? (
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="text-text-secondary">
              <th className="pb-1 font-medium">Clause</th>
              <th className="pb-1 font-medium">Severity</th>
              <th className="pb-1 font-medium">Mitigant</th>
            </tr>
          </thead>
          <tbody>
            {risks.map((row, i) => {
              const item = row as Record<string, unknown>;
              return (
                <tr key={i} className="border-t border-border-primary align-top">
                  <td className="py-1 pr-2">{String(item.clause ?? "")}</td>
                  <td className="py-1 pr-2">{String(item.severity ?? "")}</td>
                  <td className="py-1">{String(item.mitigant ?? "")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}

      {suite.length ? (
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="text-text-secondary">
              <th className="pb-1 font-medium">Role</th>
              <th className="pb-1 font-medium">Name</th>
              <th className="pb-1 font-medium">Criticality</th>
              <th className="pb-1 font-medium">Replaceability</th>
            </tr>
          </thead>
          <tbody>
            {suite.map((row, i) => {
              const item = row as Record<string, unknown>;
              return (
                <tr key={i} className="border-t border-border-primary">
                  <td className="py-1">{String(item.role ?? "")}</td>
                  <td className="py-1">{String(item.name ?? "")}</td>
                  <td className="py-1">{String(item.criticality ?? "")}</td>
                  <td className="py-1">{String(item.replaceability ?? "")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : null}

      {typeof spec.coverage === "string" ? (
        <p className="text-text-secondary">Process coverage: {spec.coverage}</p>
      ) : null}

      <dl className="grid gap-1.5">
        {specEntries(spec).map(([key, value]) => (
          <div key={key} className="grid grid-cols-[140px_1fr] gap-2">
            <dt className="font-medium text-text-secondary">{key}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

const PHASE_BLURBS: Record<string, string> = {
  data_ingestion: "Ingest and process all portfolio documents for analysis.",
  foundations: "Build foundational understanding of the company, strategy, and governance.",
  deep_dive: "Deep-dive commercial, operational, financial, and risk workstreams.",
  ic_recommendation: "Synthesize findings into an investment committee recommendation.",
  reports: "Assemble diligence reports and packs from completed agents.",
};

export function DealWorkflow({
  dealId,
  accessToken,
  onError,
  onOpenDocuments,
  onOpenAgentDocument,
}: {
  dealId: string;
  accessToken: string | undefined;
  onError: (message: string | null) => void;
  onOpenDocuments?: () => void;
  onOpenAgentDocument?: (agentKey: string) => void;
}) {
  const [pipeline, setPipeline] = useState<PipelinePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [selectedOutput, setSelectedOutput] = useState<string | null>(null);
  const [outputJson, setOutputJson] = useState<Record<string, unknown> | null>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await pipelineRequest(accessToken, dealId);
      setPipeline(res.data);
      onError(null);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Failed to load pipeline");
    } finally {
      setLoading(false);
    }
  }, [accessToken, dealId, onError]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const active =
    running ||
    !!pipeline?.running ||
    !!pipeline?.running_agent_key ||
    (pipeline?.phases ?? []).some((phase) =>
      (phase.agents ?? []).some((agent) => agent.status === "running"),
    );

  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, 600);
    return () => window.clearInterval(timer);
  }, [active, refresh]);

  async function runPhase(phaseId?: string) {
    if (!accessToken) return;
    setRunning(true);
    onError(null);
    try {
      if (phaseId === "deep_dive") {
        await pipelinePhaseRunStream(accessToken, dealId, phaseId, {
          onEvent: () => {
            void refresh();
          },
        });
      } else {
        await pipelineRunRequest(accessToken, dealId, phaseId ? { phase_id: phaseId } : {});
      }
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Pipeline run failed");
    } finally {
      setRunning(false);
    }
  }

  async function runAgent(agentKey: string) {
    if (!accessToken) return;
    setRunning(true);
    onError(null);
    try {
      await pipelineRunRequest(accessToken, dealId, { agent_key: agentKey });
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Agent run failed");
    } finally {
      setRunning(false);
    }
  }

  async function showOutput(agentKey: string) {
    if (!accessToken) return;
    setSelectedOutput(agentKey);
    try {
      const res = await pipelineAgentOutputRequest(accessToken, dealId, agentKey);
      setOutputJson(res.data.file_output || res.data.output);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "No output for this agent yet");
      setOutputJson(null);
    }
  }

  if (loading && !pipeline) {
    return <p className="text-[13px] text-text-secondary">Loading workflow…</p>;
  }
  if (!pipeline) return null;

  const busy = active;
  const completed = pipeline.completedAgents ?? 0;
  const total = pipeline.totalAgents ?? 0;
  const pct = pipeline.completionPercentage ?? 0;
  const runningKey = pipeline.running_agent_key;
  const runningName = pipeline.running_agent_name;

  return (
    <div className="space-y-4">
      <section className="rounded-[10px] border border-border-primary bg-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-[20px] font-semibold tracking-tight text-text-primary">Analysis workflow</h1>
            <p className="mt-1 text-[13px] text-text-secondary">
              {total} named agents across 5 phases — each runs its specific diligence analysis over the deal&apos;s data.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onOpenDocuments?.()}
              className="rounded-lg border border-border-primary bg-white px-3 py-2 text-[13px] font-medium text-text-primary hover:bg-[#f8f9fb]"
            >
              Document workspace
            </button>
            <button
              type="button"
              disabled={busy || !pipeline.next_phase_id}
              onClick={() => void runPhase()}
              className="rounded-lg bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white hover:bg-[#16304f] disabled:opacity-60"
            >
              {busy ? "Running…" : "Run all"}
            </button>
          </div>
        </div>
        <p className="mt-4 text-[12px] text-text-secondary">
          {completed} of {total} agents completed
        </p>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-[#e8eaee]">
          <div className="h-full rounded-full bg-[#1e3a5f]" style={{ width: `${pct}%` }} />
        </div>
        {runningName ? (
          <p className="mt-3 rounded-md bg-[#eff6ff] px-3 py-2 text-[13px] font-medium text-[#1d4ed8]">
            Now running: {runningName}
          </p>
        ) : null}
      </section>

      <div className="space-y-3">
        {pipeline.phases.map((phase: PipelinePhase) => {
          const phaseBusy = (phase.agents ?? []).some((agent) => agent.status === "running")
            || (busy && (phase.agents ?? []).some((agent) => agent.status === "pending"));
          const canRun = !busy && (pipeline.next_phase_id === phase.phase_id || phase.status === "completed");
          const open = phaseBusy || phase.status === "in_progress" || phase.status === "running";
          return (
            <details
              key={phase.phaseUuid}
              className="rounded-[10px] border border-border-primary bg-white"
              open={open || phase.order === 2}
            >
              <summary className="cursor-pointer list-none px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border-primary text-[12px] font-semibold text-text-primary">
                      {phase.order}
                    </span>
                    <div>
                      <p className="text-[14px] font-semibold text-text-primary">
                        {phase.phaseName}{" "}
                        <span className="font-normal text-text-secondary">
                          ({phase.completedAgents}/{phase.totalAgents} agents)
                        </span>
                      </p>
                      <p className="mt-0.5 text-[12px] text-text-secondary">
                        {PHASE_BLURBS[phase.phase_id] ?? phase.phaseName}
                      </p>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <button
                      type="button"
                      disabled={!canRun}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        void runPhase(phase.phase_id);
                      }}
                      className="rounded-md border border-border-primary bg-white px-2.5 py-1 text-[12px] font-medium text-text-primary disabled:opacity-40"
                    >
                      Run phase
                    </button>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${phaseBadge(phase.status)}`}>
                      {phaseBusy ? "running" : phase.status.replaceAll("_", " ")}
                    </span>
                  </div>
                </div>
              </summary>
              <div className="space-y-4 border-t border-border-primary px-4 py-3">
                {phase.stages.map((stage) => (
                  <div key={stage.stageKey}>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-[#c2410c]">
                      {stage.stageTitle} ({stage.agents.length})
                    </p>
                    <ul className="mt-2 space-y-2">
                      {stage.agents.map((agent) => {
                        const isRunning = agent.status === "running" || agent.agent_key === runningKey;
                        const isPending = agent.status === "pending";
                        const openDocument = () => {
                          if (onOpenAgentDocument) {
                            onOpenAgentDocument(agent.agent_key);
                            return;
                          }
                          void showOutput(agent.agent_key);
                        };
                        return (
                          <li
                            key={agent.agent_key}
                            role="button"
                            tabIndex={0}
                            onClick={openDocument}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" || e.key === " ") {
                                e.preventDefault();
                                openDocument();
                              }
                            }}
                            className={`flex cursor-pointer items-start justify-between gap-3 rounded-md px-2.5 py-2 transition-colors hover:bg-[#eef2ff] ${
                              isRunning ? "bg-[#eff6ff] ring-1 ring-[#bfdbfe]" : "bg-[#f8f9fb]"
                            }`}
                          >
                            <div>
                              <p className="text-[13px] font-medium text-text-primary">{agent.agentName}</p>
                              <p className="mt-1 flex flex-wrap gap-1">
                                {agent.category ? (
                                  <span className="rounded border border-border-primary px-1.5 py-0.5 text-[10px] uppercase text-text-secondary">
                                    {agent.category.replaceAll("_", " ")}
                                  </span>
                                ) : null}
                                <span className="rounded border border-border-primary px-1.5 py-0.5 text-[10px] uppercase text-text-secondary">
                                  {srcBadgeLabel(agent.src)}
                                </span>
                              </p>
                              {agent.description ? (
                                <p className="mt-1 text-[12px] text-text-secondary">{agent.description}</p>
                              ) : null}
                            </div>
                            <div className="flex shrink-0 items-center gap-2">
                              {isRunning || agent.status === "completed" || agent.status === "failed" || (busy && isPending) ? (
                                <span className={`text-[10px] font-semibold uppercase ${agentBadge(isRunning ? "running" : agent.status)}`}>
                                  {isRunning ? "running" : busy && isPending ? "queued" : agent.status}
                                </span>
                              ) : null}
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openDocument();
                                }}
                                className="text-[11px] text-text-info hover:underline"
                              >
                                Document
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  void runAgent(agent.agent_key);
                                }}
                                className="rounded-md border border-border-primary bg-white px-2 py-0.5 text-[11px] font-medium text-text-primary disabled:opacity-40"
                              >
                                Run
                              </button>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ))}
              </div>
            </details>
          );
        })}
      </div>

      {selectedOutput && outputJson ? (
        <section className="rounded-[10px] border border-border-primary bg-white px-4 py-3">
          <div className="mb-2 flex items-center justify-between">
            <p className="text-[13px] font-semibold text-text-primary">Agent output · {selectedOutput}</p>
            <button
              type="button"
              onClick={() => {
                setSelectedOutput(null);
                setOutputJson(null);
              }}
              className="text-[12px] text-text-secondary hover:text-text-primary"
            >
              Close
            </button>
          </div>
          {outputJson.spec && typeof outputJson.spec === "object" ? (
            <FoundationSpecPanel spec={outputJson.spec as Record<string, unknown>} />
          ) : null}
          <details className="rounded-md bg-[#f8f9fb] p-3">
            <summary className="cursor-pointer text-[12px] text-text-secondary">Raw JSON</summary>
            <pre className="mt-2 max-h-72 overflow-auto text-[11px] text-text-primary">
              {JSON.stringify(outputJson, null, 2)}
            </pre>
          </details>
        </section>
      ) : null}
    </div>
  );
}
