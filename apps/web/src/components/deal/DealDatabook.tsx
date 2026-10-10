"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DataQualityReview } from "@/components/deal/DataQualityReview";
import {
  DEFAULT_PAGE_SIZE,
  ListPagination,
  useClientPagination,
} from "@/components/deal/ListPagination";
import { ValidationPackReview } from "@/components/deal/ValidationPackReview";
import {
  ApiError,
  databookAcceptConflictRequest,
  databookConfirmRequest,
  databookCorrectRequest,
  databookDeepRequest,
  databookDropRequest,
  databookExcludeRequest,
  databookExportExcelRequest,
  databookExportPromotedCsv,
  databookFindingsRequest,
  databookImportExcelRequest,
  databookReleaseRequest,
  databookRemapRequest,
  databookRescanRequest,
  databookRereadRequest,
  databookRowsRequest,
  databookSummaryRequest,
  databookValidationPackRequest,
  databookVouchRequest,
  dataQualityRequest,
  type DatabookFinding,
  type DatabookRow,
  type DatabookSummary,
  type DataQualityCandidate,
  type DataQualityItem,
  type DataQualityPayload,
  type ValidationCard,
  type ValidationPack,
} from "@/lib/api";

type Tab = "files" | "derived" | "findings" | "quality" | "pack";

export function DealDatabook({
  dealId,
  accessToken,
  onError,
}: {
  dealId: string;
  accessToken?: string;
  onError: (msg: string | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("quality");
  const [summary, setSummary] = useState<DatabookSummary | null>(null);
  const [rows, setRows] = useState<DatabookRow[]>([]);
  const [findings, setFindings] = useState<DatabookFinding[]>([]);
  const [quality, setQuality] = useState<DataQualityPayload | null>(null);
  const [pack, setPack] = useState<ValidationPack | null>(null);
  const [loading, setLoading] = useState(true);
  const [rescanning, setRescanning] = useState(false);
  const [deepRunning, setDeepRunning] = useState(false);
  const [releasing, setReleasing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [selectedRowId, setSelectedRowId] = useState<string | null>(null);
  const [rereadFile, setRereadFile] = useState("");
  const [materialOnly, setMaterialOnly] = useState(true);
  const [importing, setImporting] = useState(false);
  const importInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    onError(null);
    try {
      const [sum, dq, rowRes, findRes, packRes] = await Promise.all([
        databookSummaryRequest(accessToken, dealId),
        dataQualityRequest(accessToken, dealId),
        databookRowsRequest(accessToken, dealId, { material: materialOnly }),
        databookFindingsRequest(accessToken, dealId),
        databookValidationPackRequest(accessToken, dealId).catch(() => null),
      ]);
      setSummary(sum.data);
      setQuality(dq);
      setRows(rowRes.data.items);
      setFindings(findRes.data.items);
      setPack(packRes?.data ?? null);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Failed to load Databook");
    } finally {
      setLoading(false);
    }
  }, [accessToken, dealId, materialOnly, onError]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const requireReason = () => {
    const text = reason.trim();
    if (text.length < 3) {
      onError("Enter a reason (at least 3 characters). Correcting ≠ vouching.");
      return null;
    }
    return text;
  };

  const onRescan = async () => {
    if (!accessToken) return;
    setRescanning(true);
    onError(null);
    try {
      const res = await databookRescanRequest(accessToken, dealId);
      setSummary(res.data);
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Rescan failed");
    } finally {
      setRescanning(false);
    }
  };

  const onDeep = async () => {
    if (!accessToken) return;
    setDeepRunning(true);
    onError(null);
    try {
      const res = await databookDeepRequest(accessToken, dealId);
      setSummary(res.data);
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Deep re-extract failed");
    } finally {
      setDeepRunning(false);
    }
  };

  const onRelease = async () => {
    if (!accessToken) return;
    setReleasing(true);
    onError(null);
    try {
      const res = await databookReleaseRequest(accessToken, dealId);
      setSummary(res.data.summary);
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Release failed");
    } finally {
      setReleasing(false);
    }
  };

  const onExportCsv = async () => {
    if (!accessToken) return;
    onError(null);
    try {
      await databookExportPromotedCsv(accessToken, dealId, { material: materialOnly });
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "CSV export failed");
    }
  };

  const onExportExcel = async () => {
    if (!accessToken) return;
    onError(null);
    try {
      await databookExportExcelRequest(accessToken, dealId);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Excel export failed");
    }
  };

  const onImportExcel = async (file: File | null) => {
    if (!accessToken || !file) return;
    setImporting(true);
    onError(null);
    try {
      const res = await databookImportExcelRequest(
        accessToken,
        dealId,
        file,
        reason.trim() || undefined,
      );
      if (res.data.summary) setSummary(res.data.summary);
      await refresh();
      onError(
        res.data.applied > 0
          ? null
          : res.data.errors > 0
            ? `Import finished with ${res.data.errors} error(s), ${res.data.skipped} skipped`
            : null,
      );
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Excel import failed");
    } finally {
      setImporting(false);
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };

  const onUpdateDatabook = async () => {
    await onRescan();
  };

  const runAction = async (fn: () => Promise<unknown>) => {
    if (!accessToken) return;
    setBusy(true);
    onError(null);
    try {
      await fn();
      setReason("");
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  const onAccept = async (item: Extract<DataQualityItem, { kind: "conflict" }>, cand?: DataQualityCandidate) => {
    const why = requireReason();
    if (!why || !accessToken || item.fiscal_year == null) return;
    const value = cand?.value ?? item.chosen;
    if (value == null) return;
    await runAction(() =>
      databookAcceptConflictRequest(accessToken, dealId, {
        reason: why,
        metric_key: item.metric,
        fiscal_year: item.fiscal_year as number,
        value: Number(value),
        row_id: cand?.row_ids?.[0],
      }),
    );
  };

  const onDropRow = async (rowId: string) => {
    const why = requireReason();
    if (!why || !accessToken) return;
    await runAction(() => databookDropRequest(accessToken, dealId, rowId, why));
  };

  const onVouchRow = async (rowId: string) => {
    const why = requireReason();
    if (!why || !accessToken) return;
    await runAction(() => databookVouchRequest(accessToken, dealId, rowId, why));
  };

  const onCorrectRow = async (row: DatabookRow) => {
    const why = requireReason();
    if (!why || !accessToken) return;
    const raw = window.prompt("Corrected value (leave blank to keep current)", String(row.value));
    if (raw == null) return;
    const value = raw.trim() === "" ? undefined : Number(raw);
    if (value != null && !Number.isFinite(value)) {
      onError("Invalid number");
      return;
    }
    await runAction(() =>
      databookCorrectRequest(accessToken, dealId, row.row_id, {
        reason: why,
        value,
      }),
    );
  };

  const onConfirmCard = async (card: ValidationCard) => {
    const why = requireReason();
    if (!why || !accessToken || !card.row_id) return;
    await runAction(() => databookConfirmRequest(accessToken, dealId, card.row_id!, why));
  };

  const onExcludeCard = async (card: ValidationCard) => {
    const why = requireReason();
    if (!why || !accessToken || !card.row_id) return;
    await runAction(() => databookExcludeRequest(accessToken, dealId, card.row_id!, why));
  };

  const onRemapCard = async (card: ValidationCard) => {
    const why = requireReason();
    if (!why || !accessToken || !card.row_id) return;
    const metric = window.prompt("Remap to metric_key", card.metric_key || "revenue");
    if (metric == null || !metric.trim()) return;
    await runAction(() =>
      databookRemapRequest(accessToken, dealId, card.row_id!, {
        reason: why,
        metric_key: metric.trim(),
      }),
    );
  };

  const onAcceptAltCard = async (card: ValidationCard, value: number, rowId?: string) => {
    const why = requireReason();
    if (!why || !accessToken) return;
    await runAction(() =>
      databookAcceptConflictRequest(accessToken, dealId, {
        reason: why,
        metric_key: card.metric_key,
        fiscal_year: card.fiscal_year,
        value,
        row_id: rowId || card.row_id || undefined,
      }),
    );
  };

  const onReread = async () => {
    const filename = rereadFile.trim();
    if (!filename || !accessToken) {
      onError("Enter a VDR filename to re-read");
      return;
    }
    await onRereadNamed(filename);
  };

  const onRereadNamed = async (filename: string) => {
    if (!filename.trim() || !accessToken) {
      onError("Enter a VDR filename to re-read");
      return;
    }
    setBusy(true);
    onError(null);
    try {
      await databookRereadRequest(accessToken, dealId, filename.trim());
      setRereadFile("");
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Re-read failed");
    } finally {
      setBusy(false);
    }
  };

  const flags = summary?.flags || {};
  const needsReview = quality?.summary?.needs_review ?? 0;
  const packTotal = pack?.counts?.total ?? summary?.validation_pack?.counts?.total ?? 0;
  const heldRows = rows.filter((r) => r.status === "held_out" || r.status === "candidate");
  const freshness = summary?.freshness;
  const upToDate = freshness?.up_to_date === true;

  const [derivedPageSize, setDerivedPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [findingsPageSize, setFindingsPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [filesPageSize, setFilesPageSize] = useState(DEFAULT_PAGE_SIZE);
  const derivedPager = useClientPagination(rows, derivedPageSize);
  const findingsPager = useClientPagination(findings, findingsPageSize);
  const filesSorted = useMemo(
    () => [...findings].sort((a, b) => triageRank(a.triage) - triageRank(b.triage)),
    [findings],
  );
  const filesPager = useClientPagination(filesSorted, filesPageSize);

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-[22px] font-semibold tracking-tight text-[#0f172a]">Databook</h2>
          <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-[#64748b]">
            Working store for review; reports consume the <em>released</em> snapshot (proven /
            doubtful / missing). Rescan and HITL decisions auto-publish a new release.
          </p>
          {summary?.release ? (
            <p className="mt-1 text-[12px] text-[#0f172a]">
              Current release{" "}
              <span className="font-medium">{summary.release.release_id}</span>
              {" · "}
              {summary.release.counts?.proven ?? 0} proven
              {" · "}
              {summary.release.counts?.doubtful ?? 0} doubtful
              {" · "}
              {summary.release.counts?.missing ?? 0} missing
              {(summary.release.request_count ?? summary.release.counts?.requests ?? 0) > 0
                ? ` · ${summary.release.request_count ?? summary.release.counts?.requests} open requests`
                : null}
            </p>
          ) : (
            <p className="mt-1 text-[12px] text-[#b45309]">
              No release yet — reports will withhold material agent figures until Rescan or Release.
            </p>
          )}
          {freshness?.stale_reason ? (
            <p className="mt-1 text-[12px] text-[#b45309]">{freshness.stale_reason}</p>
          ) : summary?.meta?.last_rescan_at || summary?.meta?.last_deep_at ? (
            <p className="mt-1 text-[11px] text-[#94a3b8]">
              {summary.meta.last_rescan_at ? `Last Rescan ${summary.meta.last_rescan_at}` : null}
              {summary.meta.last_rescan_at && summary.meta.last_deep_at ? " · " : null}
              {summary.meta.last_deep_at ? `Last Deep ${summary.meta.last_deep_at}` : null}
              {summary.release?.created_at ? ` · Released ${summary.release.created_at}` : null}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-1.5 text-[12px] text-[#64748b]">
            <input
              type="checkbox"
              checked={materialOnly}
              onChange={(e) => setMaterialOnly(e.target.checked)}
              className="rounded border-[#cbd5e1]"
            />
            Material metrics
          </label>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={loading || !accessToken}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-[13px] font-medium text-[#334155] hover:bg-[#f8fafc] disabled:opacity-60"
            title="Reload UI state only — does not re-extract"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={() => void onExportExcel()}
            disabled={!accessToken || busy || importing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-[13px] font-medium text-[#334155] hover:bg-[#f8fafc] disabled:opacity-60"
          >
            Export to Excel
          </button>
          <input
            ref={importInputRef}
            type="file"
            accept=".xlsx,.xlsm,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            onChange={(e) => void onImportExcel(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            onClick={() => importInputRef.current?.click()}
            disabled={!accessToken || busy || importing}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-[13px] font-medium text-[#334155] hover:bg-[#f8fafc] disabled:opacity-60"
            title="Upload an Excel file previously exported from Databook"
          >
            {importing ? "Importing…" : "Import edited Excel"}
          </button>
          <button
            type="button"
            onClick={() => void onExportCsv()}
            disabled={!accessToken || busy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#e5e7eb] bg-white px-3 py-2 text-[13px] font-medium text-[#334155] hover:bg-[#f8fafc] disabled:opacity-60"
          >
            Export CSV
          </button>
          <button
            type="button"
            onClick={() => void onRelease()}
            disabled={releasing || rescanning || deepRunning || !accessToken}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#0f766e] bg-white px-3 py-2 text-[13px] font-medium text-[#0f766e] hover:bg-[#f0fdfa] disabled:opacity-60"
            title="Publish an immutable release from the working store for reports"
          >
            {releasing ? "Releasing…" : "Release"}
          </button>
          <button
            type="button"
            onClick={() => void onDeep()}
            disabled={deepRunning || rescanning || !accessToken}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[#1e3a5f] bg-white px-3 py-2 text-[13px] font-medium text-[#1e3a5f] hover:bg-[#f1f5f9] disabled:opacity-60"
            title="Discard cached library text and re-read all VDR originals"
          >
            {deepRunning ? "Deep…" : "Deep"}
          </button>
          <button
            type="button"
            onClick={() => void onUpdateDatabook()}
            disabled={rescanning || deepRunning || !accessToken}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-2 text-[13px] font-medium disabled:opacity-60 ${
              upToDate
                ? "border border-[#93c5fd] bg-[#dbeafe] text-[#1e3a5f] hover:bg-[#bfdbfe]"
                : "bg-[#1e3a5f] text-white hover:bg-[#16304f]"
            }`}
            title={
              upToDate
                ? "Databook matches the current library — click to Rescan anyway"
                : freshness?.stale_reason || "Rescan library into Databook"
            }
          >
            {rescanning
              ? "Updating…"
              : upToDate
                ? "Databook is up to date"
                : freshness?.label || "Update databook"}
          </button>
        </div>
      </header>

      <div className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2.5">
        <label className="block text-[11px] font-medium uppercase tracking-wide text-[#94a3b8]">
          Decision reason (required for Accept / Correct / Drop / Vouch)
        </label>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Commercial DD is the governing source for FY revenue"
          className="mt-1 w-full rounded-md border border-[#e5e7eb] px-2.5 py-1.5 text-[13px] outline-none focus:border-[#1e3a5f]"
        />
      </div>

      <div className="flex flex-wrap gap-6 border-b border-[#e5e7eb] text-[13px]">
        {(
          [
            ["quality", `Needs review (${needsReview})`],
            ["pack", `Validation pack (${packTotal})`],
            ["derived", `Derived data (${rows.length})`],
            ["findings", `Findings (${findings.length})`],
            ["files", "Uploaded files"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`-mb-px border-b-2 pb-2 font-medium ${
              tab === id ? "border-[#1e3a5f] text-[#0f172a]" : "border-transparent text-[#64748b]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
        {[
          ["Conflicts", flags.conflict ?? 0],
          ["Failed checks", flags.failed_check ?? 0],
          ["Dropped", flags.dropped ?? 0],
          ["Held out", flags.held_out ?? 0],
          ["Promoted", flags.promoted ?? 0],
          ["Vouched", flags.vouched ?? 0],
        ].map(([label, value]) => (
          <div key={label as string} className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-2.5">
            <div className="text-[11px] uppercase tracking-wide text-[#94a3b8]">{label}</div>
            <div className="mt-0.5 text-[20px] font-semibold text-[#0f172a]">{value}</div>
          </div>
        ))}
      </div>

      {loading ? <p className="text-[13px] text-[#64748b]">Loading Databook…</p> : null}

      {!loading && tab === "quality" ? (
        <section className="space-y-3">
          <DataQualityReview
            quality={quality}
            busy={busy}
            onAcceptConflict={(item, cand) => void onAccept(item, cand)}
            showActions
          />
        </section>
      ) : null}

      {!loading && tab === "pack" ? (
        <section className="space-y-3">
          <p className="text-[13px] text-[#64748b]">
            Post-run review only — confirm, remap, or exclude after Release. Enter a reason above
            first. Calibration cards check that proven cells still look right.
          </p>
          <ValidationPackReview
            pack={pack}
            busy={busy}
            accessToken={accessToken}
            dealId={dealId}
            onConfirm={(card) => void onConfirmCard(card)}
            onExclude={(card) => void onExcludeCard(card)}
            onRemap={(card) => void onRemapCard(card)}
            onAcceptAlt={(card, value, rowId) => void onAcceptAltCard(card, value, rowId)}
          />
        </section>
      ) : null}

      {!loading && tab === "derived" ? (
        <section className="space-y-3">
          <p className="text-[13px] text-[#64748b]">
            Select a held-out / candidate row, then Correct, Drop, or Vouch with a reason above.
          </p>
          <div className="overflow-hidden rounded-lg border border-[#e5e7eb] bg-white">
            <table className="w-full text-left text-[13px]">
              <thead className="border-b border-[#e5e7eb] text-[11px] uppercase tracking-wide text-[#94a3b8]">
                <tr>
                  <th className="px-3 py-2 pr-2 font-medium" />
                  <th className="py-2 pr-3 font-medium">Caption</th>
                  <th className="py-2 pr-3 font-medium">Metric</th>
                  <th className="py-2 pr-3 font-medium">FY</th>
                  <th className="py-2 pr-3 font-medium">Value</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Source</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#e5e7eb]">
                {derivedPager.pageItems.map((row) => (
                  <tr
                    key={row.row_id}
                    className={selectedRowId === row.row_id ? "bg-[#f8fafc]" : undefined}
                    onClick={() => setSelectedRowId(row.row_id)}
                  >
                    <td className="px-3 py-2 pr-2">
                      <input
                        type="radio"
                        name="databook-row"
                        checked={selectedRowId === row.row_id}
                        onChange={() => setSelectedRowId(row.row_id)}
                      />
                    </td>
                    <td className="py-2 pr-3 text-[#0f172a]">{row.caption}</td>
                    <td className="py-2 pr-3 text-[#64748b]">{row.metric_key || "—"}</td>
                    <td className="py-2 pr-3">{row.fiscal_year ?? "—"}</td>
                    <td className="py-2 pr-3 font-medium">{formatNum(row.value)}</td>
                    <td className="py-2 pr-3">
                      <StatusPill status={row.status} />
                    </td>
                    <td className="py-2 pr-3 text-[#64748b]">{row.source_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <ListPagination
              page={derivedPager.page}
              pageCount={derivedPager.pageCount}
              total={derivedPager.total}
              from={derivedPager.from}
              to={derivedPager.to}
              pageSize={derivedPageSize}
              onPageChange={derivedPager.setPage}
              onPageSizeChange={setDerivedPageSize}
            />
          </div>
          {selectedRowId ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  const row = rows.find((r) => r.row_id === selectedRowId);
                  if (row) void onCorrectRow(row);
                }}
                className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-[12px] font-medium text-[#0f172a] hover:bg-[#f8fafc] disabled:opacity-50"
              >
                Correct
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onDropRow(selectedRowId)}
                className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-[12px] font-medium text-[#0f172a] hover:bg-[#f8fafc] disabled:opacity-50"
              >
                Drop
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onVouchRow(selectedRowId)}
                className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-[12px] font-medium text-[#0f172a] hover:bg-[#f8fafc] disabled:opacity-50"
              >
                Vouch
              </button>
              <span className="self-center text-[11px] text-[#94a3b8]">
                {heldRows.some((r) => r.row_id === selectedRowId)
                  ? "Held-out / candidate selected"
                  : "Already decided rows can still be corrected"}
              </span>
            </div>
          ) : null}
          {rows.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-[#64748b]">No derived rows yet.</p>
          ) : null}
        </section>
      ) : null}

      {!loading && tab === "findings" ? (
        <section className="space-y-2">
          <p className="text-[13px] text-[#64748b]">
            Trust ledger by file (Phase 1 classify: set-aside, forecast-only, source basis / ladder). Silence is
            not a pass — a file with no statement-block checks is not cleared.
          </p>
          {(flags.set_aside || flags.forecast_only) ? (
            <p className="text-[12px] text-[#b45309]">
              {flags.set_aside || 0} set aside · {flags.forecast_only || 0} forecast-only ·{" "}
              {flags.history_source || 0} history sources
            </p>
          ) : null}
          {findings.length === 0 ? (
            <p className="py-8 text-center text-[13px] text-[#64748b]">No findings yet.</p>
          ) : (
            <div className="overflow-hidden rounded-lg border border-[#e5e7eb] bg-white">
              <div className="divide-y divide-[#e5e7eb]">
                {findingsPager.pageItems.map((f) => (
                  <div key={f.source_name} className="px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="font-medium text-[#0f172a]">{f.source_name}</div>
                      {f.triage === "document_request" ? null : (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => {
                            setRereadFile(f.source_name);
                            setTab("files");
                          }}
                          className="text-[12px] font-medium text-[#1e3a5f] hover:underline"
                        >
                          Re-read…
                        </button>
                      )}
                    </div>
                    <div className="mt-1.5 flex flex-wrap gap-1.5">
                      {(f.flags || []).map((flag) => (
                        <span
                          key={flag}
                          className="rounded bg-[#f8fafc] px-1.5 py-0.5 text-[11px] font-medium text-[#475569]"
                        >
                          {triageLabel(flag)}
                        </span>
                      ))}
                      {f.triage ? (
                        <span className="rounded bg-[#fef3c7] px-1.5 py-0.5 text-[11px] font-medium text-[#92400e]">
                          Triage: {triageLabel(f.triage)}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-[12px] text-[#64748b]">
                      {f.checks_total
                        ? `${f.checks_failed ?? 0}/${f.checks_total} checks failed`
                        : "No checks"}{" "}
                      · {f.held_out} held out · {f.promoted} promoted · {f.conflicts} conflicts
                      {f.basis ? ` · ${f.basis}` : ""}
                      {f.ladder_score != null ? ` (ladder ${f.ladder_score})` : ""}
                    </p>
                    <p className="mt-1 text-[11px] text-[#94a3b8]">{f.note}</p>
                  </div>
                ))}
              </div>
              <ListPagination
                page={findingsPager.page}
                pageCount={findingsPager.pageCount}
                total={findingsPager.total}
                from={findingsPager.from}
                to={findingsPager.to}
                pageSize={findingsPageSize}
                onPageChange={findingsPager.setPage}
                onPageSizeChange={setFindingsPageSize}
              />
            </div>
          )}
        </section>
      ) : null}

      {!loading && tab === "files" ? (
        <section className="space-y-3">
          <p className="text-[13px] text-[#64748b]">
            Uploaded-files queue in triage order (set-aside → forecast → assumption → failed check → sources
            disagree → unread → not landed). Re-read re-extracts one VDR file, then Rescans Databook.
          </p>
          <div className="overflow-hidden rounded-lg border border-[#e5e7eb] bg-white">
            <div className="divide-y divide-[#e5e7eb]">
              {filesPager.pageItems.map((f) => (
                <div
                  key={`file-${f.source_name}`}
                  className="flex flex-wrap items-center justify-between gap-2 px-4 py-3"
                >
                  <div>
                    <div className="font-medium text-[#0f172a]">{f.source_name}</div>
                    <p className="mt-0.5 text-[12px] text-[#64748b]">
                      {f.triage ? triageLabel(f.triage) : "Clear"} · {f.note}
                    </p>
                  </div>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void onRereadNamed(f.source_name)}
                    className="rounded-lg border border-[#e5e7eb] bg-white px-3 py-1.5 text-[12px] font-medium text-[#0f172a] hover:bg-[#f8fafc] disabled:opacity-50"
                  >
                    Re-read
                  </button>
                </div>
              ))}
            </div>
            <ListPagination
              page={filesPager.page}
              pageCount={filesPager.pageCount}
              total={filesPager.total}
              from={filesPager.from}
              to={filesPager.to}
              pageSize={filesPageSize}
              onPageChange={filesPager.setPage}
              onPageSizeChange={setFilesPageSize}
            />
          </div>
          <div className="flex flex-wrap gap-2 rounded-lg border border-[#e5e7eb] bg-white px-4 py-4">
            <input
              value={rereadFile}
              onChange={(e) => setRereadFile(e.target.value)}
              placeholder="Or type a VDR filename…"
              className="min-w-[280px] flex-1 rounded-md border border-[#e5e7eb] px-2.5 py-1.5 text-[13px]"
            />
            <button
              type="button"
              disabled={busy || !rereadFile.trim()}
              onClick={() => void onReread()}
              className="rounded-lg bg-[#1e3a5f] px-3 py-1.5 text-[13px] font-medium text-white disabled:opacity-50"
            >
              Re-read file
            </button>
          </div>
        </section>
      ) : null}
    </div>
  );
}

function triageLabel(flag: string): string {
  switch (flag) {
    case "document_request":
      return "Document request";
    case "set_aside":
      return "Set aside";
    case "forecast_only":
      return "Forecast only";
    case "assumption":
      return "Assumption made";
    case "sources_disagree":
      return "Sources disagree";
    case "unread":
      return "Unread";
    case "not_landed":
      return "Not landed";
    case "failed_check":
      return "Failed its check";
    default:
      return flag;
  }
}

function triageRank(triage: string | null | undefined): number {
  const order = [
    "set_aside",
    "forecast_only",
    "assumption",
    "failed_check",
    "sources_disagree",
    "unread",
    "not_landed",
  ];
  if (!triage) return 99;
  const idx = order.indexOf(triage);
  return idx >= 0 ? idx : 50;
}

function formatNum(value: unknown): string {
  if (value == null || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return String(value);
  if (Math.abs(n) >= 1_000_000) return n.toLocaleString("en-US", { maximumFractionDigits: 0 });
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "promoted" || status === "vouched"
      ? "bg-[#ecfdf3] text-[#15803d]"
      : status === "held_out"
        ? "bg-[#fef3c7] text-[#92400e]"
        : status === "dropped"
          ? "bg-[#f1f5f9] text-[#475569]"
          : "bg-[#eff6ff] text-[#1d4ed8]";
  return <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${tone}`}>{status}</span>;
}
