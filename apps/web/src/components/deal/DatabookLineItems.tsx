"use client";

import { useEffect, useMemo, useState } from "react";
import {
  DEFAULT_PAGE_SIZE,
  ListPagination,
  useClientPagination,
} from "@/components/deal/ListPagination";
import type { DatabookDqIssue, DatabookLineRow, DatabookView } from "@/lib/api";

const DISPLAY_CAP = 4000;

type IssueFilter = "any" | "conflict" | "assumed" | null;

export function DatabookLineItems({
  rows,
  view,
  loading,
}: Readonly<{
  rows: DatabookLineRow[];
  view: DatabookView | null;
  loading?: boolean;
}>) {
  const [q, setQ] = useState("");
  const [unmappedOnly, setUnmappedOnly] = useState(false);
  const [issueFilter, setIssueFilter] = useState<IssueFilter>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  const capped = useMemo(() => rows.slice(0, DISPLAY_CAP), [rows]);

  const chipCounts = useMemo(() => countIssues(capped), [capped]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return capped.filter((row) => {
      if (unmappedOnly && row.metric) return false;
      if (needle && !matchesQuery(row, needle)) return false;
      if (issueFilter === "any" && !(row.dq && row.dq.length > 0)) return false;
      if (
        issueFilter &&
        issueFilter !== "any" &&
        !(row.dq || []).some((d) => d.kind === issueFilter)
      ) {
        return false;
      }
      return true;
    });
  }, [capped, q, unmappedOnly, issueFilter]);

  const pager = useClientPagination(filtered, pageSize);
  const selected =
    selectedKey == null
      ? null
      : filtered.find((r, index) => `${r.key || "row"}::${index}` === selectedKey) ?? null;
  const inventoryTotal = view?.totals.rows ?? rows.length;
  const reportingCurrency = view?.reporting_currency || "";

  useEffect(() => {
    setSelectedKey(null);
  }, [q, unmappedOnly, issueFilter]);

  if (loading) {
    return <p className="text-[13px] text-[#64748b]">Loading line items…</p>;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="text-[15px] font-semibold text-[#0f172a]">All line items</h3>
          <p className="mt-0.5 text-[12px] text-[#64748b]">
            {capped.length < inventoryTotal
              ? `Showing ${capped.length.toLocaleString()} of ${inventoryTotal.toLocaleString()}`
              : `${capped.length.toLocaleString()} rows`}
            {view?.totals.mapped_rows != null
              ? ` · ${view.totals.mapped_rows.toLocaleString()} mapped`
              : null}
            {" · "}
            {capped.filter((r) => !r.metric).length.toLocaleString()} unmapped
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-1.5 text-[12px] text-[#64748b]">
            <input
              type="checkbox"
              checked={unmappedOnly}
              onChange={(e) => setUnmappedOnly(e.target.checked)}
              className="rounded border-[#cbd5e1]"
            />
            unmapped only
          </label>
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="filter by caption or file"
            className="w-56 rounded-md border border-[#e5e7eb] px-2.5 py-1.5 text-[13px] outline-none focus:border-[#1e3a5f]"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip
          active={issueFilter === "any"}
          onClick={() => setIssueFilter(issueFilter === "any" ? null : "any")}
          label={`any issue: ${chipCounts.any.toLocaleString()}`}
        />
        <Chip
          active={issueFilter === "conflict"}
          tone="warn"
          onClick={() =>
            setIssueFilter(issueFilter === "conflict" ? null : "conflict")
          }
          label={`Sources disagree: ${chipCounts.conflict.toLocaleString()}`}
        />
        <Chip
          active={issueFilter === "assumed"}
          tone="warn"
          onClick={() =>
            setIssueFilter(issueFilter === "assumed" ? null : "assumed")
          }
          label={`Assumption made: ${chipCounts.assumed.toLocaleString()}`}
        />
      </div>

      {filtered.length === 0 ? (
        <p className="rounded-lg border border-[#e5e7eb] bg-white py-10 text-center text-[13px] text-[#64748b]">
          {rows.length === 0
            ? "No line items for this deal yet."
            : "No rows match these filters."}
        </p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-[#e5e7eb] bg-white">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-[13px]">
              <thead className="border-b border-[#e5e7eb] text-[11px] uppercase tracking-wide text-[#94a3b8]">
                <tr>
                  <th className="px-3 py-2 font-medium">Line item</th>
                  <th className="px-3 py-2 font-medium">Statement</th>
                  <th className="px-3 py-2 font-medium">Period</th>
                  <th className="px-3 py-2 text-right font-medium">Value</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e5e7eb]">
                {pager.pageItems.map((row, pageIndex) => {
                  const index = pager.page * pageSize + pageIndex;
                  const issues = row.dq || [];
                  const rowKey = `${row.key || "row"}::${index}`;
                  const active = selectedKey === rowKey;
                  return (
                    <tr
                      key={rowKey}
                      className={active ? "bg-[#f8fafc]" : "hover:bg-[#fafafa]"}
                      onClick={() => setSelectedKey(rowKey)}
                    >
                      <td className="px-3 py-2 align-top">
                        <div className="font-medium text-[#0f172a]">{row.line_item}</div>
                        {row.sheet ? (
                          <div className="mt-0.5 text-[11px] text-[#94a3b8]">{row.sheet}</div>
                        ) : null}
                        {issues.length > 0 ? (
                          <div className="mt-1 flex flex-wrap gap-1">
                            {issues.slice(0, 1).map((issue) => (
                              <DqBadge key={issue.n} issue={issue} more={issues.length - 1} />
                            ))}
                          </div>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 align-top text-[#64748b]">
                        {row.statement || "—"}
                      </td>
                      <td className="px-3 py-2 align-top text-[#0f172a]">
                        <span className={row.forecast ? "italic" : undefined}>
                          FY{row.period}
                        </span>
                      </td>
                      <td
                        className={`px-3 py-2 text-right align-top tabular-nums font-medium text-[#0f172a] ${
                          row.forecast ? "italic" : ""
                        }`}
                      >
                        {formatValue(row, reportingCurrency)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <ListPagination
            page={pager.page}
            pageCount={pager.pageCount}
            total={pager.total}
            from={pager.from}
            to={pager.to}
            pageSize={pageSize}
            onPageChange={pager.setPage}
            onPageSizeChange={setPageSize}
          />
        </div>
      )}

      {selected ? (
        <LineDetailDrawer
          row={selected}
          reportingCurrency={reportingCurrency}
          onClose={() => setSelectedKey(null)}
        />
      ) : null}
    </div>
  );
}

function LineDetailDrawer({
  row,
  reportingCurrency,
  onClose,
}: Readonly<{
  row: DatabookLineRow;
  reportingCurrency: string;
  onClose: () => void;
}>) {
  return (
    <aside className="rounded-lg border border-[#e5e7eb] bg-[#f8fafc] px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="text-[13px] font-semibold text-[#0f172a]">{row.line_item}</h4>
          <p className="mt-0.5 text-[12px] text-[#64748b]">
            {row.sheet ? `${row.sheet} · ` : ""}
            {row.statement || "statement"} · FY{row.period}
            {row.forecast ? " (forecast)" : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-[#e5e7eb] bg-white px-2 py-1 text-[12px] text-[#64748b]"
        >
          Close
        </button>
      </div>
      <dl className="mt-3 grid gap-2 text-[13px] sm:grid-cols-2">
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Value</dt>
          <dd className="font-medium text-[#0f172a]">
            {formatValue(row, reportingCurrency)}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Metric</dt>
          <dd className="text-[#0f172a]">{row.metric || "(unmapped)"}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Source</dt>
          <dd className="break-all text-[#0f172a]">{row.source || "—"}</dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Cell</dt>
          <dd className="font-mono text-[12px] text-[#0f172a]">
            {row.token || row.block || "—"}
          </dd>
        </div>
        <div>
          <dt className="text-[11px] uppercase tracking-wide text-[#94a3b8]">Fact id</dt>
          <dd className="font-mono text-[12px] text-[#0f172a]">{row.fact_id || "—"}</dd>
        </div>
      </dl>
      {(row.dq || []).length > 0 ? (
        <ul className="mt-3 space-y-1.5">
          {(row.dq || []).map((issue) => (
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
      {row.source ? (
        <p className="mt-3 text-[12px] text-[#64748b]" title="Show this line in its document">
          Document: <span className="text-[#0f172a]">{row.source}</span>
          {row.token ? ` · ${row.token}` : ""}
        </p>
      ) : null}
    </aside>
  );
}

function Chip({
  label,
  active,
  tone = "neutral",
  onClick,
}: Readonly<{
  label: string;
  active: boolean;
  tone?: "neutral" | "warn";
  onClick: () => void;
}>) {
  let base = "border-[#e5e7eb] bg-white text-[#64748b] hover:bg-[#f8fafc]";
  if (tone === "warn" && active) {
    base = "border-[#fb923c] bg-[#ffedd5] text-[#9a3412]";
  } else if (tone === "warn") {
    base = "border-[#fed7aa] bg-white text-[#c2410c] hover:bg-[#fff7ed]";
  } else if (active) {
    base = "border-[#1e3a5f] bg-[#e2e8f0] text-[#0f172a]";
  }
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-2.5 py-1 text-[12px] font-medium ${base}`}
    >
      {label}
    </button>
  );
}

function DqBadge({
  issue,
  more,
}: Readonly<{ issue: DatabookDqIssue; more: number }>) {
  const suffix = more > 0 ? ` +${more} more` : "";
  return (
    <span className="inline-flex rounded bg-[#ffedd5] px-1.5 py-0.5 text-[10px] font-semibold text-[#c2410c]">
      #{issue.n} {issue.label}
      {suffix}
    </span>
  );
}

function matchesQuery(row: DatabookLineRow, needle: string): boolean {
  const hay = [row.line_item, row.source, row.raw, row.sheet, row.metric]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return hay.includes(needle);
}

function countIssues(rows: DatabookLineRow[]) {
  let any = 0;
  let conflict = 0;
  let assumed = 0;
  for (const row of rows) {
    const dq = row.dq || [];
    if (dq.length === 0) continue;
    any += 1;
    if (dq.some((d) => d.kind === "conflict")) conflict += 1;
    if (dq.some((d) => d.kind === "assumed")) assumed += 1;
  }
  return { any, conflict, assumed };
}

function formatValue(row: DatabookLineRow, reportingCurrency: string): string {
  if (row.value == null || !Number.isFinite(row.value)) return "—";
  if (row.kind === "percent" || row.unit === "%") {
    const pct = Math.abs(row.value) <= 1 ? row.value * 100 : row.value;
    return `${pct.toFixed(1)}%`;
  }
  const currency = (row.currency || reportingCurrency || "").trim();
  const formatted = new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Math.abs(row.value) >= 100 ? 0 : 2,
  }).format(row.value);
  return currency ? `${currency} ${formatted}` : formatted;
}
