"use client";

import { useMemo, useState } from "react";
import type { DocumentCapability } from "@/lib/api";

type Filter = "all" | "algo" | "web";

function srcBadge(src: string): { label: string; className: string } {
  if (src === "web") {
    return {
      label: "Web",
      className: "bg-[#ecfdf5] text-[#047857]",
    };
  }
  return {
    label: "Data room",
    className: "bg-[#eef0f3] text-[#4b5563]",
  };
}

function groupLabel(section: string): string {
  const short = section.split(":").pop()?.trim() || section;
  return short.length > 48 ? `${short.slice(0, 47)}…` : short;
}

export function capabilityPrompt(cap: DocumentCapability, dealName: string): string {
  const subject = dealName.trim() || "the company";
  return `Research this and add a section to the document: Run ${cap.title} analysis for ${subject}.`;
}

export function CapabilityCatalogPanel({
  open,
  capabilities,
  dealName,
  loading,
  disabled,
  onClose,
  onSelect,
}: {
  open: boolean;
  capabilities: DocumentCapability[];
  dealName: string;
  loading?: boolean;
  disabled?: boolean;
  onClose: () => void;
  onSelect: (cap: DocumentCapability, prompt: string) => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return capabilities.filter((cap) => {
      if (filter === "web" && cap.src !== "web") return false;
      if (filter === "algo" && cap.src === "web") return false;
      if (!q) return true;
      const hay = [
        cap.title,
        cap.id,
        cap.section,
        cap.description,
        cap.blurb,
        cap.exhibit,
        cap.kind,
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [capabilities, filter, query]);

  const grouped = useMemo(() => {
    const map = new Map<string, DocumentCapability[]>();
    for (const cap of filtered) {
      const key = cap.section || "Other";
      const list = map.get(key) || [];
      list.push(cap);
      map.set(key, list);
    }
    return [...map.entries()];
  }, [filtered]);

  if (!open) return null;

  return (
    <div
      className="absolute inset-x-0 bottom-0 z-20 flex max-h-[min(72vh,520px)] flex-col rounded-t-[12px] border border-border-primary bg-white shadow-[0_-8px_32px_rgba(15,23,42,0.12)]"
      role="dialog"
      aria-label="Capability catalog"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border-primary px-3 py-2.5">
        <div className="min-w-0">
          <h3 className="text-[13px] font-semibold text-text-primary">Capability catalog</h3>
          <p className="text-[11px] text-text-secondary">
            {capabilities.length} runnable analyses · pick one to research and write
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close capability catalog"
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-text-secondary hover:bg-[#f1f5f9] hover:text-text-primary"
        >
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6 6 18M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="space-y-2 border-b border-border-primary px-3 py-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search capabilities…"
          className="w-full rounded-lg border border-border-primary bg-white px-2.5 py-1.5 text-[12px] text-text-primary outline-none placeholder:text-text-secondary focus:border-[#93c5fd]"
        />
        <div className="flex flex-wrap gap-1.5">
          {(
            [
              ["all", "All"],
              ["algo", "Data room"],
              ["web", "Web"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setFilter(id)}
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                filter === id
                  ? "bg-[#1d4ed8] text-white"
                  : "bg-[#f1f5f9] text-text-secondary hover:bg-[#e2e8f0]"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
        {loading ? (
          <p className="py-6 text-center text-[12px] text-text-secondary">Loading catalog…</p>
        ) : grouped.length === 0 ? (
          <p className="py-6 text-center text-[12px] text-text-secondary">No capabilities match your search.</p>
        ) : (
          <div className="space-y-3 pb-2">
            {grouped.map(([section, caps]) => (
              <div key={section}>
                <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-text-secondary">
                  {groupLabel(section)}
                </p>
                <div className="space-y-1.5">
                  {caps.map((cap) => {
                    const badge = srcBadge(cap.src);
                    return (
                      <button
                        key={cap.id}
                        type="button"
                        disabled={disabled}
                        onClick={() => onSelect(cap, capabilityPrompt(cap, dealName))}
                        className="w-full rounded-[10px] border border-border-primary bg-[#fafbfc] px-2.5 py-2 text-left transition hover:border-[#93c5fd] hover:bg-[#f8fbff] disabled:opacity-50"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <p className="text-[12px] font-medium text-text-primary">{cap.title}</p>
                          <span
                            className={`shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-semibold uppercase ${badge.className}`}
                          >
                            {badge.label}
                          </span>
                        </div>
                        <p className="mt-0.5 line-clamp-2 text-[11px] text-text-secondary">
                          {cap.blurb || cap.description}
                        </p>
                        {cap.exhibit ? (
                          <p className="mt-1 text-[10px] text-[#64748b]">Exhibit · {cap.exhibit.replace(/_/g, " ")}</p>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
