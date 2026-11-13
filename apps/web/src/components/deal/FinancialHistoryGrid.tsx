"use client";

import { useMemo, useState } from "react";
import { FigureSourceTip, type SourceTarget } from "@/components/deal/SourceDocumentPanel";
import type {
  DatabookDqIssue,
  DatabookSeriesCell,
  DatabookView,
} from "@/lib/api";

/** Preferred metric row order (DiligenceIQ Financial history). */
const METRIC_ORDER = [
  "revenue",
  "cogs",
  "gross_profit",
  "ebitda",
  "ebit",
  "net_income",
  "cash",
  "total_assets",
  "equity",
] as const;

const METRIC_LABELS: Record<string, string> = {
  revenue: "Revenue",
  cogs: "Cost of goods sold",
  gross_profit: "Gross profit",
  ebitda: "EBITDA",
  ebit: "Operating profit (EBIT)",
  net_income: "Result for the year",
  cash: "Cash",
  total_assets: "Total assets",
  equity: "Equity",
  ebitda_margin: "EBITDA margin",
  gross_margin: "Gross margin",
  grr: "GRR",
  nrr: "NRR",
  grr_commercial: "Commercial GRR",
  nrr_commercial: "Commercial NRR",
  grr_residential: "Residential GRR",
  nrr_residential: "Residential NRR",
};

const RATIO_METRICS = new Set([
  "ebitda_margin",
  "gross_margin",
  "grr",
  "nrr",
  "grr_commercial",
  "nrr_commercial",
  "grr_residential",
  "nrr_residential",
]);

export type FinancialHistorySelection = {
  metric: string;
  year: number;
  cell: DatabookSeriesCell | null;
  issues: DatabookDqIssue[];
};

export function FinancialHistoryGrid({
  view,
  busy = false,
  onSelectCell,
  onAcceptCell,
  onOpenSource,
}: Readonly<{
  view: DatabookView | null;
  busy?: boolean;
  onSelectCell?: (selection: FinancialHistorySelection) => void;
  onAcceptCell?: (selection: FinancialHistorySelection) => void;
  onOpenSource?: (target: SourceTarget) => void;
}>) {
  const [selected, setSelected] = useState<FinancialHistorySelection | null>(null);
  const [tip, setTip] = useState<{
    x: number;
    y: number;
    title: string;
    readFrom: string;
    issues: DatabookDqIssue[];
  } | null>(null);

  const years = useMemo(() => collectYears(view), [view]);
  const metrics = useMemo(() => collectMetrics(view), [view]);

  if (!view) {
    return (
      <p className="text-[13px] text-[#64748b]">Financial history is not loaded yet.</p>
    );
  }

  if (view.status === "unpublished") {
    return (
      <div className="rounded-lg border border-[#fde68a] bg-[#fffbeb] px-4 py-3 text-[13px] text-[#92400e]">
        No financial history for this deal yet.
      </div>
    );
  }

  if (view.status === "building" || (metrics.length === 0 && (view.totals.building ?? 0) > 0)) {
    return (
      <div className="rounded-lg border border-[#bfdbfe] bg-[#eff6ff] px-4 py-3 text-[13px] text-[#1e3a5f]">
        Financial history is still being prepared.
      </div>
    );
  }

  if (metrics.length === 0 || years.length === 0) {
    return (
      <div className="rounded-lg border border-[#e5e7eb] bg-white px-4 py-3 text-[13px] text-[#64748b]">
        No sourced financial history for this deal yet. Mapped statement facts will appear here
        as metric × year cells.
      </div>
    );
  }

  const actualThrough = view.actual_through ?? null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h3 className="text-[15px] font-semibold text-[#0f172a]">Financial history</h3>
          <p className="mt-0.5 text-[12px] text-[#64748b]">
            {view.totals.mapped_rows ?? 0} mapped rows · {view.totals.metrics ?? metrics.length}{" "}
            metrics
            {view.reporting_currency ? ` · ${view.reporting_currency}` : ""}
            {actualThrough != null ? ` · actual through FY${actualThrough}` : ""}
          </p>
        </div>
      </div>

      <div className="overflow-x-auto rounded-lg border border-[#e5e7eb] bg-white">
        <table className="min-w-full border-collapse text-left text-[13px]">
          <thead>
            <tr className="border-b border-[#e5e7eb] text-[11px] uppercase tracking-wide text-[#94a3b8]">
              <th className="sticky left-0 z-10 bg-white px-3 py-2.5 font-medium">Metric</th>
              {years.map((year) => (
                <th key={year} className="px-3 py-2.5 text-right font-medium whitespace-nowrap">
                  FY{year}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {metrics.map((metric) => (
              <tr key={metric} className="border-b border-[#f1f5f9] last:border-0">
                <th
                  scope="row"
                  className="sticky left-0 z-10 bg-white px-3 py-2 font-medium text-[#0f172a] whitespace-nowrap"
                >
                  {METRIC_LABELS[metric] || metric}
                </th>
                {years.map((year) => {
                  const cell = view.series[metric]?.[String(year)] ?? null;
                  const issues = (view.dq_cells[`${metric}|${year}`] || []).filter((issue) =>
                    Number.isFinite(issue.n),
                  );
                  const isForecast = actualThrough != null && year > actualThrough;
                  const empty = cell?.value == null;
                  const title = empty
                    ? "No sourced fact for this figure and year."
                    : sourceTitle(cell);
                  const readFrom = cell?.raw || [cell?.sheet || cell?.statement, cell?.line_item].filter(Boolean).join(" · ");
                  const selection: FinancialHistorySelection = {
                    metric,
                    year,
                    cell,
                    issues,
                  };
                  let cellTone = "text-[#0f172a] hover:bg-[#f8fafc]";
                  if (empty) cellTone = "text-[#94a3b8] hover:bg-[#f8fafc]";
                  else if (issues.length > 0) {
                    cellTone = "bg-[#ffedd5] text-[#9a3412] hover:bg-[#fed7aa]";
                  }
                  const forecastClass = isForecast && !empty ? "italic" : "";
                  const selectedClass =
                    selected?.metric === metric && selected?.year === year
                      ? "ring-1 ring-[#1e3a5f]"
                      : "";
                  return (
                    <td key={year} className="px-1.5 py-1 text-right align-middle">
                      <button
                        type="button"
                        title={empty ? title : undefined}
                        onMouseEnter={(event) => {
                          if (empty) return;
                          const box = event.currentTarget.getBoundingClientRect();
                          setTip({
                            x: box.left,
                            y: box.bottom + 8,
                            title,
                            readFrom,
                            issues,
                          });
                        }}
                        onMouseLeave={() => setTip(null)}
                        onClick={() => {
                          setTip(null);
                          const filename = sourceFile(cell?.source);
                          if (!empty && filename && onOpenSource) {
                            onOpenSource({
                              filename,
                              sheet: cell?.sheet || null,
                              line: cell?.line_item || null,
                              metric,
                              year,
                              row: cell?.source_row,
                              col: cell?.source_col,
                            });
                            return;
                          }
                          setSelected(selection);
                          onSelectCell?.(selection);
                        }}
                        className={`w-full rounded px-2 py-1.5 text-right tabular-nums transition-colors ${cellTone} ${forecastClass} ${selectedClass}`}
                      >
                        {empty ? (
                          <span aria-hidden>—</span>
                        ) : (
                          <span className="inline-flex flex-wrap items-baseline justify-end gap-x-1.5 gap-y-0.5">
                            {issues.length > 0 ? (
                              <span className="text-[10px] font-semibold text-[#c2410c]">
                                {formatDqChip(issues)}
                              </span>
                            ) : null}
                            <span>
                              {formatCellValue(cell, view.reporting_currency, metric)}
                            </span>
                          </span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-[11px] leading-relaxed text-[#94a3b8]">
        Hover a figure for the source document and the line it was read from. Click it to open
        that document. Orange tint marks a data-quality review. Italic is a forecast.
      </p>

      {tip ? (
        <FigureSourceTip
          x={tip.x}
          y={tip.y}
          title={tip.title}
          readFrom={tip.readFrom}
          issues={tip.issues}
        />
      ) : null}

      {selected ? (
        <FinancialHistoryDrawer
          selection={selected}
          reportingCurrency={view.reporting_currency}
          busy={busy}
          onAccept={onAcceptCell}
          onClose={() => setSelected(null)}
        />
      ) : null}
    </div>
  );
}

function FinancialHistoryDrawer({
  selection,
  reportingCurrency,
  busy,
  onAccept,
  onClose,
}: Readonly<{
  selection: FinancialHistorySelection;
  reportingCurrency: string;
  busy: boolean;
  onAccept?: (selection: FinancialHistorySelection) => void;
  onClose: () => void;
}>) {
  const { metric, year, cell, issues } = selection;
  return (
    <aside className="rounded-lg border border-[#e5e7eb] bg-[#f8fafc] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-[13px] font-semibold text-[#0f172a]">
            {METRIC_LABELS[metric] || metric} · FY{year}
          </h4>
          <p className="mt-0.5 text-[12px] text-[#64748b]">
            Accept writes the chosen fact as the selected ontology value. Enter a decision
            reason above first.
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-[#e5e7eb] bg-white px-2 py-1 text-[12px] text-[#64748b] hover:bg-white"
        >
          Close
        </button>
      </div>
      {cell?.value == null ? (
        <p className="mt-3 text-[13px] text-[#64748b]">
          No sourced fact for this figure and year.
        </p>
      ) : (
        <dl className="mt-3 grid gap-2 text-[13px] sm:grid-cols-2">
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Value</dt>
            <dd className="font-medium text-[#0f172a]">
              {formatCellValue(cell, reportingCurrency, metric)}
            </dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Line item</dt>
            <dd className="text-[#0f172a]">{cell.line_item || "—"}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Source</dt>
            <dd className="break-all text-[#0f172a]">{cell.source || "—"}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Raw</dt>
            <dd className="text-[#0f172a]">{cell.raw || "—"}</dd>
          </div>
          <div>
            <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Fact id</dt>
            <dd className="font-mono text-[12px] text-[#0f172a]">{cell.fact_id || "—"}</dd>
          </div>
        </dl>
      )}
      {issues.length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {issues.map((issue) => (
            <li
              key={issue.n}
              className="rounded border border-[#fed7aa] bg-[#fff7ed] px-2.5 py-1.5 text-[12px] text-[#9a3412]"
            >
              <span className="font-semibold">
                #{issue.n} {issue.label}
              </span>
              {issue.detail ? (
                <span className="mt-0.5 block text-[#c2410c]">{issue.detail}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {onAccept && cell?.value != null && cell.fact_id && issues.some((issue) => issue.kind === "conflict") ? (
        <button
          type="button"
          disabled={busy}
          onClick={() => onAccept(selection)}
          className="mt-3 rounded border border-[#0f172a] bg-[#0f172a] px-3 py-1.5 text-[12px] font-medium text-white disabled:opacity-50"
        >
          Accept this value
        </button>
      ) : null}
    </aside>
  );
}

function collectYears(view: DatabookView | null): number[] {
  if (!view) return [];
  const years = new Set<number>();
  for (const byYear of Object.values(view.series || {})) {
    for (const key of Object.keys(byYear || {})) {
      const year = Number(key);
      if (Number.isFinite(year)) years.add(year);
    }
  }
  for (const key of Object.keys(view.dq_cells || {})) {
    const year = Number(key.split("|")[1]);
    if (Number.isFinite(year)) years.add(year);
  }
  return [...years].sort((a, b) => a - b);
}

function collectMetrics(view: DatabookView | null): string[] {
  if (!view) return [];
  const present = new Set(Object.keys(view.series || {}));
  const ordered = METRIC_ORDER.filter((m) => present.has(m));
  const extras = [...present].filter((m) => !METRIC_ORDER.includes(m as (typeof METRIC_ORDER)[number]));
  extras.sort((a, b) => a.localeCompare(b));
  return [...ordered, ...extras];
}

function formatDqChip(issues: DatabookDqIssue[]): string {
  if (issues.length === 0) return "";
  const first = issues[0].n;
  if (issues.length === 1) return `#${first}`;
  return `#${first}+${issues.length - 1}`;
}

function formatCellValue(
  cell: DatabookSeriesCell | null | undefined,
  reportingCurrency: string,
  metric?: string,
): string {
  if (cell?.value == null || !Number.isFinite(cell.value)) return "—";
  const unit = (cell.unit || "").trim();
  if (unit === "%" || (metric != null && RATIO_METRICS.has(metric))) {
    const pct = Math.abs(cell.value) <= 1 ? cell.value * 100 : cell.value;
    return `${pct.toFixed(1)}%`;
  }
  const currency = (cell.currency || reportingCurrency || "").trim();
  const formatted = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Math.abs(cell.value) >= 100 ? 0 : 2,
  }).format(cell.value);
  return currency ? `${currency} ${formatted}` : formatted;
}

function sourceTitle(cell: DatabookSeriesCell | null): string {
  if (!cell) return "";
  const line = cell.line_item || "Figure";
  const file = sourceFile(cell.source);
  return file ? `${line} — ${file}` : line;
}

function sourceFile(source: string | null | undefined): string {
  if (!source) return "";
  const parts = source.split(/[/\\]/);
  return parts[parts.length - 1] || source;
}
