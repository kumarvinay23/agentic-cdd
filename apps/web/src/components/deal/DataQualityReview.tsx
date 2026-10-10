"use client";

import { useMemo, useState } from "react";
import type { DataQualityCandidate, DataQualityItem, DataQualityPayload } from "@/lib/api";
import {
  DEFAULT_PAGE_SIZE,
  ListPagination,
  useClientPagination,
} from "@/components/deal/ListPagination";

export type DataQualityFilter = "all" | "dropped" | "conflict" | "assumed" | "failed_check";

function formatNum(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-GB", { maximumFractionDigits: 4 }).format(value);
}

function itemTitle(item: DataQualityItem, index: number): string {
  const n = index + 1;
  if (item.kind === "conflict") {
    return `# ${n} Sources disagree · ${item.metric} · FY${item.fiscal_year ?? "—"}`;
  }
  if (item.kind === "dropped") {
    return `# ${n} Not landed — ${item.reason}`;
  }
  if (item.kind === "failed_check") {
    return `# ${n} Failed its check · ${item.source || "Document"}${
      item.fiscal_year != null ? ` · FY${item.fiscal_year}` : ""
    }`;
  }
  if (item.kind === "assumed") {
    return `# ${n} Assumption made · ${item.metric}${
      item.fiscal_year != null ? ` · FY${item.fiscal_year}` : ""
    } — ${item.reason}`;
  }
  return `# ${n}`;
}

function badge(kind: DataQualityItem["kind"]): { label: string; className: string } {
  switch (kind) {
    case "conflict":
      return { label: "Sources disagree", className: "bg-[#fef3c7] text-[#92400e]" };
    case "dropped":
      return { label: "Not landed", className: "bg-[#f1f5f9] text-[#475569]" };
    case "failed_check":
      return { label: "Failed its check", className: "bg-[#fee2e2] text-[#991b1b]" };
    case "assumed":
      return { label: "Assumption made", className: "bg-[#e0e7ff] text-[#3730a3]" };
    default:
      return { label: "Issue", className: "bg-[#f1f5f9] text-[#475569]" };
  }
}

export function DataQualityReview({
  quality,
  busy,
  onAcceptConflict,
  showActions = true,
  pageSize: pageSizeProp,
}: {
  quality: DataQualityPayload | null;
  busy?: boolean;
  onAcceptConflict?: (
    item: Extract<DataQualityItem, { kind: "conflict" }>,
    cand?: DataQualityCandidate,
  ) => void;
  showActions?: boolean;
  /** @deprecated Hard cap removed — use pageSize instead. Kept as unused alias for callers. */
  maxItems?: number;
  pageSize?: number;
}) {
  const [filter, setFilter] = useState<DataQualityFilter>("all");
  const [expanded, setExpanded] = useState<number | null>(0);
  const [pageSize, setPageSize] = useState(pageSizeProp ?? DEFAULT_PAGE_SIZE);

  const items = quality?.items || [];
  const byKind = quality?.summary?.by_kind || {};
  const counts = useMemo(
    () => ({
      all: quality?.summary?.total ?? items.length,
      dropped: byKind.dropped ?? items.filter((i) => i.kind === "dropped").length,
      conflict: byKind.conflict ?? items.filter((i) => i.kind === "conflict").length,
      assumed: byKind.assumed ?? items.filter((i) => i.kind === "assumed").length,
      failed_check:
        byKind.failed_check ?? items.filter((i) => i.kind === "failed_check").length,
    }),
    [byKind, items, quality?.summary?.total],
  );

  const filtered = useMemo(() => {
    if (filter === "all") return items;
    return items.filter((i) => i.kind === filter);
  }, [filter, items]);

  const pager = useClientPagination(filtered, pageSize);

  const chips: Array<{ id: DataQualityFilter; label: string; count: number }> = [
    { id: "all", label: "All", count: counts.all },
    { id: "dropped", label: "Not landed", count: counts.dropped },
    { id: "conflict", label: "Sources disagree", count: counts.conflict },
    { id: "assumed", label: "Assumption made", count: counts.assumed },
    { id: "failed_check", label: "Failed check", count: counts.failed_check },
  ];

  return (
    <section className="overflow-hidden rounded-[10px] border border-[#e5e7eb] bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
      <div className="border-b border-[#e5e7eb] px-4 py-3">
        <h3 className="text-[15px] font-semibold text-[#0f172a]">Data quality review</h3>
        <p className="mt-0.5 text-[12px] text-[#64748b]">
          Exceptions from extract and mapping. Clear in order: assumptions → sources disagree → not
          landed. Auto-chosen conflict values are proposals only.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {chips.map((chip) => {
            if (chip.id !== "all" && chip.count === 0) return null;
            const active = filter === chip.id;
            return (
              <button
                key={chip.id}
                type="button"
                onClick={() => {
                  setFilter(chip.id);
                  setExpanded(0);
                }}
                className={`rounded-full px-3 py-1.5 text-[12px] font-medium ${
                  active
                    ? "bg-[#1e3a5f] text-white"
                    : "bg-[#eef0f3] text-[#0f172a] hover:bg-[#e5e7eb]"
                }`}
              >
                {chip.label} : {chip.count}
              </button>
            );
          })}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="px-4 py-8 text-center text-[13px] text-[#64748b]">
          {counts.all === 0
            ? "No data-quality issues yet. Upload VDR files, run library ingest, then Rescan Databook."
            : "Nothing in this filter."}
        </p>
      ) : (
        <ul className="divide-y divide-[#e5e7eb]">
          {pager.pageItems.map((item, idx) => {
            const absoluteIndex = pager.from - 1 + idx;
            const open = expanded === absoluteIndex;
            const tone = badge(item.kind);
            return (
              <li key={`${item.kind}-${absoluteIndex}`}>
                <button
                  type="button"
                  onClick={() => setExpanded(open ? null : absoluteIndex)}
                  className="flex w-full items-start gap-2 px-4 py-3 text-left hover:bg-[#f8fafc]"
                >
                  <span
                    className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${tone.className}`}
                  >
                    {tone.label}
                  </span>
                  <span className="min-w-0 flex-1 text-[13px] text-[#0f172a]">
                    {itemTitle(item, absoluteIndex)}
                  </span>
                  <span className="shrink-0 text-[12px] text-[#94a3b8]">{open ? "▾" : "▸"}</span>
                </button>
                {open ? (
                  <div className="border-t border-[#f1f5f9] bg-[#fafafa] px-4 py-3 text-[13px]">
                    {item.kind === "conflict" ? (
                      <div className="space-y-2">
                        <p className="text-[#475569]">
                          Scope: {item.scope}. Proposed:{" "}
                          <span className="font-medium text-[#0f172a]">{formatNum(item.chosen)}</span>
                        </p>
                        <ul className="space-y-1.5 text-[12px] text-[#64748b]">
                          {(item.candidates || []).map((c, i) => (
                            <li key={i} className="flex flex-wrap items-center gap-2">
                              <span>
                                {c.chosen ? "✓ " : "· "}
                                {formatNum(c.value)} — {(c.captions || []).join(", ") || "—"} —{" "}
                                {(c.sources || []).join(", ") || "—"}
                              </span>
                              {showActions && onAcceptConflict ? (
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onAcceptConflict(item, c);
                                  }}
                                  className="rounded border border-[#e5e7eb] bg-white px-1.5 py-0.5 text-[11px] font-medium text-[#1e3a5f] hover:bg-[#f8fafc] disabled:opacity-50"
                                >
                                  {c.chosen ? "Accept proposal" : "Choose this"}
                                </button>
                              ) : null}
                            </li>
                          ))}
                        </ul>
                        {item.rule ? (
                          <p className="text-[11px] text-[#94a3b8]">Rule: {item.rule}</p>
                        ) : null}
                      </div>
                    ) : null}

                    {item.kind === "dropped" ? (
                      <div>
                        <p className="text-[#0f172a]">
                          {item.detail?.metric || "Metric"}
                          {item.detail?.fiscal_year != null
                            ? ` · FY${item.detail.fiscal_year}`
                            : ""}
                          : {formatNum(item.detail?.value)}
                        </p>
                        <p className="mt-1 text-[#64748b]">{item.reason}</p>
                        <p className="mt-1 text-[11px] text-[#94a3b8]">Source: {item.source}</p>
                      </div>
                    ) : null}

                    {item.kind === "failed_check" ? (
                      <div>
                        <p className="text-[#475569]">
                          Printed {formatNum(item.printed_subtotal)} vs sum{" "}
                          {formatNum(item.computed_sum)}
                        </p>
                        <p className="mt-1 text-[#64748b]">
                          {item.reason ||
                            "Statement block does not tie — constituents held out of the databook."}
                        </p>
                      </div>
                    ) : null}

                    {item.kind === "assumed" ? (
                      <div>
                        <p className="text-[#0f172a]">
                          Value {formatNum(item.value)}
                          {item.unit || item.scale || item.currency
                            ? ` (${[item.currency, item.scale, item.unit].filter(Boolean).join(" ")})`
                            : ""}
                        </p>
                        <p className="mt-1 text-[#64748b]">{item.reason}</p>
                        <p className="mt-1 text-[11px] text-[#94a3b8]">
                          {item.caption ? `${item.caption} · ` : ""}
                          {item.source}
                        </p>
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}

      <ListPagination
        page={pager.page}
        pageCount={pager.pageCount}
        total={pager.total}
        from={pager.from}
        to={pager.to}
        pageSize={pageSize}
        onPageChange={(p) => {
          pager.setPage(p);
          setExpanded(null);
        }}
        onPageSizeChange={setPageSize}
      />
    </section>
  );
}
