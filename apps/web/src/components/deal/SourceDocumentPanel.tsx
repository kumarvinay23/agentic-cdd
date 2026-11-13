"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  vdrPreviewRequest,
  type DatabookDqIssue,
  type DatabookRow,
  type VdrPreview,
} from "@/lib/api";

export type SourceTarget = {
  filename: string;
  sheet?: string | null;
  line?: string | null;
  metric?: string;
  year?: number;
  row?: number | null;
  col?: number | null;
};

export function FigureSourceTip({
  x,
  y,
  title,
  readFrom,
  issues,
}: Readonly<{
  x: number;
  y: number;
  title: string;
  readFrom: string;
  issues: DatabookDqIssue[];
}>) {
  const left = Math.max(8, Math.min(x, typeof window !== "undefined" ? window.innerWidth - 360 : x));
  return (
    <div
      className="pointer-events-none fixed z-50 w-[340px] rounded-md border border-[#e5e7eb] bg-white px-3 py-2.5 text-left shadow-lg"
      style={{ top: y, left }}
    >
      <p className="text-[13px] font-semibold text-[#0f172a]">{title}</p>
      <p className="mt-1.5 text-[12px] text-[#64748b]">read from: {readFrom || "—"}</p>
      {issues.length > 0 ? (
        <div className="mt-2 text-[12px] text-[#0f172a]">
          <p className="font-semibold">Data quality:</p>
          <ul className="mt-1 space-y-1.5">
            {issues.map((issue) => (
              <li key={issue.n}>
                <span className="font-semibold">
                  #{issue.n} {issue.label}
                </span>
                {issue.detail ? (
                  <span className="mt-0.5 block whitespace-pre-line text-[#64748b]">{issue.detail}</span>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function SourceDocumentPanel({
  accessToken,
  dealId,
  target,
  rows,
  onClose,
}: Readonly<{
  accessToken?: string;
  dealId: string;
  target: SourceTarget;
  rows: DatabookRow[];
  onClose: () => void;
}>) {
  const [sheet, setSheet] = useState(target.sheet || "");
  const [active, setActive] = useState(target);
  const [preview, setPreview] = useState<VdrPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const placeRef = useRef<HTMLTableRowElement | null>(null);

  const figures = useMemo(
    () => rows.filter((row) => row.source_name === target.filename),
    [rows, target.filename],
  );

  useEffect(() => {
    setSheet(target.sheet || "");
    setActive(target);
  }, [target]);

  useEffect(() => {
    if (!accessToken) return;
    let cancel = false;
    setLoading(true);
    setError(null);
    vdrPreviewRequest(accessToken, dealId, target.filename, sheet || null)
      .then((res) => {
        if (!cancel) setPreview(res.data);
      })
      .catch((err: unknown) => {
        if (!cancel) setError(err instanceof Error ? err.message : "Could not open this document");
      })
      .finally(() => {
        if (!cancel) setLoading(false);
      });
    return () => {
      cancel = true;
    };
  }, [accessToken, dealId, target.filename, sheet]);

  const grid = preview?.rows ?? [];
  const place = findPlace(grid, active.line || "", active.row);
  useEffect(() => {
    placeRef.current?.scrollIntoView({ block: "center" });
  }, [place, preview]);

  return (
    <div className="fixed inset-0 z-40 flex items-stretch justify-center bg-[#0f172a]/40 p-4">
      <div className="flex min-h-0 w-full max-w-6xl overflow-hidden rounded-lg border border-[#e5e7eb] bg-white shadow-xl">
        <aside className="flex w-[340px] shrink-0 flex-col border-r border-[#e5e7eb]">
          <div className="border-b border-[#e5e7eb] px-4 py-3">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-[#94a3b8]">Derived data</p>
            <h3 className="mt-1 truncate text-[13px] font-semibold text-[#0f172a]" title={target.filename}>
              {target.filename}
            </h3>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
            <p className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#94a3b8]">
              Figures read from this document ({figures.length})
            </p>
            {figures.length === 0 ? (
              <p className="px-2 py-3 text-[12px] text-[#64748b]">No working-store rows from this file.</p>
            ) : (
              <ul>
                {figures.map((row) => {
                  const selected =
                    row.metric_key === active.metric &&
                    row.fiscal_year === active.year &&
                    row.caption === active.line;
                  return (
                    <li key={row.row_id}>
                      <button
                        type="button"
                        onClick={() => {
                          setActive({
                            filename: row.source_name,
                            sheet: row.table_name || row.source_ref?.table || "",
                            line: row.caption,
                            metric: row.metric_key || undefined,
                            year: row.fiscal_year ?? undefined,
                            row: row.source_ref?.row,
                            col: row.source_ref?.col,
                          });
                          const nextSheet = row.table_name || row.source_ref?.table || "";
                          if (nextSheet) setSheet(nextSheet);
                        }}
                        className={`w-full rounded px-2 py-1.5 text-left text-[12px] ${
                          selected ? "bg-[#e0f2fe] text-[#0f172a]" : "hover:bg-[#f8fafc] text-[#334155]"
                        }`}
                      >
                        <span className="font-medium">{row.caption}</span>
                        <span className="mt-0.5 block text-[11px] text-[#64748b]">
                          {row.metric_key || "unmapped"}
                          {row.fiscal_year ? ` · FY${row.fiscal_year}` : ""} · {formatFig(row.value)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </aside>
        <section className="flex min-w-0 flex-1 flex-col">
          <header className="flex items-center justify-between gap-3 border-b border-[#e5e7eb] px-4 py-3">
            <div className="min-w-0">
              <h3 className="truncate text-[14px] font-semibold text-[#0f172a]">{target.filename}</h3>
              <p className="mt-0.5 text-[12px] text-[#64748b]">
                {active.line
                  ? place == null
                    ? "Place not located"
                    : `${preview?.active_sheet || sheet || "Sheet"} · ${active.line}`
                  : "Source document"}
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-[#e5e7eb] px-2 py-1 text-[12px] text-[#64748b]"
            >
              Close
            </button>
          </header>
          <div className="flex items-center gap-2 border-b border-[#e5e7eb] px-4 py-2">
            {(preview?.sheets || []).length > 1 ? (
              <label className="text-[12px] text-[#64748b]">
                Sheet{" "}
                <select
                  value={preview?.active_sheet || sheet}
                  onChange={(e) => setSheet(e.target.value)}
                  className="ml-1 rounded border border-[#e5e7eb] px-2 py-1 text-[12px] text-[#0f172a]"
                >
                  {(preview?.sheets || []).map((name) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            ) : (
              <span className="text-[12px] text-[#64748b]">{preview?.active_sheet || sheet || "Document"}</span>
            )}
          </div>
          <div className="min-h-0 flex-1 overflow-auto px-4 py-3">
            {loading ? <p className="text-[13px] text-[#64748b]">Opening document…</p> : null}
            {error ? <p className="text-[13px] text-[#b45309]">{error}</p> : null}
            {!loading && !error && grid.length > 0 ? (
              <table className="w-full border-collapse text-left text-[12px]">
                <tbody>
                  {grid.map((row, index) => (
                    <tr
                      key={index}
                      ref={index === place ? placeRef : undefined}
                      className={index === place ? "bg-[#fef3c7]" : undefined}
                    >
                      {row.map((cell, col) => (
                        <td key={col} className="border border-[#f1f5f9] px-2 py-1 align-top text-[#0f172a]">
                          {cell}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : null}
            {!loading && !error && preview?.text ? (
              <pre className="whitespace-pre-wrap text-[12px] text-[#0f172a]">{preview.text}</pre>
            ) : null}
            {!loading && !error && (preview?.blocks || []).length > 0 ? (
              <div className="space-y-2 text-[13px] text-[#0f172a]">
                {(preview?.blocks || []).map((block, index) =>
                  block.text ? <p key={index}>{block.text}</p> : null,
                )}
              </div>
            ) : null}
            {!loading && !error && preview?.note ? (
              <p className="text-[13px] text-[#64748b]">{preview.note}</p>
            ) : null}
          </div>
        </section>
      </div>
    </div>
  );
}

function findPlace(rows: string[][], line: string, excelRow?: number | null): number | null {
  const needle = line.trim().toLowerCase();
  if (needle) {
    const exact = rows.findIndex((row) => row.some((cell) => cell.trim().toLowerCase() === needle));
    if (exact >= 0) return exact;
    const loose = rows.findIndex((row) => row.some((cell) => cell.toLowerCase().includes(needle)));
    if (loose >= 0) return loose;
  }
  if (excelRow != null && excelRow > 0 && excelRow - 1 < rows.length) return excelRow - 1;
  return null;
}

function formatFig(value: number): string {
  if (!Number.isFinite(value)) return "—";
  return value.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
