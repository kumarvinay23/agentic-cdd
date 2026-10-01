"use client";

import type { Deal } from "@/lib/deal-types";

function statusClass(status: string) {
  const s = status.toLowerCase().replace(/_/g, "-");
  if (s === "active") return "bg-[#e8f5ee] text-[#1f6b45]";
  return "bg-[#eef0f3] text-[#4b5563]";
}

function statusLabel(status: string) {
  return status.replace(/-/g, " ").toUpperCase();
}

export function DealCard({ deal, onOpen }: { deal: Deal; onOpen?: (deal: Deal) => void }) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen?.(deal)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen?.(deal);
        }
      }}
      className="group cursor-pointer rounded-[10px] border border-border-primary bg-background-secondary transition hover:border-border-secondary"
    >
      <div className="flex items-start gap-3 p-4">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#eef2f7] text-[#1e3a5f]">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.7">
            <path d="M3 8.5A2.5 2.5 0 0 1 5.5 6H10l2 2h6.5A2.5 2.5 0 0 1 21 10.5v7A2.5 2.5 0 0 1 18.5 20h-13A2.5 2.5 0 0 1 3 17.5v-9z" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <h2 className="truncate text-[14px] font-semibold text-text-primary">{deal.name}</h2>
            <span
              className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide ${statusClass(deal.status)}`}
            >
              {statusLabel(deal.status)}
            </span>
          </div>
          <p className="mt-1 text-[12px] text-text-secondary">
            {deal.summary ||
              (deal.docs_count
                ? `Data ingestion - ${deal.docs_count} documents uploaded, awaiting action.`
                : "No documents uploaded yet.")}
          </p>
          <p className="mt-1 text-[11px] text-text-secondary">{deal.team_label || "No team assigned"}</p>
        </div>
        <span className="mt-1 text-text-secondary opacity-60 group-hover:opacity-100">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="m9 6 6 6-6 6" />
          </svg>
        </span>
      </div>
    </article>
  );
}
