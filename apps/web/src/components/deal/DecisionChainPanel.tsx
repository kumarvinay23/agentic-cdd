"use client";

import { useMemo, useState } from "react";
import type { ReportDecisionChainEntry } from "@/lib/api";

function agentLabel(agent: string): string {
  return agent
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

type ChainTab = "chain" | "sources" | "gaps";

export function DecisionChainPanel({
  entries,
  sectionAgents,
}: {
  readonly entries: ReportDecisionChainEntry[];
  readonly sectionAgents: string[];
}) {
  const rows = useMemo(() => {
    if (entries.length) return entries;
    return sectionAgents.map((agent) => ({
      agent,
      available: false,
      status: "missing",
      chain: {
        plain_english: `No decision-chain data for ${agentLabel(agent)}.`,
        inputs: [],
        calculations: [],
        reads: [],
        gaps: [{ label: "Agent output", detail: "Not available." }],
        source_entries: [],
        counts: { chain: 0, sources: 0, gaps: 1, reads: 0 },
      },
    }));
  }, [entries, sectionAgents]);

  const [activeAgent, setActiveAgent] = useState(rows[0]?.agent || "");
  const [tab, setTab] = useState<ChainTab>("chain");

  const active = rows.find((r) => r.agent === activeAgent) || rows[0];
  const chain = active?.chain;
  const counts = chain?.counts || {
    chain: (chain?.calculations?.length || 0) + (chain?.inputs?.length || 0),
    sources: chain?.source_entries?.length || active?.sources?.length || 0,
    gaps: chain?.gaps?.length || 0,
    reads: chain?.reads?.length || 0,
  };

  if (!rows.length) {
    return (
      <p className="mt-2 text-[12px] text-text-secondary">No workflow agents on this section.</p>
    );
  }

  return (
    <div className="mt-3 overflow-hidden rounded-lg border border-[#e5e7eb] bg-white">
      <div className="border-b border-[#e5e7eb] bg-[#f8f9fb] px-3 py-2">
        <p className="text-[12px] font-semibold text-text-primary">
          Decision chain — source + calculation for every number
        </p>
        <div className="mt-2 flex flex-wrap gap-1.5">
          {rows.map((row) => {
            const selected = row.agent === (active?.agent || "");
            return (
              <button
                key={row.agent}
                type="button"
                onClick={() => {
                  setActiveAgent(row.agent);
                  setTab("chain");
                }}
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                  selected
                    ? "bg-[#1e3a5f] text-white"
                    : "bg-[#eef0f3] text-[#4b5563] hover:bg-[#e5e7eb]"
                }`}
              >
                {agentLabel(row.agent)}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap gap-1 border-b border-[#e5e7eb] px-3 py-2">
        {(
          [
            ["chain", `Σ Chain ${counts.chain ?? 0}`],
            ["sources", `Sources ${counts.sources ?? 0}`],
            ["gaps", `Gaps ${counts.gaps ?? 0}`],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`rounded px-2.5 py-1 text-[11px] font-semibold ${
              tab === id ? "bg-[#1e3a5f] text-white" : "bg-[#eef0f3] text-[#4b5563]"
            }`}
          >
            {label}
          </button>
        ))}
        <span className="ml-auto self-center text-[11px] text-text-secondary">
          {active?.status || "—"} · coverage {active?.coverage || "—"} · extract{" "}
          {active?.extract_source || "—"}
        </span>
      </div>

      <div className="space-y-4 px-3 py-3">
        {tab === "chain" ? (
          <>
            <div className="rounded-md border border-[#dbe4f0] bg-[#eef4fb] px-3 py-2 text-[12px] leading-relaxed text-[#334155]">
              <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-[#1e3a5f]">
                In plain English
              </p>
              <p>{chain?.plain_english || "No narrative available for this agent."}</p>
            </div>

            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                Inputs &amp; source
              </p>
              {(chain?.inputs || []).length ? (
                <div className="divide-y divide-[#eef0f3] rounded-md border border-[#e5e7eb]">
                  {(chain?.inputs || []).map((row, idx) => (
                    <div
                      key={`in-${idx}-${row.label}`}
                      className="grid gap-2 px-3 py-2 text-[12px] md:grid-cols-[1.2fr_1fr_1fr]"
                    >
                      <div>
                        <p className="font-medium text-text-primary">{row.label}</p>
                        {row.key ? <p className="text-[11px] text-[#9ca3af]">{row.key}</p> : null}
                      </div>
                      <p className="text-[#374151]">{row.value}</p>
                      <p className="text-[#6b7280] md:text-right">{row.source || "—"}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[12px] text-text-secondary">No structured inputs on this agent.</p>
              )}
            </div>

            <div>
              <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                Calculations
              </p>
              {(chain?.calculations || []).length ? (
                <div className="divide-y divide-[#eef0f3] rounded-md border border-[#e5e7eb]">
                  {(chain?.calculations || []).map((row, idx) => (
                    <div
                      key={`calc-${idx}-${row.key || row.label}`}
                      className="grid gap-2 px-3 py-2.5 text-[12px] md:grid-cols-[1.2fr_1.6fr_0.8fr]"
                    >
                      <div>
                        <p className="font-medium text-text-primary">{row.label}</p>
                        {row.key ? <p className="text-[11px] text-[#9ca3af]">{row.key}</p> : null}
                        {row.formula ? (
                          <p className="mt-0.5 text-[11px] text-[#6b7280]">{row.formula}</p>
                        ) : null}
                      </div>
                      <p className="text-[#374151]">{row.trace || "—"}</p>
                      <p className="font-semibold text-[#1d4ed8] md:text-right">{row.result || "—"}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-[12px] text-text-secondary">No calculations derived for this agent.</p>
              )}
            </div>

            <details className="rounded-md border border-[#e5e7eb] bg-[#fafbfc] px-3 py-2">
              <summary className="cursor-pointer text-[12px] font-medium text-text-primary">
                Read straight from the source ({counts.reads ?? chain?.reads?.length ?? 0})
              </summary>
              <ul className="mt-2 space-y-1.5 text-[12px] text-text-secondary">
                {(chain?.reads || []).map((row, idx) => (
                  <li key={`read-${idx}-${row.label}`}>
                    <span className="font-medium text-text-primary">{row.label}</span>
                    {" — "}
                    {row.value}
                    <span className="block text-[11px] text-[#9ca3af]">{row.source}</span>
                  </li>
                ))}
                {!chain?.reads?.length ? (
                  <li>No verbatim reads recorded.</li>
                ) : null}
              </ul>
            </details>
          </>
        ) : null}

        {tab === "sources" ? (
          <div className="space-y-2">
            {(chain?.source_entries || []).length || active?.sources?.length ? (
              (chain?.source_entries?.length
                ? chain.source_entries
                : (active?.sources || []).map((file) => ({
                    file,
                    role: "cited",
                    used_by: agentLabel(active?.agent || ""),
                  }))
              ).map((entry) => (
                <div
                  key={`${entry.file}-${entry.used_by}`}
                  className="flex items-center justify-between rounded-md border border-[#e5e7eb] px-3 py-2 text-[12px]"
                >
                  <div>
                    <p className="font-medium text-text-primary">{entry.file}</p>
                    <p className="text-[11px] text-text-secondary">
                      {entry.role || "cited"}
                      {entry.used_by ? ` · ${entry.used_by}` : ""}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <p className="text-[12px] text-text-secondary">No source documents cited.</p>
            )}
          </div>
        ) : null}

        {tab === "gaps" ? (
          <div className="space-y-2">
            {(chain?.gaps || []).length ? (
              (chain?.gaps || []).map((gap, idx) => (
                <div
                  key={`gap-${idx}-${gap.label}`}
                  className="rounded-md border border-[#fde68a] bg-[#fffbeb] px-3 py-2 text-[12px]"
                >
                  <p className="font-semibold text-[#92400e]">{gap.label}</p>
                  <p className="text-[#78350f]">{gap.detail}</p>
                </div>
              ))
            ) : (
              <p className="text-[12px] text-text-secondary">No gaps flagged for this agent.</p>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
}
