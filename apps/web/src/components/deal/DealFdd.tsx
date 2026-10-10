"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  ApiError,
  fddAcknowledgeG2Request,
  fddApproveG1Request,
  fddBuildClaimsRequest,
  fddCreateRunRequest,
  fddGetClaimsRequest,
  fddGetGatesRequest,
  fddGetScopeRequest,
  fddListRunsRequest,
  fddPhase2Request,
  fddPutScopeRequest,
  type FddClaimsLedger,
  type FddGateState,
  type FddRunSummary,
  type FddScopeProfile,
} from "@/lib/api";

type Tab = "scope" | "claims" | "gates";

const SECTION_OPTIONS = [
  "SEC-A",
  "SEC-B",
  "SEC-C",
  "SEC-D",
  "SEC-E",
  "SEC-F",
  "SEC-G",
  "SEC-H",
  "SEC-I",
  "SEC-J",
  "SEC-K",
  "SEC-ES",
] as const;

const SECTION_LABELS: Record<string, string> = {
  "SEC-A": "Scope & perimeter",
  "SEC-B": "Historical trading",
  "SEC-C": "Revenue & margin",
  "SEC-D": "Costs & people",
  "SEC-E": "Quality of earnings",
  "SEC-F": "Balance sheet / NAV",
  "SEC-G": "Net working capital",
  "SEC-H": "Net debt",
  "SEC-I": "Cash flow / capex",
  "SEC-J": "Forecast (optional)",
  "SEC-K": "Key findings",
  "SEC-ES": "Executive summary",
};

function csvLines(value: string): string[] {
  return value
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function gateTone(state?: FddGateState): "ok" | "warn" | "bad" | "neutral" {
  if (!state) return "neutral";
  if (state.passed || state.approved) return "ok";
  if (state.blocked || (state.blockers && state.blockers.length > 0)) return "bad";
  if (state.ready) return "warn";
  return "neutral";
}

function toneClass(tone: ReturnType<typeof gateTone>): string {
  if (tone === "ok") return "bg-[#ecfdf3] text-[#15803d] border-[#bbf7d0]";
  if (tone === "warn") return "bg-[#fffbeb] text-[#b45309] border-[#fde68a]";
  if (tone === "bad") return "bg-[#fef2f2] text-[#dc2626] border-[#fecaca]";
  return "bg-[#f3f4f6] text-[#4b5563] border-[#e5e7eb]";
}

export function DealFdd({
  dealId,
  accessToken,
  onError,
}: {
  dealId: string;
  accessToken?: string;
  onError: (msg: string | null) => void;
}) {
  const [tab, setTab] = useState<Tab>("scope");
  const [runs, setRuns] = useState<FddRunSummary[]>([]);
  const [runId, setRunId] = useState<string | null>(null);
  const [scope, setScope] = useState<FddScopeProfile | null>(null);
  const [g1Ready, setG1Ready] = useState(false);
  const [g1Blockers, setG1Blockers] = useState<string[]>([]);
  const [gates, setGates] = useState<Record<string, FddGateState>>({});
  const [claims, setClaims] = useState<FddClaimsLedger | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [g2Note, setG2Note] = useState("");
  const [entitiesIn, setEntitiesIn] = useState("");
  const [entitiesOut, setEntitiesOut] = useState("");
  const [periods, setPeriods] = useState("");
  const [dealType, setDealType] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [scale, setScale] = useState("M");
  const [materialityPct, setMaterialityPct] = useState("0.05");
  const [materialityM, setMaterialityM] = useState("");
  const [materialityBasis, setMaterialityBasis] = useState("adj_ebitda");
  const [sections, setSections] = useState<string[]>([]);
  const [notes, setNotes] = useState("");

  const syncForm = useCallback((profile: FddScopeProfile) => {
    setEntitiesIn((profile.entities_in || []).join("\n"));
    setEntitiesOut((profile.entities_out || []).join("\n"));
    setPeriods((profile.periods || []).join(", "));
    setDealType(profile.deal_type || "");
    setCurrency(profile.currency || "USD");
    setScale(profile.scale || "M");
    setMaterialityPct(String(profile.materiality_pct ?? 0.05));
    setMaterialityM(
      profile.materiality_m != null && Number.isFinite(profile.materiality_m)
        ? String(profile.materiality_m)
        : "",
    );
    setMaterialityBasis(profile.materiality_basis || "adj_ebitda");
    setSections(listOrDefault(profile.sections_in_scope));
    setNotes(profile.notes || "");
  }, []);

  const refresh = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    onError(null);
    try {
      let runList = (await fddListRunsRequest(accessToken, dealId)).data || [];
      if (!runList.length) {
        await fddCreateRunRequest(accessToken, dealId);
        runList = (await fddListRunsRequest(accessToken, dealId)).data || [];
      }
      setRuns(runList);
      const current =
        runList.find((r) => r.is_current)?.run_id ||
        runList[0]?.run_id ||
        null;
      const active = runId && runList.some((r) => r.run_id === runId) ? runId : current;
      setRunId(active);
      if (!active) return;

      await fddPhase2Request(accessToken, dealId, active).catch(() => null);

      const [scopeRes, gatesRes] = await Promise.all([
        fddGetScopeRequest(accessToken, dealId, active),
        fddGetGatesRequest(accessToken, dealId, active),
      ]);
      setScope(scopeRes.data.scope);
      setG1Ready(scopeRes.data.g1_ready);
      setG1Blockers(scopeRes.data.g1_blockers || []);
      syncForm(scopeRes.data.scope);
      setGates(gatesRes.data || {});

      try {
        const claimsRes = await fddGetClaimsRequest(accessToken, dealId, active);
        setClaims(claimsRes.data);
      } catch {
        setClaims(null);
      }
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Failed to load FDD workspace");
    } finally {
      setLoading(false);
    }
  }, [accessToken, dealId, onError, runId, syncForm]);

  useEffect(() => {
    void refresh();
    // Intentionally once per deal/token — runId changes handled via select.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, dealId]);

  const approved = scope?.status === "approved";

  const saveScope = async () => {
    if (!accessToken || !runId) return;
    setBusy(true);
    onError(null);
    try {
      const pct = Number(materialityPct);
      const mAbs = materialityM.trim() === "" ? null : Number(materialityM);
      const res = await fddPutScopeRequest(accessToken, dealId, runId, {
        entities_in: csvLines(entitiesIn),
        entities_out: csvLines(entitiesOut),
        periods: csvLines(periods),
        deal_type: dealType.trim() || null,
        currency: currency.trim() || "USD",
        scale: scale.trim() || "M",
        materiality_pct: Number.isFinite(pct) ? pct : 0.05,
        materiality_m: mAbs != null && Number.isFinite(mAbs) ? mAbs : null,
        materiality_basis: materialityBasis,
        sections_in_scope: sections,
        notes: notes.trim() || null,
        allow_edit_approved: approved,
      });
      setScope(res.data.scope);
      setG1Ready(res.data.g1_ready);
      setG1Blockers(res.data.g1_blockers || []);
      syncForm(res.data.scope);
      const gatesRes = await fddGetGatesRequest(accessToken, dealId, runId);
      setGates(gatesRes.data || {});
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Failed to save scope");
    } finally {
      setBusy(false);
    }
  };

  const approveG1 = async () => {
    if (!accessToken || !runId) return;
    onError(null);
    try {
      await saveScope();
      setBusy(true);
      await fddApproveG1Request(accessToken, dealId, runId, "Scope approved from FDD workspace");
      await refresh();
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "G1 approval failed");
    } finally {
      setBusy(false);
    }
  };

  const buildClaims = async () => {
    if (!accessToken || !runId) return;
    setBusy(true);
    onError(null);
    try {
      const res = await fddBuildClaimsRequest(accessToken, dealId, runId);
      setClaims(res.data.claims);
      const gatesRes = await fddGetGatesRequest(accessToken, dealId, runId);
      setGates(gatesRes.data || {});
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Claims build failed");
    } finally {
      setBusy(false);
    }
  };

  const acknowledgeG2 = async () => {
    if (!accessToken || !runId) return;
    const unreliable = gates.G2?.unreliable_modules || claims?.unreliable_modules || [];
    if (unreliable.length && g2Note.trim().length < 3) {
      onError("Enter a note (3+ chars) to acknowledge unreliable modules.");
      return;
    }
    setBusy(true);
    onError(null);
    try {
      await fddAcknowledgeG2Request(accessToken, dealId, runId, {
        note: g2Note.trim() || undefined,
        allow_unreliable: unreliable.length > 0,
      });
      setG2Note("");
      const gatesRes = await fddGetGatesRequest(accessToken, dealId, runId);
      setGates(gatesRes.data || {});
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "G2 acknowledge failed");
    } finally {
      setBusy(false);
    }
  };

  const gateOrder = useMemo(
    () => ["G0", "G1", "G2", "G3", "G4", "G5", "G6", "G7"] as const,
    [],
  );

  if (loading && !scope) {
    return <p className="text-sm text-text-secondary">Loading FDD workspace…</p>;
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-text-primary">Financial due diligence</h2>
          <p className="mt-1 text-sm text-text-secondary">
            Scope editor, claims reliability (G2), and gate status for this deal.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-xs text-text-secondary">
            Run
            <select
              className="ml-2 rounded border border-[#e5e7eb] bg-white px-2 py-1.5 text-sm"
              value={runId || ""}
              onChange={(e) => {
                setRunId(e.target.value || null);
                void (async () => {
                  if (!accessToken || !e.target.value) return;
                  setLoading(true);
                  try {
                    const [scopeRes, gatesRes] = await Promise.all([
                      fddGetScopeRequest(accessToken, dealId, e.target.value),
                      fddGetGatesRequest(accessToken, dealId, e.target.value),
                    ]);
                    setScope(scopeRes.data.scope);
                    setG1Ready(scopeRes.data.g1_ready);
                    setG1Blockers(scopeRes.data.g1_blockers || []);
                    syncForm(scopeRes.data.scope);
                    setGates(gatesRes.data || {});
                    try {
                      setClaims(
                        (await fddGetClaimsRequest(accessToken, dealId, e.target.value)).data,
                      );
                    } catch {
                      setClaims(null);
                    }
                  } catch (err) {
                    onError(err instanceof ApiError ? err.message : "Failed to switch run");
                  } finally {
                    setLoading(false);
                  }
                })();
              }}
            >
              {runs.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.run_id.slice(0, 12)}
                  {r.is_current ? " · current" : ""}
                  {r.g2_passed ? " · G2" : ""}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="rounded border border-[#e5e7eb] px-3 py-1.5 text-sm hover:bg-[#f9fafb]"
            disabled={busy || !accessToken}
            onClick={() => void refresh()}
          >
            Refresh
          </button>
          <button
            type="button"
            className="rounded bg-[#111827] px-3 py-1.5 text-sm text-white hover:bg-[#1f2937] disabled:opacity-50"
            disabled={busy || !accessToken}
            onClick={() =>
              void (async () => {
                if (!accessToken) return;
                setBusy(true);
                try {
                  await fddCreateRunRequest(accessToken, dealId);
                  setRunId(null);
                  await refresh();
                } catch (err) {
                  onError(err instanceof ApiError ? err.message : "Create run failed");
                } finally {
                  setBusy(false);
                }
              })()
            }
          >
            New run
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {gateOrder.map((id) => {
          const st = gates[id];
          const tone = gateTone(st);
          const label =
            st?.passed || st?.approved
              ? "pass"
              : st?.ready
                ? "ready"
                : st?.blockers?.length
                  ? "blocked"
                  : "—";
          return (
            <span
              key={id}
              className={`rounded border px-2.5 py-1 text-xs font-medium ${toneClass(tone)}`}
              title={(st?.blockers || []).join("; ") || id}
            >
              {id} · {label}
            </span>
          );
        })}
      </div>

      <div className="flex gap-1 border-b border-[#e5e7eb]">
        {(
          [
            ["scope", "Scope"],
            ["claims", "Claims / G2"],
            ["gates", "Gates"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`px-3 py-2 text-sm ${
              tab === id
                ? "border-b-2 border-[#111827] font-medium text-text-primary"
                : "text-text-secondary hover:text-text-primary"
            }`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "scope" ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span
              className={`rounded border px-2 py-0.5 text-xs ${toneClass(
                approved ? "ok" : g1Ready ? "warn" : "bad",
              )}`}
            >
              {approved ? "G1 approved" : g1Ready ? "Ready for G1" : "Scope incomplete"}
            </span>
            {g1Blockers.length > 0 ? (
              <span className="text-xs text-[#b45309]">Blockers: {g1Blockers.join(", ")}</span>
            ) : null}
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Entities in scope (one per line)">
              <textarea
                className="min-h-[88px] w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={entitiesIn}
                onChange={(e) => setEntitiesIn(e.target.value)}
              />
            </Field>
            <Field label="Entities out of scope">
              <textarea
                className="min-h-[88px] w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={entitiesOut}
                onChange={(e) => setEntitiesOut(e.target.value)}
              />
            </Field>
            <Field label="Deal type">
              <input
                className="w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={dealType}
                onChange={(e) => setDealType(e.target.value)}
                placeholder="buy-side / sell-side / carve-out"
              />
            </Field>
            <Field label="Periods (comma-separated)">
              <input
                className="w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={periods}
                onChange={(e) => setPeriods(e.target.value)}
                placeholder="FY22A, FY23A, FY24A"
              />
            </Field>
            <Field label="Currency">
              <input
                className="w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={currency}
                onChange={(e) => setCurrency(e.target.value)}
              />
            </Field>
            <Field label="Scale">
              <input
                className="w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={scale}
                onChange={(e) => setScale(e.target.value)}
                placeholder="M / Cr / K"
              />
            </Field>
            <Field label="Materiality % of basis">
              <input
                className="w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={materialityPct}
                onChange={(e) => setMaterialityPct(e.target.value)}
              />
            </Field>
            <Field label="Materiality basis">
              <select
                className="w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={materialityBasis}
                onChange={(e) => setMaterialityBasis(e.target.value)}
              >
                <option value="adj_ebitda">Adjusted EBITDA</option>
                <option value="revenue">Revenue</option>
              </select>
            </Field>
            <Field label="Materiality M (absolute, optional)">
              <input
                className="w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={materialityM}
                onChange={(e) => setMaterialityM(e.target.value)}
              />
            </Field>
            <Field label="Notes">
              <textarea
                className="min-h-[88px] w-full rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </Field>
          </div>

          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-text-secondary">
              Sections in scope
            </p>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {SECTION_OPTIONS.map((sid) => {
                const on = sections.includes(sid);
                return (
                  <label
                    key={sid}
                    className="flex cursor-pointer items-center gap-2 rounded border border-[#e5e7eb] px-3 py-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={on}
                      onChange={() =>
                        setSections((prev) =>
                          on ? prev.filter((x) => x !== sid) : [...prev, sid],
                        )
                      }
                    />
                    <span>
                      <span className="font-medium">{sid}</span>{" "}
                      <span className="text-text-secondary">{SECTION_LABELS[sid]}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || !runId}
              onClick={() => void saveScope()}
              className="rounded border border-[#e5e7eb] bg-white px-4 py-2 text-sm hover:bg-[#f9fafb] disabled:opacity-50"
            >
              Save scope
            </button>
            <button
              type="button"
              disabled={busy || !runId || approved || !g1Ready}
              onClick={() => void approveG1()}
              className="rounded bg-[#111827] px-4 py-2 text-sm text-white hover:bg-[#1f2937] disabled:opacity-50"
            >
              Approve G1
            </button>
          </div>
        </div>
      ) : null}

      {tab === "claims" ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className={`rounded border px-2 py-0.5 text-xs ${toneClass(gateTone(gates.G2))}`}>
              G2 {gates.G2?.passed ? "passed" : gates.G2?.ready ? "ready" : "not ready"}
            </span>
            {(gates.G2?.unreliable_modules || []).length > 0 ? (
              <span className="text-xs text-[#dc2626]">
                Unreliable: {(gates.G2?.unreliable_modules || []).join(", ")}
              </span>
            ) : null}
            <button
              type="button"
              disabled={busy || !runId}
              onClick={() => void buildClaims()}
              className="rounded bg-[#111827] px-3 py-1.5 text-sm text-white disabled:opacity-50"
            >
              Build / refresh claims
            </button>
          </div>

          {claims ? (
            <div className="grid gap-3 sm:grid-cols-4">
              {[
                ["Claims", claims.claim_count],
                ["Agrees", claims.agrees],
                ["Contradicted", claims.contradicted],
                ["Unverifiable", claims.unverifiable],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded border border-[#e5e7eb] px-3 py-2">
                  <p className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</p>
                  <p className="text-lg font-semibold text-text-primary">{value}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-secondary">
              No claims ledger yet — build claims to run the G2 reliability gate.
            </p>
          )}

          {claims?.modules?.length ? (
            <div className="overflow-x-auto rounded border border-[#e5e7eb]">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-[#f9fafb] text-xs uppercase text-text-secondary">
                  <tr>
                    <th className="px-3 py-2">Module</th>
                    <th className="px-3 py-2">Total</th>
                    <th className="px-3 py-2">Failed</th>
                    <th className="px-3 py-2">Fail rate</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {claims.modules.map((m) => (
                    <tr key={m.source_agent} className="border-t border-[#e5e7eb]">
                      <td className="px-3 py-2">{m.source_agent}</td>
                      <td className="px-3 py-2">{m.total}</td>
                      <td className="px-3 py-2">{m.failed}</td>
                      <td className="px-3 py-2">{(m.fail_rate * 100).toFixed(0)}%</td>
                      <td className="px-3 py-2">
                        {m.unreliable ? (
                          <span className="text-[#dc2626]">Unreliable</span>
                        ) : (
                          <span className="text-[#15803d]">OK</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}

          {(gates.G2?.unreliable_modules || []).length > 0 ||
          (claims && !gates.G2?.passed) ? (
            <div className="rounded border border-[#fde68a] bg-[#fffbeb] p-3 space-y-2">
              <p className="text-sm text-[#92400e]">
                G2 auto-passes when claims are built and no module exceeds the 50% fail
                threshold. Acknowledge with a note to proceed despite unreliable modules.
              </p>
              <textarea
                className="min-h-[64px] w-full rounded border border-[#fde68a] bg-white px-3 py-2 text-sm"
                placeholder="Acknowledgement note (required if unreliable modules)"
                value={g2Note}
                onChange={(e) => setG2Note(e.target.value)}
              />
              <button
                type="button"
                disabled={busy || !runId || gates.G2?.passed}
                onClick={() => void acknowledgeG2()}
                className="rounded bg-[#111827] px-3 py-1.5 text-sm text-white disabled:opacity-50"
              >
                Acknowledge G2
              </button>
            </div>
          ) : null}

          {claims?.claims?.length ? (
            <div className="overflow-x-auto rounded border border-[#e5e7eb]">
              <table className="min-w-full text-left text-sm">
                <thead className="bg-[#f9fafb] text-xs uppercase text-text-secondary">
                  <tr>
                    <th className="px-3 py-2">Agent</th>
                    <th className="px-3 py-2">Claim</th>
                    <th className="px-3 py-2">Result</th>
                  </tr>
                </thead>
                <tbody>
                  {claims.claims.slice(0, 40).map((c) => (
                    <tr key={c.claim_id} className="border-t border-[#e5e7eb]">
                      <td className="px-3 py-2 whitespace-nowrap">{c.source_agent || "—"}</td>
                      <td className="px-3 py-2 max-w-md truncate" title={c.text}>
                        {c.text}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={
                            c.test_result === "agrees"
                              ? "text-[#15803d]"
                              : c.failed
                                ? "text-[#dc2626]"
                                : "text-text-secondary"
                          }
                        >
                          {c.test_result}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </div>
      ) : null}

      {tab === "gates" ? (
        <div className="grid gap-3 sm:grid-cols-2">
          {gateOrder.map((id) => {
            const st = gates[id];
            return (
              <div key={id} className={`rounded border p-3 ${toneClass(gateTone(st))}`}>
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="font-semibold">{id}</h3>
                  <span className="text-xs">
                    {st?.passed || st?.approved
                      ? "Passed"
                      : st?.ready
                        ? "Ready"
                        : st?.blocked
                          ? "Blocked"
                          : "Pending"}
                  </span>
                </div>
                {st?.score != null ? (
                  <p className="mt-1 text-xs">Score: {(st.score * 100).toFixed(0)}%</p>
                ) : null}
                {st?.claim_count != null ? (
                  <p className="mt-1 text-xs">
                    Claims: {st.claim_count} · contradicted {st.contradicted ?? 0}
                  </p>
                ) : null}
                {(st?.blockers || []).length > 0 ? (
                  <ul className="mt-2 list-disc pl-4 text-xs">
                    {(st?.blockers || []).slice(0, 6).map((b) => (
                      <li key={b}>{b}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-2 text-xs opacity-80">No blockers</p>
                )}
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function listOrDefault(sections?: string[] | null): string[] {
  if (sections && sections.length) return [...sections];
  return SECTION_OPTIONS.filter((s) => s !== "SEC-J");
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-text-secondary">
        {label}
      </span>
      {children}
    </label>
  );
}
