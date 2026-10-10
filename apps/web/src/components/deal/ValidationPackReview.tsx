"use client";

import { useEffect, useState } from "react";
import type { ValidationCard, ValidationPack } from "@/lib/api";
import { databookCropObjectUrl } from "@/lib/api";
import {
  DEFAULT_PAGE_SIZE,
  ListPagination,
  useClientPagination,
} from "@/components/deal/ListPagination";

const KIND_LABEL: Record<ValidationCard["kind"], string> = {
  conflict: "Conflict",
  doubtful: "Doubtful",
  missing: "Missing",
  calibration: "Calibration",
};

const KIND_TONE: Record<ValidationCard["kind"], string> = {
  conflict: "border-[#fca5a5] bg-[#fef2f2] text-[#991b1b]",
  doubtful: "border-[#fcd34d] bg-[#fffbeb] text-[#92400e]",
  missing: "border-[#cbd5e1] bg-[#f8fafc] text-[#475569]",
  calibration: "border-[#99f6e4] bg-[#f0fdfa] text-[#0f766e]",
};

function fmtValue(card: ValidationCard): string {
  if (card.value == null) return "—";
  const n = Number(card.value);
  if (!Number.isFinite(n)) return String(card.value);
  const unit = [card.currency, card.scale, card.unit].filter(Boolean).join(" ");
  return `${n.toLocaleString(undefined, { maximumFractionDigits: 4 })}${unit ? ` ${unit}` : ""}`;
}

function labels(card: ValidationCard): string {
  const bits = [
    card.statement,
    card.scope,
    card.period_end,
    card.period_length,
    card.source_basis,
    card.proof_level,
  ].filter(Boolean);
  return bits.length ? bits.join(" · ") : "—";
}

function sourceLocator(card: ValidationCard): string | null {
  const ref = card.source_ref;
  if (!ref) return null;
  const bits = [
    ref.doc,
    ref.page != null ? `p${ref.page}` : null,
    ref.table,
    ref.row != null ? `row ${ref.row}` : null,
    ref.col != null ? `col ${ref.col}` : null,
    ref.rule,
  ].filter(Boolean);
  return bits.length ? bits.join(" · ") : null;
}

function CropThumb({
  card,
  accessToken,
  dealId,
}: {
  card: ValidationCard;
  accessToken?: string;
  dealId?: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const cropRef = card.crop_ref;
  const status = card.crop_status || "unavailable";

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;
    if (!accessToken || !dealId || !cropRef || status !== "available") {
      setUrl(null);
      return;
    }
    setError(false);
    void databookCropObjectUrl(accessToken, dealId, cropRef)
      .then((objectUrl) => {
        if (cancelled) {
          URL.revokeObjectURL(objectUrl);
          return;
        }
        revoked = objectUrl;
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [accessToken, dealId, cropRef, status]);

  if (status === "available" && url) {
    const isPdf = (cropRef || "").toLowerCase().endsWith(".pdf");
    return (
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="block overflow-hidden rounded-lg border border-[#e2e8f0] bg-[#f8fafc]"
        title="Open source crop"
      >
        {isPdf ? (
          <div className="flex h-36 flex-col items-center justify-center gap-1 px-3 text-center text-[11px] text-[#0f766e]">
            <span className="font-medium">PDF crop</span>
            <span className="text-[#64748b]">Open in new tab</span>
          </div>
        ) : (
          /* eslint-disable-next-line @next/next/no-img-element */
          <img
            src={url}
            alt={`Source crop for ${card.metric_key} FY${card.fiscal_year}`}
            className="max-h-36 w-full object-contain object-left bg-white"
          />
        )}
      </a>
    );
  }

  const tone =
    status === "pending"
      ? "border-[#fde68a] bg-[#fffbeb] text-[#92400e]"
      : "border-[#e2e8f0] bg-[#f8fafc] text-[#64748b]";
  const label =
    status === "pending"
      ? "Crop pending"
      : status === "available" && error
        ? "Crop failed to load"
        : card.crop_reason || "Crop unavailable";

  return (
    <div className={`rounded-lg border px-3 py-6 text-center text-[11px] ${tone}`}>{label}</div>
  );
}

export function ValidationPackReview({
  pack,
  busy,
  accessToken,
  dealId,
  onConfirm,
  onExclude,
  onRemap,
  onAcceptAlt,
}: {
  pack: ValidationPack | null;
  busy?: boolean;
  accessToken?: string;
  dealId?: string;
  onConfirm: (card: ValidationCard) => void;
  onExclude: (card: ValidationCard) => void;
  onRemap: (card: ValidationCard) => void;
  onAcceptAlt: (card: ValidationCard, value: number, rowId?: string) => void;
}) {
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const cards = pack?.cards || [];
  const pager = useClientPagination(cards, pageSize);

  if (!pack) {
    return (
      <p className="rounded-lg border border-dashed border-[#e2e8f0] bg-[#f8fafc] px-4 py-8 text-center text-[13px] text-[#64748b]">
        Load a validation pack after Release to review doubtful cells and a calibration sample.
      </p>
    );
  }

  if (!pack.ready_for_review) {
    return (
      <p className="rounded-lg border border-[#fde68a] bg-[#fffbeb] px-4 py-6 text-[13px] text-[#92400e]">
        No released databook yet — run Rescan or Release first. Validation is post-run only (OL-1).
      </p>
    );
  }

  const counts = pack.counts || {};

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-[12px] text-[#64748b]">
        <span className="font-medium text-[#0f172a]">
          Release {pack.release_id || "—"}
          {pack.release_version != null ? ` (v${pack.release_version})` : null}
        </span>
        <span>·</span>
        <span>{counts.conflict ?? 0} conflict</span>
        <span>·</span>
        <span>{counts.doubtful ?? 0} doubtful</span>
        <span>·</span>
        <span>{counts.missing ?? 0} missing</span>
        <span>·</span>
        <span>{counts.calibration ?? 0} calibration</span>
        {counts.crops_available != null ? (
          <>
            <span>·</span>
            <span>{counts.crops_available} crops ready</span>
          </>
        ) : null}
      </div>

      {cards.length === 0 ? (
        <p className="rounded-lg border border-[#bbf7d0] bg-[#f0fdf4] px-4 py-6 text-[13px] text-[#166534]">
          Pack is empty — no doubtful/missing cells and no calibration sample available.
        </p>
      ) : (
        <div className="overflow-hidden rounded-xl border border-[#e2e8f0] bg-white">
          <ul className="divide-y divide-[#e2e8f0]">
            {pager.pageItems.map((card) => (
              <li key={card.card_id} className="p-4">
                <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_11rem]">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${KIND_TONE[card.kind]}`}
                        >
                          {KIND_LABEL[card.kind]}
                        </span>
                        <span className="text-[14px] font-semibold text-[#0f172a]">
                          {card.metric_key} · FY{card.fiscal_year}
                        </span>
                      </div>
                      <p className="mt-1 text-[13px] text-[#0f172a]">{fmtValue(card)}</p>
                      <p className="mt-1 text-[11px] text-[#64748b]">{labels(card)}</p>
                      {sourceLocator(card) ? (
                        <p className="mt-1 text-[11px] text-[#475569]">{sourceLocator(card)}</p>
                      ) : null}
                      {card.reason ? (
                        <p className="mt-1 text-[12px] text-[#b45309]">{card.reason}</p>
                      ) : null}
                      {card.document_request ? (
                        <p className="mt-1 text-[12px] text-[#1e3a5f]">
                          Request: {card.document_request.label}
                          {card.document_request.priority === "required" ? " (required)" : ""}
                        </p>
                      ) : null}
                      {card.captions?.length ? (
                        <p className="mt-1 text-[12px] text-[#475569]">
                          Caption: {card.captions.slice(0, 2).join(" · ")}
                        </p>
                      ) : null}
                      {card.sources?.length ? (
                        <p className="mt-0.5 text-[11px] text-[#94a3b8]">
                          Sources: {card.sources.slice(0, 3).join(", ")}
                        </p>
                      ) : null}
                      {card.dependents?.length ? (
                        <p className="mt-0.5 text-[11px] text-[#64748b]">
                          Same-year dependents: {card.dependents.join(", ")}
                        </p>
                      ) : null}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {card.row_id && card.kind !== "missing" ? (
                        <>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => onConfirm(card)}
                            className="rounded-lg border border-[#0f766e] px-2.5 py-1.5 text-[12px] font-medium text-[#0f766e] hover:bg-[#f0fdfa] disabled:opacity-50"
                          >
                            Confirm
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => onRemap(card)}
                            className="rounded-lg border border-[#e2e8f0] px-2.5 py-1.5 text-[12px] font-medium text-[#334155] hover:bg-[#f8fafc] disabled:opacity-50"
                          >
                            Remap
                          </button>
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => onExclude(card)}
                            className="rounded-lg border border-[#fecaca] px-2.5 py-1.5 text-[12px] font-medium text-[#b91c1c] hover:bg-[#fef2f2] disabled:opacity-50"
                          >
                            Exclude
                          </button>
                        </>
                      ) : null}
                    </div>
                  </div>
                  {card.kind !== "missing" ? (
                    <CropThumb card={card} accessToken={accessToken} dealId={dealId} />
                  ) : null}
                </div>
                {card.alternatives && card.alternatives.length > 0 ? (
                  <div className="mt-3 border-t border-[#f1f5f9] pt-3">
                    <p className="mb-1.5 text-[11px] font-medium uppercase tracking-wide text-[#94a3b8]">
                      Alternatives
                    </p>
                    <ul className="space-y-1">
                      {card.alternatives.map((alt, idx) => {
                        const value = typeof alt.value === "number" ? alt.value : Number(alt.value);
                        const rowId =
                          typeof alt.row_id === "string"
                            ? alt.row_id
                            : Array.isArray(alt.row_ids)
                              ? String(alt.row_ids[0] || "")
                              : undefined;
                        return (
                          <li
                            key={`${card.card_id}-alt-${idx}`}
                            className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-[#f8fafc] px-2.5 py-1.5 text-[12px]"
                          >
                            <span className="text-[#334155]">
                              {Number.isFinite(value) ? value.toLocaleString() : String(alt.value)}
                              {typeof alt.source_name === "string" ? ` · ${alt.source_name}` : ""}
                            </span>
                            {Number.isFinite(value) ? (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => onAcceptAlt(card, value, rowId)}
                                className="rounded border border-[#e2e8f0] bg-white px-2 py-1 text-[11px] font-medium text-[#0f172a] hover:bg-white disabled:opacity-50"
                              >
                                Pick
                              </button>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
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
    </div>
  );
}
