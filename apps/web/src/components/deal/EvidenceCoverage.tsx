"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { EvidenceNetworkMap } from "@/components/deal/EvidenceNetworkMap";
import { product } from "@/lib/config";
import {
  dataClassLabel,
  isAvailable,
  STATUS_ORDER,
  type EvidenceAnalyzePayload,
  type EvidenceNode,
  type EvidenceStatus,
} from "@/lib/evidence-types";

type Tab = "map" | "table";
type TableFilter = "all" | "available" | "missing";

function StatusDot({ color, size = 8 }: { color: string; size?: number }) {
  return (
    <span
      className="inline-block shrink-0 rounded-full"
      style={{ width: size, height: size, background: color }}
    />
  );
}

function EvidenceTypeBadge({ dataClass }: { dataClass?: EvidenceNode["data_class"] }) {
  const primary = dataClass === "primary";
  return (
    <span
      className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${
        primary ? "bg-[#f8e8e4] text-[#9a4b3f]" : "bg-[#f3f0ea] text-[#4b5563] ring-1 ring-[#e5e0d6]"
      }`}
    >
      {dataClassLabel(dataClass)}
    </span>
  );
}

function AvailabilityBadge({ status }: { status?: EvidenceStatus }) {
  const available = isAvailable(status);
  return (
    <span
      className={`inline-flex rounded-md px-2 py-0.5 text-[11px] font-medium ${
        available ? "bg-[#e8f6ec] text-[#166534]" : "bg-[#fdecec] text-[#b42318]"
      }`}
    >
      {available ? "Available" : "Not available"}
    </span>
  );
}

function NodeDetail({
  node,
  graph,
}: {
  node: EvidenceNode | null;
  graph: EvidenceAnalyzePayload["graph"];
}) {
  if (!node) {
    return (
      <p className="text-[13px] leading-5 text-text-secondary">
        Click a requirement in the map to see why it matters and how to close the gap. Node size
        reflects its weight in the diligence.
      </p>
    );
  }

  if (node.kind === "root") {
    return (
      <div className="space-y-2">
        <h3 className="text-[16px] font-semibold text-text-primary">{node.label}</h3>
        <p className="text-[13px] text-text-secondary">
          {graph.vdr_files.length} documents in the data room.
        </p>
      </div>
    );
  }

  if (node.kind === "workstream") {
    const roll = graph.workstreams.find((ws) => ws.id === node.ws)?.roll;
    return (
      <div className="space-y-3">
        <div>
          <h3 className="text-[16px] font-semibold text-text-primary">{node.label}</h3>
          <p className="mt-1 text-[12px] text-text-secondary">{node.desc}</p>
        </div>
        {roll ? (
          <div className="space-y-1.5">
            {STATUS_ORDER.map((key) => (
              <div key={key} className="flex items-center justify-between text-[12px]">
                <span className="flex items-center gap-2 text-text-secondary">
                  <StatusDot color={graph.status_legend[key].color} />
                  {graph.status_legend[key].label}
                </span>
                <span className="font-medium text-text-primary">{roll[key]}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );
  }

  const legend = node.status ? graph.status_legend[node.status] : null;
  const workstream = graph.workstreams.find((ws) => ws.id === node.ws)?.label;
  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-[16px] font-semibold leading-snug text-text-primary">{node.label}</h3>
        <p className="mt-1 text-[12px] text-text-secondary">
          {workstream} · {node.data_class}-class · weight {node.weight ?? 1}
        </p>
      </div>
      {legend ? (
        <span
          className="inline-flex rounded-md px-2.5 py-1 text-[12px] font-medium text-white"
          style={{ background: legend.color }}
        >
          {legend.label}
        </span>
      ) : null}
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
          Why it matters
        </p>
        <p className="text-[13px] leading-5 text-text-primary">{node.so_what}</p>
      </div>
      <div>
        <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
          How to close it
        </p>
        <p className="text-[13px] leading-5 text-text-primary">{node.remedy}</p>
      </div>
      {node.trail?.length ? (
        <div>
          <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-text-secondary">
            Evidence trail
          </p>
          <div className="flex flex-wrap gap-1.5">
            {node.trail.map((item) => (
              <span
                key={item}
                className="rounded-md bg-[#eeeae3] px-2 py-0.5 text-[11px] text-[#4b5563]"
              >
                {item}
              </span>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CoverageTable({
  graph,
  filter,
  onSelect,
}: {
  graph: EvidenceAnalyzePayload["graph"];
  filter: TableFilter;
  onSelect: (node: EvidenceNode) => void;
}) {
  const reqs = graph.nodes.filter((n) => n.kind === "req");
  const grouped = graph.workstreams.map((ws) => {
    const items = reqs
      .filter((n) => n.ws === ws.id)
      .filter((n) => {
        if (filter === "available") return isAvailable(n.status);
        if (filter === "missing") return !isAvailable(n.status);
        return true;
      });
    const available = reqs.filter((n) => n.ws === ws.id && isAvailable(n.status)).length;
    const total = reqs.filter((n) => n.ws === ws.id).length;
    return { ws, items, available, total };
  });

  return (
    <div className="space-y-5">
      {grouped.map(({ ws, items, available, total }) => (
        <section key={ws.id} className="overflow-hidden rounded-xl border border-[#e6e1d6] bg-white">
          <header className="flex items-center justify-between bg-[#f3eee4] px-4 py-2.5">
            <h3 className="text-[12px] font-semibold uppercase tracking-wide text-text-primary">{ws.label}</h3>
            <p className="text-[12px] text-text-secondary">
              {available}/{total} available
            </p>
          </header>
          <div>
            {items.length === 0 ? (
              <p className="px-4 py-3 text-[13px] text-text-secondary">No requirements in this filter.</p>
            ) : (
              items.map((node) => {
                const legend = node.status ? graph.status_legend[node.status] : null;
                return (
                  <button
                    key={node.id}
                    type="button"
                    onClick={() => onSelect(node)}
                    className="flex w-full items-center gap-4 border-t border-[#efeae1] px-4 py-3 text-left hover:bg-[#faf8f4]"
                    style={{ boxShadow: `inset 3px 0 0 ${legend?.color || "#d1d5db"}` }}
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-semibold text-text-primary">{node.label}</p>
                      <p className="mt-0.5 text-[12px] text-text-secondary">{node.remedy}</p>
                    </div>
                    <EvidenceTypeBadge dataClass={node.data_class} />
                    <span className="inline-flex min-w-[132px] items-center gap-1.5 text-[12px] text-text-primary">
                      {legend ? <StatusDot color={legend.color} /> : null}
                      {legend?.label}
                    </span>
                    <AvailabilityBadge status={node.status} />
                  </button>
                );
              })
            )}
          </div>
        </section>
      ))}
    </div>
  );
}

export function EvidenceCoverage({
  dealId,
  payload,
  analyzing,
  error,
  onReanalyze,
}: {
  dealId: string;
  payload: EvidenceAnalyzePayload | null;
  analyzing: boolean;
  error: string | null;
  onReanalyze: () => void;
}) {
  const [tab, setTab] = useState<Tab>("map");
  const [filter, setFilter] = useState<TableFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const graph = payload?.graph;
  const scorecard = payload?.scorecard || graph?.scorecard;

  const selected = useMemo(
    () => graph?.nodes.find((n) => n.id === selectedId) || null,
    [graph, selectedId],
  );

  return (
    <div className="min-h-screen bg-[#f4f1ea]">
      <header className="sticky top-0 z-20 border-b border-[#e6e1d6] bg-[#f4f1ea]/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1280px] items-center justify-between px-5 py-3">
          <Link
            href={`/deals/${dealId}?view=vdr`}
            className="text-[13px] font-medium text-text-secondary hover:text-text-primary"
          >
            ← Deal Room
          </Link>
          <button
            type="button"
            onClick={onReanalyze}
            disabled={analyzing}
            className="inline-flex items-center rounded-lg border border-[#1e3a5f] bg-white px-3 py-1.5 text-[13px] font-medium text-[#1e3a5f] hover:bg-[#eef3f8] disabled:opacity-60"
          >
            {analyzing ? "Analyzing…" : "Reanalyze documents"}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-[1280px] px-5 py-6">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
          Commercial due diligence
        </p>
        <div className="mt-1 flex items-end justify-between gap-4">
          <div>
            <h1 className="text-[28px] font-semibold tracking-tight text-text-primary">
              Evidence Coverage & Gap Analysis
            </h1>
            <p className="mt-1 max-w-3xl text-[13px] leading-5 text-text-secondary">
              Full diligence draws on 32 kinds of evidence. This map shows what the data room already
              covers versus what still needs secondary (web) or primary research.
            </p>
          </div>
          <p className="hidden text-[12px] text-text-secondary sm:block">{product.name}</p>
        </div>

        {error ? (
          <p className="mt-4 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
            {error}
          </p>
        ) : null}

        {!payload && !analyzing ? (
          <div className="mt-8 rounded-xl border border-[#e6e1d6] bg-white p-8 text-center">
            <p className="text-[14px] text-text-secondary">No evidence coverage yet. Analyze the data room to score 32 requirements.</p>
            <button
              type="button"
              onClick={onReanalyze}
              className="mt-4 rounded-lg bg-[#1e3a5f] px-4 py-2 text-[13px] font-medium text-white"
            >
              Analyze documents
            </button>
          </div>
        ) : null}

        {scorecard ? (
          <section className="mt-6 flex flex-wrap items-center gap-8 rounded-xl border border-[#e6e1d6] bg-white px-5 py-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                Evidence readiness
              </p>
              <p className="text-[32px] font-semibold leading-none text-text-primary">
                {scorecard.readiness}
                <span className="text-[18px] font-medium text-text-secondary"> / 100</span>
              </p>
              <p className="mt-1 max-w-xs text-[12px] text-text-secondary">{scorecard.tier}</p>
            </div>
            <div className="flex flex-wrap gap-6">
              {STATUS_ORDER.map((key) => (
                <div key={key} className="min-w-[88px]">
                  <p className="flex items-center gap-2 text-[22px] font-semibold text-text-primary">
                    <StatusDot color={graph?.status_legend[key].color || "#9ca3af"} size={10} />
                    {scorecard.counts[key]}
                  </p>
                  <p className="text-[12px] text-text-secondary">{graph?.status_legend[key].label}</p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

        {graph ? (
          <>
            <div className="mt-6 flex items-center justify-between gap-4 border-b border-[#e6e1d6]">
              <div className="flex gap-5">
                {(
                  [
                    ["map", "Network map"],
                    ["table", "Coverage table"],
                  ] as const
                ).map(([id, label]) => (
                  <button
                    key={id}
                    type="button"
                    onClick={() => setTab(id)}
                    className={`border-b-2 pb-2 text-[13px] ${
                      tab === id
                        ? "border-text-primary font-semibold text-text-primary"
                        : "border-transparent text-text-secondary hover:text-text-primary"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {tab === "table" ? (
                <p className="hidden text-[11px] text-text-secondary lg:block">
                  Node size = weight in the diligence. &apos;Not available&apos; splits into web-fillable,
                  request-from-management, or primary-research per the Status column.
                </p>
              ) : null}
            </div>

            {tab === "table" ? (
              <div className="mt-4">
                <div className="mb-4 flex gap-2">
                  {(
                    [
                      ["all", "All"],
                      ["available", "Available"],
                      ["missing", "Not available"],
                    ] as const
                  ).map(([id, label]) => (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setFilter(id)}
                      className={`rounded-md px-3 py-1.5 text-[12px] font-medium ${
                        filter === id
                          ? "bg-[#1e3a5f] text-white"
                          : "bg-white text-text-secondary ring-1 ring-[#e6e1d6] hover:text-text-primary"
                      }`}
                    >
                      {label}
                    </button>
                  ))}
                </div>
                <CoverageTable
                  graph={graph}
                  filter={filter}
                  onSelect={(node) => {
                    setSelectedId(node.id);
                    setTab("map");
                  }}
                />
              </div>
            ) : (
              <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                <EvidenceNetworkMap
                  graph={graph}
                  selectedId={selectedId}
                  onSelect={(node) => setSelectedId(node.id)}
                />
                <aside className="space-y-4">
                  <section className="rounded-xl border border-[#e6e1d6] bg-white p-4">
                    <p className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                      {selected?.kind === "req" ? "Requirement" : "Select a node"}
                    </p>
                    <NodeDetail node={selected} graph={graph} />
                  </section>
                  <section className="rounded-xl border border-[#e6e1d6] bg-white p-4">
                    <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                      Legend
                    </p>
                    <div className="space-y-2">
                      {STATUS_ORDER.map((key) => (
                        <div key={key} className="flex items-center gap-2 text-[13px] text-text-primary">
                          <StatusDot color={graph.status_legend[key].color} />
                          {graph.status_legend[key].label}
                        </div>
                      ))}
                    </div>
                  </section>
                  <section className="rounded-xl border border-[#e6e1d6] bg-white p-4">
                    <p className="mb-3 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                      Documents ({graph.vdr_files.length})
                    </p>
                    <div className="flex max-h-56 flex-wrap gap-1.5 overflow-auto">
                      {graph.vdr_files.map((name) => (
                        <span
                          key={name}
                          className="rounded-md bg-[#f3f0ea] px-2 py-1 text-[11px] text-text-secondary"
                        >
                          {name}
                        </span>
                      ))}
                    </div>
                  </section>
                </aside>
              </div>
            )}
          </>
        ) : null}
      </main>
    </div>
  );
}
