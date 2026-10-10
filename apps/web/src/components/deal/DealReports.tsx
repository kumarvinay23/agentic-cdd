"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ApiError,
  reportArtifactBlobUrlRequest,
  reportDownloadRequest,
  reportEventsStream,
  reportGenerateRequest,
  reportPreviewRequest,
  reportSourcesRequest,
  reportStatusRequest,
  reportStorylineRequest,
  reportsCatalogRequest,
  type ReportCatalogEntry,
  type ReportStorylineSection,
  type ReportSourcesPayload,
  type ReportPreviewBlock,
  type ReportPreviewSlide,
  type ReportPreviewPayload,
  type ReportDecisionChainEntry,
} from "@/lib/api";
import { DecisionChainPanel } from "@/components/deal/DecisionChainPanel";

const IMPLEMENTED_REPORTS = new Set([
  "ops_dashboard",
  "strategy_report",
  "ic_memo",
  "market_deck",
  "cdd_deck",
  "fdd_report",
  "fdd_deck",
]);

/** Surface FDD first so Phase 0–1 stubs are easy to find in the catalog. */
const CATALOG_ORDER = [
  "fdd_report",
  "fdd_deck",
  "cdd_deck",
  "ic_memo",
  "market_deck",
  "strategy_report",
  "ops_dashboard",
];

function sortCatalog(entries: ReportCatalogEntry[]): ReportCatalogEntry[] {
  const rank = new Map(CATALOG_ORDER.map((id, i) => [id, i]));
  return [...entries].sort((a, b) => {
    const ra = rank.get(a.report_type) ?? 100;
    const rb = rank.get(b.report_type) ?? 100;
    if (ra !== rb) return ra - rb;
    return a.report_type.localeCompare(b.report_type);
  });
}

type ReportTab = "preview" | "storyline" | "sources";
type ViewMode = "catalog" | "detail";

type GenLogEntry = {
  stage: string;
  message: string;
  level?: string;
  t?: number;
};

function statusBadge(status: string): { label: string; className: string } {
  switch (status) {
    case "ready":
      return { label: "Ready", className: "bg-[#ecfdf3] text-[#15803d] ring-1 ring-[#bbf7d0]" };
    case "running":
      return { label: "Generating…", className: "bg-[#eff6ff] text-[#1d4ed8] ring-1 ring-[#bfdbfe]" };
    case "failed":
      return { label: "Failed", className: "bg-[#fef2f2] text-[#dc2626] ring-1 ring-[#fecaca]" };
    default:
      return { label: "Not generated", className: "bg-[#f3f4f6] text-[#6b7280] ring-1 ring-[#e5e7eb]" };
  }
}

function formatKind(report: ReportCatalogEntry): string {
  if (report.format === "dashboard") return "DASHBOARD";
  if (report.format === "deck") return "SLIDE DECK";
  return "DOCUMENT";
}

function downloadLabel(report: ReportCatalogEntry): string {
  const map: Record<string, string> = {
    xlsx: "Download Excel",
    pptx: "Download PowerPoint",
    docx: "Download Word",
    pdf: "Download PDF",
  };
  return map[report.export] || `Download ${report.export?.toUpperCase() || "file"}`;
}

function agentLabel(agent: string): string {
  return agent
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

function ReportTypeIcon({ format }: { format: string }) {
  const props = {
    viewBox: "0 0 24 24",
    width: 22,
    height: 22,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
  };
  if (format === "dashboard") {
    return (
      <svg {...props}>
        <rect x="3" y="3" width="8" height="8" rx="1.5" />
        <rect x="13" y="3" width="8" height="5" rx="1.5" />
        <rect x="13" y="10" width="8" height="11" rx="1.5" />
        <rect x="3" y="13" width="8" height="8" rx="1.5" />
      </svg>
    );
  }
  if (format === "deck") {
    return (
      <svg {...props}>
        <rect x="3" y="5" width="18" height="12" rx="1.5" />
        <path d="M8 19h8" />
        <path d="M12 17v2" />
      </svg>
    );
  }
  return (
    <svg {...props}>
      <path d="M7 3h8l4 4v14H7V3z" />
      <path d="M15 3v5h5" />
      <path d="M10 12h6M10 16h6" />
    </svg>
  );
}

function RagCell({ value }: { readonly value: unknown }) {
  const text = typeof value === "string" || typeof value === "number" ? String(value) : "";
  const lower = text.toLowerCase();
  let cls = "";
  if (lower.includes("on-track") || lower === "on track") cls = "bg-[#70AD47] text-white";
  else if (lower.includes("at-risk") || lower.includes("below target") || lower === "critical")
    cls = "bg-[#FF4444] text-white";
  else if (lower.includes("monitor") || lower.includes("warn")) cls = "bg-[#FFC000] text-[#1f2937]";
  if (!cls) return <>{text}</>;
  return <span className={`inline-block rounded px-1.5 py-0.5 text-[11px] font-semibold ${cls}`}>{text}</span>;
}

function isRagCell(value: unknown): boolean {
  const s = String(value ?? "");
  return ["On-Track", "At-Risk", "Monitor", "Critical", "Below Target"].some((t) => s.includes(t));
}

function PreviewDataTable({ rows }: { readonly rows: string[][] }) {
  if (!rows.length) return null;

  function renderCell(cell: string, ri: number) {
    const upper = cell.trim().toUpperCase();
    if (ri > 0 && (upper === "CONFIRMED" || upper === "ASSUMED")) {
      const confirmed = upper === "CONFIRMED";
      return (
        <span
          className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${
            confirmed ? "bg-[#ecfdf3] text-[#15803d]" : "bg-[#fffbeb] text-[#b45309]"
          }`}
        >
          {upper}
        </span>
      );
    }
    return cell;
  }

  return (
    <div className="my-3 overflow-auto rounded-md border border-[#d1d5db]">
      <table className="min-w-full border-collapse text-left text-[12px]">
        <tbody>
          {rows.map((row, ri) => (
            <tr
              key={`tr-${ri}`}
              className={ri === 0 ? "bg-[#1F3864] text-white" : ri % 2 === 0 ? "bg-white" : "bg-[#f3f6fb]"}
            >
              {row.map((cell, ci) => (
                <td
                  key={`td-${ri}-${ci}`}
                  className={`border border-[#e5e7eb] px-2.5 py-1.5 align-top ${
                    ri === 0 ? "font-semibold" : "text-text-primary"
                  }`}
                >
                  {renderCell(cell, ri)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PdfPreview({ url, pageCount }: { readonly url: string; readonly pageCount?: number }) {
  if (!url) {
    return (
      <div className="py-10 text-center">
        <p className="text-[14px] font-medium text-text-primary">Preview is empty</p>
        <p className="mt-1 text-[13px] text-text-secondary">Regenerate the report, then try again.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-[#e5e7eb] bg-[#e8eaed] shadow-sm">
      <div className="flex items-center justify-between border-b border-[#d1d5db] bg-[#fafbfc] px-4 py-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-secondary">
          PDF preview
        </p>
        <p className="text-[11px] text-text-secondary">
          {pageCount ? `${pageCount} pages · ` : ""}
          <span className="font-semibold text-[#C2410C]">Strictly Private &amp; Confidential</span>
        </p>
      </div>
      <iframe
        title="IC Memo PDF preview"
        src={`${url}#toolbar=1&navpanes=0`}
        className="h-[min(78vh,920px)] w-full bg-white"
      />
    </div>
  );
}

function DocxPreview({ blocks }: { readonly blocks: ReportPreviewBlock[] }) {
  if (!blocks.length) {
    return (
      <div className="py-10 text-center">
        <p className="text-[14px] font-medium text-text-primary">Preview is empty</p>
        <p className="mt-1 text-[13px] text-text-secondary">Regenerate the report, then try again.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-1 rounded-lg border border-[#e5e7eb] bg-[#fafbfc] p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between border-b border-[#e5e7eb] pb-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-secondary">
          Document preview
        </p>
        <p className="text-[11px] font-semibold text-[#C2410C]">Strictly Private &amp; Confidential</p>
      </div>

      {blocks.map((block, idx) => {
        const key = `b-${idx}`;
        if (block.type === "page_break") {
          return (
            <div
              key={key}
              className="my-6 flex items-center gap-3 text-[10px] uppercase tracking-widest text-[#9ca3af]"
            >
              <div className="h-px flex-1 bg-[#e5e7eb]" />
              Page break
              <div className="h-px flex-1 bg-[#e5e7eb]" />
            </div>
          );
        }
        if (block.type === "cover_hero") {
          const text = block.rows?.[0]?.[0] || block.text || "";
          return (
            <div
              key={key}
              className="my-3 rounded-md bg-[#1F3864] px-5 py-8 text-white shadow-sm"
            >
              <p className="whitespace-pre-wrap text-[13px] leading-relaxed">{text}</p>
            </div>
          );
        }
        if (block.type === "divider") {
          const text = block.rows?.[0]?.[0] || block.text || "";
          return (
            <div
              key={key}
              className="my-5 rounded-md bg-[#1F3864] px-5 py-10 text-white"
            >
              <p className="whitespace-pre-wrap text-[15px] font-semibold leading-relaxed">{text}</p>
            </div>
          );
        }
        if (block.type === "callout") {
          const text = block.rows?.[0]?.[0] || block.text || "";
          return (
            <div
              key={key}
              className="my-3 rounded-md border-l-4 border-[#C2410C] bg-[#f8f5f2] px-4 py-3 text-[12px] text-[#4b5563]"
            >
              {text}
            </div>
          );
        }
        if (block.type === "meta" || block.type === "table") {
          return <PreviewDataTable key={key} rows={block.rows || []} />;
        }
        if (block.type === "heading") {
          const level = block.level || 1;
          const cls =
            level === 1
              ? "mt-5 mb-2 border-b-2 border-[#1F3864] pb-1 text-[18px] font-bold text-[#1F3864]"
              : level === 2
                ? "mt-4 mb-1.5 text-[15px] font-semibold text-[#1F3864]"
                : "mt-3 mb-1 text-[13px] font-semibold text-[#374151]";
          return (
            <h3 key={key} className={cls}>
              {block.text}
            </h3>
          );
        }
        if (block.type === "insight") {
          return (
            <div
              key={key}
              className="my-2 rounded-r-md border-l-4 border-[#1F3864] bg-[#E8EEF7] px-3 py-2 text-[12px] italic text-[#4b5563]"
            >
              <span className="font-semibold not-italic text-[#1F3864]">Insight: </span>
              {block.text}
            </div>
          );
        }
        if (block.type === "bullet") {
          return (
            <li key={key} className="ml-5 list-disc text-[13px] leading-relaxed text-text-primary">
              {block.text}
            </li>
          );
        }
        return (
          <p
            key={key}
            className={`my-1.5 text-[13px] leading-relaxed ${
              block.muted ? "text-text-secondary italic" : "text-text-primary"
            }`}
          >
            {block.text}
          </p>
        );
      })}
    </div>
  );
}

function PptxSlideFrame({ slide }: { readonly slide: ReportPreviewSlide }) {
  const kind = slide.kind || "content";
  const isDark = kind === "cover" || kind === "divider";

  if (isDark) {
    return (
      <div className="relative aspect-[16/9] w-full overflow-hidden rounded-lg bg-[#0F2A4A] text-white shadow-md">
        <div className="absolute right-0 top-0 h-14 w-24 bg-[#E87A2E]" />
        <div className="flex h-full flex-col justify-center px-10 py-8">
          {kind === "cover" ? (
            <>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-[#D4B88A]">
                {slide.title || "Investment Due Diligence · Market Intelligence"}
              </p>
              <h2 className="mt-3 text-[32px] font-bold leading-tight">
                {slide.subtitle && !slide.subtitle.toLowerCase().includes("ola")
                  ? slide.subtitle
                  : "Market Intel Deck"}
              </h2>
              {(slide.paragraphs || [])
                .filter((p) => p && p !== slide.subtitle && p !== slide.title)
                .slice(0, 2)
                .map((p) => (
                  <p key={p} className="mt-2 text-[14px] text-white/85">
                    {p}
                  </p>
                ))}
              {slide.meta_rows && slide.meta_rows.length > 0 ? (
                <div className="mt-8 grid grid-cols-2 gap-4 md:grid-cols-4">
                  {slide.meta_rows.map((row) => (
                    <div key={row[0]}>
                      <p className="text-[10px] font-semibold uppercase tracking-wide text-[#D4B88A]">
                        {row[0]}
                      </p>
                      <p className="mt-1 text-[13px] font-semibold">{row[1]}</p>
                    </div>
                  ))}
                </div>
              ) : null}
              <p className="mt-auto pt-8 text-[10px] uppercase tracking-wide text-white/70">
                Strictly Private &amp; Confidential · Prepared for Investment Committee
              </p>
            </>
          ) : (
            <>
              <p className="text-[56px] font-bold leading-none text-[#6B8FB5]">
                {slide.number || "—"}
              </p>
              <p className="mt-3 text-[11px] font-semibold uppercase tracking-wide text-white/90">
                {slide.eyebrow || `SECTION ${slide.number || ""}`}
              </p>
              <div className="mt-2 h-1 w-12 bg-[#E87A2E]" />
              <h2 className="mt-3 text-[28px] font-bold">{slide.title}</h2>
              {slide.subtitle ? (
                <p className="mt-2 max-w-xl text-[14px] text-white/80">{slide.subtitle}</p>
              ) : null}
            </>
          )}
        </div>
        <div className="absolute bottom-3 right-5 text-[11px] font-semibold text-white/80">
          {slide.page}
        </div>
      </div>
    );
  }

  return (
    <div className="relative aspect-[16/9] w-full overflow-hidden rounded-lg border border-[#e5e7eb] bg-white shadow-md">
      <div className="flex items-center justify-between px-5 pt-3">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-[#1F3864]">
          Market Intel Deck
        </p>
        <p className="text-[10px] font-semibold uppercase tracking-wide text-[#B91C1C]">
          Strictly Private &amp; Confidential
        </p>
      </div>
      <div className="mx-5 mt-1 h-[2px] bg-[#E87A2E]" />

      <div className="flex h-[calc(100%-3.2rem)] flex-col px-5 pb-8 pt-3">
        {slide.eyebrow ? (
          <p className="text-[10px] font-bold uppercase tracking-wide text-[#E87A2E]">
            {slide.eyebrow}
          </p>
        ) : null}
        <h2 className="mt-1 text-[18px] font-bold leading-snug text-[#1F3864]">{slide.title}</h2>
        <div className="mt-1 h-[3px] w-10 bg-[#E87A2E]" />
        {slide.subtitle ? (
          <p className="mt-2 text-[12px] text-[#6B7280]">{slide.subtitle}</p>
        ) : null}

        {slide.insight ? (
          <div className="mt-3 border-l-4 border-[#1F3864] bg-[#EEF2F7] px-3 py-2 text-[12px] text-[#1F3864]">
            <span className="font-semibold">Insight Snapshot: </span>
            {slide.insight}
          </div>
        ) : null}

        {kind === "agenda" && slide.agenda_items && slide.agenda_items.length > 0 ? (
          <div className="mt-3 space-y-2 overflow-auto">
            {slide.agenda_items.map((item) => (
              <div key={item.num} className="border-b border-[#E5E7EB] pb-2">
                <div className="flex items-start gap-3">
                  <span className="text-[20px] font-bold text-[#E87A2E]">{item.num}</span>
                  <div>
                    <p className="text-[13px] font-semibold text-[#1F3864]">{item.title}</p>
                    <p className="text-[11px] text-[#6B7280]">{item.blurb}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : null}

        {slide.cards && slide.cards.length > 0 ? (
          <div className="mt-3 grid flex-1 grid-cols-2 gap-2 overflow-auto md:grid-cols-3">
            {slide.cards.map((card, idx) => (
              <div
                key={`${card.label}-${idx}`}
                className="border border-[#E5E7EB] border-l-4 border-l-[#1F3864] bg-white p-2"
              >
                <p className="text-[10px] font-bold uppercase tracking-wide text-[#1F3864]">
                  <span className="mr-1 text-[#E87A2E]">{idx + 1}</span>
                  {card.label}
                </p>
                <p className="mt-1 text-[11px] leading-snug text-[#4B5563]">{card.body}</p>
              </div>
            ))}
          </div>
        ) : null}

        {slide.table && slide.table.length > 0 ? (
          <div className="mt-3 max-h-[55%] overflow-auto rounded border border-[#E5E7EB]">
            <table className="min-w-full border-collapse text-left text-[10px]">
              <tbody>
                {slide.table.map((row, ri) => (
                  <tr
                    key={`t-${ri}`}
                    className={ri === 0 ? "bg-[#1F3864] text-white" : ri % 2 ? "bg-[#F3F6FB]" : "bg-white"}
                  >
                    {row.map((cell, ci) => (
                      <td key={`c-${ri}-${ci}`} className="border border-[#E5E7EB]/px-2 py-1 align-top">
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {slide.bullets && slide.bullets.length > 0 ? (
          <ul className="mt-3 space-y-1.5 overflow-auto text-[12px] text-[#374151]">
            {slide.bullets.map((b, idx) => (
              <li key={`bu-${idx}`} className="flex gap-2">
                <span className="mt-[6px] h-[2px] w-3 shrink-0 bg-[#E87A2E]" />
                <span>{b}</span>
              </li>
            ))}
          </ul>
        ) : null}

        {(!slide.cards || slide.cards.length === 0) &&
        (!slide.bullets || slide.bullets.length === 0) &&
        (!slide.table || slide.table.length === 0) &&
        (!slide.agenda_items || slide.agenda_items.length === 0) &&
        slide.paragraphs &&
        slide.paragraphs.length > 0 ? (
          <div className="mt-3 space-y-1.5 overflow-auto text-[12px] text-[#374151]">
            {slide.paragraphs.slice(0, 8).map((p, idx) => (
              <p key={`p-${idx}`}>{p}</p>
            ))}
          </div>
        ) : null}
      </div>

      <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between border-t border-[#E87A2E] px-5 py-1.5">
        <p className="text-[9px] text-[#6B7280]">
          Investment Due Diligence · © Agentic CDD
        </p>
        <p className="text-[11px] font-semibold text-[#1F3864]">{slide.page}</p>
      </div>
    </div>
  );
}

function PptxPreview({
  slides,
  slideCount,
}: {
  readonly slides: ReportPreviewSlide[];
  readonly slideCount?: number;
}) {
  if (!slides.length) {
    return (
      <div className="py-10 text-center">
        <p className="text-[14px] font-medium text-text-primary">Preview is empty</p>
        <p className="mt-1 text-[13px] text-text-secondary">Regenerate the report, then try again.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-[#e5e7eb] bg-[#e8eaed] shadow-sm">
      <div className="flex items-center justify-between border-b border-[#d1d5db] bg-[#fafbfc] px-4 py-2">
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-secondary">
          Deck preview
        </p>
        <p className="text-[11px] text-text-secondary">
          {slideCount || slides.length} slides ·{" "}
          <span className="font-semibold text-[#B91C1C]">Strictly Private &amp; Confidential</span>
        </p>
      </div>
      <div className="max-h-[min(78vh,980px)] space-y-4 overflow-auto p-4">
        {slides.map((slide) => (
          <div key={`slide-${slide.index}`} className="mx-auto w-full max-w-4xl">
            <PptxSlideFrame slide={slide} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function DealReports({
  dealId,
  dealName,
  accessToken,
  onError,
}: {
  readonly dealId: string;
  readonly dealName: string;
  readonly accessToken?: string;
  readonly onError: (message: string | null) => void;
}) {
  const [catalog, setCatalog] = useState<ReportCatalogEntry[]>([]);
  const [view, setView] = useState<ViewMode>("catalog");
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState<ReportTab>("preview");
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [genLog, setGenLog] = useState<GenLogEntry[]>([]);
  const [storyline, setStoryline] = useState<ReportStorylineSection[]>([]);
  const [sources, setSources] = useState<ReportSourcesPayload["sources"] | null>(null);
  const [previewSheets, setPreviewSheets] = useState<string[]>([]);
  const [activeSheet, setActiveSheet] = useState<string>("");
  const [previewRows, setPreviewRows] = useState<Array<Array<string | number | boolean>>>([]);
  const [previewBlocks, setPreviewBlocks] = useState<ReportPreviewBlock[]>([]);
  const [previewSlides, setPreviewSlides] = useState<ReportPreviewSlide[]>([]);
  const [previewSlideCount, setPreviewSlideCount] = useState<number | undefined>(undefined);
  const [previewFormat, setPreviewFormat] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [pdfPreviewUrl, setPdfPreviewUrl] = useState<string>("");
  const [pdfPageCount, setPdfPageCount] = useState<number | undefined>(undefined);
  const [openDecision, setOpenDecision] = useState<Record<number, boolean>>({});

  const selectedReport = useMemo(
    () => catalog.find((r) => r.report_type === selected) ?? null,
    [catalog, selected],
  );

  const catalogView = useMemo(() => sortCatalog(catalog), [catalog]);

  const refreshCatalog = useCallback(async () => {
    if (!accessToken) return;
    const res = await reportsCatalogRequest(accessToken, dealId);
    setCatalog(res.data || []);
  }, [accessToken, dealId]);

  const loadDetail = useCallback(
    async (reportType: string) => {
      if (!accessToken) return;
      const [sl, src, status] = await Promise.all([
        reportStorylineRequest(accessToken, dealId, reportType),
        reportSourcesRequest(accessToken, dealId, reportType).catch(() => null),
        reportStatusRequest(accessToken, dealId, reportType),
      ]);
      setStoryline(sl.sections || []);
      setSources(src?.sources ?? null);
      setCatalog((prev) =>
        prev.map((item) => (item.report_type === reportType ? { ...item, ...status } : item)),
      );
    },
    [accessToken, dealId],
  );

  const loadPreview = useCallback(
    async (reportType: string, sheet?: string, exportFmt?: string) => {
      if (!accessToken) return;
      setPreviewLoading(true);
      try {
        const isPdf = exportFmt === "pdf";
        if (isPdf) {
          setPreviewFormat("pdf");
          setPreviewBlocks([]);
          setPreviewSlides([]);
          setPreviewSlideCount(undefined);
          setPreviewSheets([]);
          setActiveSheet("");
          setPreviewRows([]);
          const [url, meta] = await Promise.all([
            reportArtifactBlobUrlRequest(accessToken, dealId, reportType),
            reportPreviewRequest(accessToken, dealId, reportType).catch(() => null),
          ]);
          setPdfPreviewUrl((prev) => {
            if (prev) URL.revokeObjectURL(prev);
            return url;
          });
          setPdfPageCount(
            typeof meta?.page_count === "number" ? meta.page_count : undefined,
          );
          return;
        }

        const data: ReportPreviewPayload = await reportPreviewRequest(
          accessToken,
          dealId,
          reportType,
          sheet,
        );
        const fmt = data.format || (data.slides?.length ? "pptx" : data.blocks ? "docx" : "xlsx");
        setPreviewFormat(fmt);
        setPdfPreviewUrl((prev) => {
          if (prev) URL.revokeObjectURL(prev);
          return "";
        });
        setPdfPageCount(undefined);
        if (fmt === "pptx") {
          setPreviewSlides(data.slides || []);
          setPreviewSlideCount(
            typeof data.slide_count === "number" ? data.slide_count : data.slides?.length,
          );
          setPreviewBlocks(data.blocks || []);
          setPreviewSheets([]);
          setActiveSheet("");
          setPreviewRows([]);
        } else if (fmt === "docx" || fmt === "pdf") {
          setPreviewBlocks(data.blocks || []);
          setPreviewSlides([]);
          setPreviewSlideCount(undefined);
          setPreviewSheets([]);
          setActiveSheet("");
          setPreviewRows([]);
        } else {
          setPreviewSheets(data.sheets || []);
          setActiveSheet(data.active_sheet || data.sheets?.[0] || "");
          setPreviewRows(data.rows || []);
          setPreviewBlocks([]);
          setPreviewSlides([]);
          setPreviewSlideCount(undefined);
        }
      } catch (err) {
        onError(err instanceof ApiError ? err.message : "Failed to load preview");
      } finally {
        setPreviewLoading(false);
      }
    },
    [accessToken, dealId, onError],
  );

  useEffect(() => {
    return () => {
      if (pdfPreviewUrl) URL.revokeObjectURL(pdfPreviewUrl);
    };
  }, [pdfPreviewUrl]);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    onError(null);
    void (async () => {
      try {
        await refreshCatalog();
      } catch (err) {
        onError(err instanceof ApiError ? err.message : "Failed to load reports");
      } finally {
        setLoading(false);
      }
    })();
  }, [accessToken, refreshCatalog, onError]);

  useEffect(() => {
    if (!accessToken || !selected || view !== "detail") return;
    void loadDetail(selected).catch((err) => {
      onError(err instanceof ApiError ? err.message : "Failed to load report detail");
    });
  }, [accessToken, selected, view, loadDetail, onError]);

  useEffect(() => {
    if (!accessToken || !selectedReport || selectedReport.status !== "ready") return;
    if (view !== "detail" || tab !== "preview") return;
    const fmt = selectedReport.export;
    if (fmt !== "xlsx" && fmt !== "docx" && fmt !== "pdf" && fmt !== "pptx") return;
    void loadPreview(selectedReport.report_type, undefined, selectedReport.export);
  }, [accessToken, selectedReport, tab, view, loadPreview]);

  function openReport(reportType: string) {
    setSelected(reportType);
    setView("detail");
    setTab("preview");
    setGenLog([]);
    setOpenDecision({});
    onError(null);
  }

  function backToCatalog() {
    setView("catalog");
    setSelected(null);
    setGenLog([]);
  }

  async function onGenerate() {
    if (!accessToken || !selected || !IMPLEMENTED_REPORTS.has(selected)) return;
    setGenerating(true);
    setGenLog([]);
    onError(null);
    try {
      await reportGenerateRequest(accessToken, dealId, selected);
      setCatalog((prev) =>
        prev.map((item) =>
          item.report_type === selected ? { ...item, status: "running" } : item,
        ),
      );
      await reportEventsStream(accessToken, dealId, selected, {
        onEvent: (evt) => {
          setGenLog((prev) => [
            ...prev,
            {
              stage: String(evt.stage || "info"),
              message: String(evt.message || ""),
              level: evt.level ? String(evt.level) : undefined,
              t: typeof evt.t === "number" ? evt.t : undefined,
            },
          ]);
        },
        onError: (message) => onError(message),
      });
      await refreshCatalog();
      await loadDetail(selected);
      const exportFmt = selectedReport?.export;
      if (exportFmt === "xlsx" || exportFmt === "docx" || exportFmt === "pdf") {
        await loadPreview(selected, undefined, exportFmt);
      }
      setTab("preview");
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Generation failed");
      await refreshCatalog();
    } finally {
      setGenerating(false);
    }
  }

  async function onDownload() {
    if (!accessToken || !selected || selectedReport?.status !== "ready") return;
    onError(null);
    try {
      const name = `${dealName}_${(selectedReport!.label || selected).replace(/\s+/g, "_")}.${selectedReport!.export}`;
      await reportDownloadRequest(accessToken, dealId, selected, name);
    } catch (err) {
      onError(err instanceof ApiError ? err.message : "Download failed");
    }
  }

  async function onSheetChange(sheet: string) {
    if (!selected) return;
    setActiveSheet(sheet);
    await loadPreview(selected, sheet, selectedReport?.export);
  }

  const badge = selectedReport ? statusBadge(selectedReport.status) : statusBadge("not_generated");
  const isImplemented = selected ? IMPLEMENTED_REPORTS.has(selected) : false;

  // ----- Catalog view -----
  if (view === "catalog") {
    return (
      <div className="space-y-6">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 inline-grid h-9 w-9 place-items-center rounded-lg bg-[#e8eef5] text-[#1e3a5f]">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M8 3h8l4 4v14H8V3z" />
              <path d="M16 3v5h5" />
            </svg>
          </span>
          <div>
            <h1 className="text-[22px] font-semibold tracking-tight text-text-primary">Reports</h1>
            <p className="mt-1 max-w-2xl text-[13px] text-text-secondary">
              Institutional deliverables from this deal — including FDD Report (Word/PDF) and FDD IC Deck.
              Open a card, then click Generate.
            </p>
          </div>
        </div>

        {loading ? <p className="text-[13px] text-text-secondary">Loading report catalog…</p> : null}

        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {catalogView.map((report) => {
            const itemBadge = statusBadge(report.status);
            const ready = report.status === "ready";
            const implemented = IMPLEMENTED_REPORTS.has(report.report_type);
            const isFdd = report.report_type.startsWith("fdd_");
            return (
              <button
                key={report.report_type}
                type="button"
                onClick={() => openReport(report.report_type)}
                className="group flex flex-col rounded-[12px] border border-border-primary bg-white p-5 text-left shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition
                  hover:border-[#2563eb] hover:bg-[#f8fafc] hover:shadow-[0_4px_14px_rgba(37,99,235,0.12)]
                  focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2563eb] focus-visible:ring-offset-2
                  active:border-[#1d4ed8] active:bg-[#eff6ff]"
              >
                <div className="mb-3 flex items-start justify-between gap-2">
                  <span className="inline-grid h-10 w-10 place-items-center rounded-lg bg-[#eef3f8] text-[#1e3a5f] transition group-hover:bg-[#dbeafe] group-hover:text-[#1d4ed8]">
                    <ReportTypeIcon format={report.format} />
                  </span>
                  <div className="flex flex-col items-end gap-1">
                    {isFdd ? (
                      <span className="rounded-full bg-[#eff6ff] px-2.5 py-0.5 text-[11px] font-semibold text-[#1d4ed8] ring-1 ring-[#bfdbfe]">
                        New · FDD
                      </span>
                    ) : null}
                    <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${itemBadge.className}`}>
                      {itemBadge.label}
                    </span>
                  </div>
                </div>
                <h2 className="text-[16px] font-semibold text-text-primary group-hover:text-[#1e3a5f]">
                  {report.label}
                </h2>
                <p className="mt-1 text-[11px] font-semibold uppercase tracking-[0.06em] text-text-secondary">
                  {formatKind(report)}
                </p>
                <p className="mt-3 flex-1 text-[13px] leading-relaxed text-text-secondary">{report.description}</p>
                <div className="mt-4 border-t border-border-primary pt-3 group-hover:border-[#bfdbfe]">
                  <span className="inline-flex items-center gap-1.5 text-[13px] font-medium text-[#2563eb] group-hover:text-[#1d4ed8]">
                    {ready ? (
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="9" />
                        <path d="M8 12l2.5 2.5L16 9" />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M5 12h14M13 6l6 6-6 6" />
                      </svg>
                    )}
                    Open
                  </span>
                  {!implemented ? (
                    <p className="mt-1 text-[11px] text-[#9ca3af]">Generate coming soon — storyline available</p>
                  ) : null}
                </div>
              </button>
            );
          })}
        </section>
      </div>
    );
  }

  // ----- Detail view -----
  if (!selectedReport) {
    return (
      <div className="space-y-3">
        <button type="button" onClick={backToCatalog} className="text-[13px] text-[#2563eb]">
          ← Back to Reports
        </button>
        <p className="text-[13px] text-text-secondary">Report not found.</p>
      </div>
    );
  }

  const detailSubtitle = `${formatKind(selectedReport).charAt(0)}${formatKind(selectedReport).slice(1).toLowerCase()} — ${selectedReport.description}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center gap-2">
            <button
              type="button"
              onClick={backToCatalog}
              aria-label="Back to Reports"
              className="inline-grid h-8 w-8 place-items-center rounded-lg text-text-secondary hover:bg-[#eef0f3] hover:text-text-primary"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M15 6 9 12l6 6" />
              </svg>
            </button>
            <span className="inline-grid h-8 w-8 place-items-center rounded-lg bg-[#eef3f8] text-[#1e3a5f]">
              <ReportTypeIcon format={selectedReport.format} />
            </span>
            <h1 className="text-[22px] font-semibold tracking-tight text-text-primary">{selectedReport.label}</h1>
          </div>
          <p className="max-w-3xl text-[13px] text-text-secondary">{detailSubtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${badge.className}`}>
            {badge.label}
          </span>
          {selectedReport.status === "ready" ? (
            <button
              type="button"
              onClick={() => void onDownload()}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border-primary bg-white px-3 py-2 text-[13px] font-medium text-text-primary hover:bg-[#fafafa]"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M12 4v10" />
                <path d="m8 10 4 4 4-4" />
                <path d="M5 20h14" />
              </svg>
              {downloadLabel(selectedReport)}
            </button>
          ) : null}
          {isImplemented ? (
            <button
              type="button"
              disabled={generating}
              onClick={() => void onGenerate()}
              className="inline-flex items-center gap-1.5 rounded-lg bg-[#1e3a5f] px-3 py-2 text-[13px] font-medium text-white hover:bg-[#16304f] disabled:opacity-60"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M21 12a9 9 0 1 1-2.6-6.3" />
                <path d="M21 4v5h-5" />
              </svg>
              {generating ? "Generating…" : selectedReport.status === "ready" ? "Regenerate" : "Generate"}
            </button>
          ) : (
            <span className="rounded-lg bg-[#f3f4f6] px-3 py-2 text-[12px] text-text-secondary">
              Builder coming soon
            </span>
          )}
        </div>
      </div>

      {(generating || genLog.length > 0) && isImplemented ? (
        <div className="rounded-[10px] border border-border-primary bg-[#f8f9fb] px-4 py-3">
          <p className="mb-2 text-[12px] font-semibold text-text-primary">Generation log</p>
          <ul className="max-h-40 space-y-1 overflow-y-auto font-mono text-[11px] text-text-secondary">
            {genLog.map((entry, i) => (
              <li key={`${entry.stage}-${i}`}>
                <span className="font-semibold text-[#1e3a5f]">[{entry.stage}]</span> {entry.message}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="border-b border-border-primary">
        <nav className="flex gap-1">
          {(
            [
              { id: "preview" as const, label: "Preview", icon: "eye" },
              {
                id: "storyline" as const,
                label: storyline.length ? `Storyline (${storyline.length})` : "Storyline",
                icon: "list",
              },
              { id: "sources" as const, label: "Sources", icon: "link" },
            ]
          ).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setTab(item.id)}
              className={`inline-flex items-center gap-1.5 border-b-2 px-3 py-2.5 text-[13px] font-medium ${
                tab === item.id
                  ? "border-[#2563eb] text-[#1e3a5f]"
                  : "border-transparent text-text-secondary hover:text-text-primary"
              }`}
            >
              {item.icon === "eye" ? (
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" />
                  <circle cx="12" cy="12" r="3" />
                </svg>
              ) : null}
              {item.icon === "list" ? (
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
                </svg>
              ) : null}
              {item.icon === "link" ? (
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <path d="M10 13a5 5 0 0 0 7.07 0l2.12-2.12a5 5 0 0 0-7.07-7.07L11 5" />
                  <path d="M14 11a5 5 0 0 0-7.07 0L4.8 13.12a5 5 0 0 0 7.07 7.07L13 19" />
                </svg>
              ) : null}
              {item.label}
            </button>
          ))}
        </nav>
      </div>

      <div className="rounded-[10px] border border-border-primary bg-white p-5">
        {tab === "preview" ? (
          selectedReport.status !== "ready" ? (
            <div className="py-14 text-center">
              <p className="text-[15px] font-medium text-text-primary">No preview yet</p>
              <p className="mt-1 text-[13px] text-text-secondary">
                {isImplemented
                  ? "Generate the report to preview it here."
                  : "This report type is not implemented yet."}
              </p>
              {isImplemented ? (
                <button
                  type="button"
                  disabled={generating}
                  onClick={() => void onGenerate()}
                  className="mt-4 rounded-lg bg-[#1e3a5f] px-4 py-2 text-[13px] font-medium text-white"
                >
                  Generate
                </button>
              ) : null}
            </div>
          ) : selectedReport.export !== "xlsx" &&
            selectedReport.export !== "docx" &&
            selectedReport.export !== "pdf" &&
            selectedReport.export !== "pptx" ? (
            <div className="py-14 text-center">
              <p className="text-[14px] font-medium text-text-primary">Preview not available for this format</p>
              <p className="mt-1 text-[13px] text-text-secondary">Use {downloadLabel(selectedReport)} to open the file.</p>
            </div>
          ) : previewLoading ? (
            <p className="text-[13px] text-text-secondary">Loading preview…</p>
          ) : previewFormat === "pdf" || selectedReport.export === "pdf" ? (
            <PdfPreview url={pdfPreviewUrl} pageCount={pdfPageCount} />
          ) : previewFormat === "pptx" || selectedReport.export === "pptx" ? (
            <PptxPreview slides={previewSlides} slideCount={previewSlideCount} />
          ) : previewFormat === "docx" || selectedReport.export === "docx" ? (
            <DocxPreview blocks={previewBlocks} />
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap gap-1 border-b border-border-primary pb-2">
                {previewSheets.map((sheet) => (
                  <button
                    key={sheet}
                    type="button"
                    onClick={() => void onSheetChange(sheet)}
                    className={`rounded px-3 py-1.5 text-[12px] font-medium ${
                      sheet === activeSheet
                        ? "bg-[#1e3a5f] text-white"
                        : "bg-[#eef0f3] text-text-primary hover:bg-[#e5e7eb]"
                    }`}
                  >
                    {sheet}
                  </button>
                ))}
              </div>
              <div className="overflow-auto rounded-lg border border-border-primary">
                <table className="min-w-full border-collapse text-left text-[12px]">
                  <tbody>
                    {previewRows.map((row, ri) => (
                        <tr
                          key={`r-${ri}`}
                          className={
                            ri === 0
                              ? "bg-[#1F3864] text-white"
                              : ri % 2 === 0
                                ? "bg-white"
                                : "bg-[#f8f9fb]"
                          }
                        >
                          {row.map((cell, ci) => (
                            <td
                              key={`c-${ri}-${ci}`}
                              className={`border border-[#e5e7eb] px-2 py-1.5 whitespace-nowrap ${
                                ri === 0 ? "font-semibold" : "text-text-primary"
                              }`}
                            >
                              {ri > 0 && isRagCell(cell) ? <RagCell value={cell} /> : String(cell ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </div>
          )
        ) : null}

        {tab === "storyline" ? (
          <div className="space-y-3">
            <p className="text-[13px] text-text-secondary">
              Sections included in this {selectedReport.label}. Toggle inclusion is saved with the next regenerate.
            </p>
            {storyline.map((section) => (
              <article key={section.idx} className="rounded-lg border border-border-primary px-4 py-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-[14px] font-semibold text-text-primary">
                      {section.idx}. {section.title}
                    </p>
                    <p className="mt-0.5 text-[11px] uppercase tracking-wide text-text-secondary">
                      KIND: {section.kind} · {section.included ? "Included" : "Excluded"}
                    </p>
                  </div>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                      section.included ? "bg-[#ecfdf3] text-[#15803d]" : "bg-[#f3f4f6] text-[#6b7280]"
                    }`}
                  >
                    {section.included ? "On" : "Off"}
                  </span>
                </div>
                {section.agents?.length ? (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {section.agents.map((agent) => (
                      <span
                        key={agent}
                        className="rounded-full bg-[#eef0f3] px-2.5 py-0.5 text-[11px] font-medium text-[#4b5563]"
                      >
                        {agentLabel(agent)}
                      </span>
                    ))}
                  </div>
                ) : null}
              </article>
            ))}
            {!storyline.length ? (
              <p className="text-[13px] text-text-secondary">No storyline sections configured for this report.</p>
            ) : null}
          </div>
        ) : null}

        {tab === "sources" ? (
          <div className="space-y-5">
            <div>
              <p className="text-[14px] text-text-primary">
                Everything this {selectedReport.label} was built from — the deal&apos;s data room, live web research, and
                the workflow analyst document.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded-full bg-[#eef0f3] px-3 py-1 text-[12px] font-medium text-text-primary">
                  {sources?.data_room_files ?? 0} data-room files
                </span>
                <span className="rounded-full bg-[#eef0f3] px-3 py-1 text-[12px] font-medium text-text-primary">
                  Web research {sources?.web_research ? "on" : "off"}
                </span>
                <span className="rounded-full bg-[#eef0f3] px-3 py-1 text-[12px] font-medium text-text-primary">
                  Workflow agents — {sources?.workflow_agents ?? 0} agents across{" "}
                  {(sources?.sections || storyline).length || 0} sections
                </span>
                <span className="rounded-full bg-[#eef0f3] px-3 py-1 text-[12px] font-medium text-text-primary">
                  {sources?.analyst_document ? "Analyst document attached" : "No analyst document"}
                </span>
                {(sources?.cited_file_count ?? 0) > 0 ? (
                  <span className="rounded-full bg-[#eef0f3] px-3 py-1 text-[12px] font-medium text-text-primary">
                    {sources?.cited_file_count} cited inputs
                  </span>
                ) : null}
              </div>
              {sources?.files?.length ? (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {sources.files.map((file) => (
                    <span
                      key={file}
                      className="rounded border border-[#e5e7eb] bg-white px-2 py-0.5 text-[11px] text-[#4b5563]"
                    >
                      {file}
                    </span>
                  ))}
                </div>
              ) : null}
            </div>

            <div>
              <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.08em] text-text-secondary">
                How each part of the storyline was built
              </p>
              <div className="space-y-3">
                {(sources?.sections?.length
                  ? sources.sections.map((s, i) => ({
                      idx: i + 1,
                      title: s.title,
                      agents: s.agents,
                      source_files: s.source_files || [],
                      decision_chain: (s.decision_chain || []) as ReportDecisionChainEntry[],
                    }))
                  : storyline.map((s) => ({
                      idx: s.idx,
                      title: s.title,
                      agents: s.agents,
                      source_files: [] as string[],
                      decision_chain: [] as ReportDecisionChainEntry[],
                    }))
                ).map((section) => (
                  <article key={section.idx} className="rounded-[10px] border border-border-primary px-4 py-3">
                    <div className="flex items-start gap-3">
                      <span className="inline-grid h-7 w-7 shrink-0 place-items-center rounded-full bg-[#eef3f8] text-[12px] font-semibold text-[#1e3a5f]">
                        {section.idx}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[14px] font-semibold text-text-primary">{section.title}</p>
                        <p className="mt-0.5 text-[12px] text-text-secondary">
                          Built from the deal&apos;s data room, with figures computed from the financials and workflow
                          agent outputs.
                        </p>
                        <div className="mt-2">
                          <p className="mb-1 text-[11px] font-medium text-text-secondary">Workflow analysis</p>
                          <div className="flex flex-wrap gap-1.5">
                            {section.agents.map((agent) => (
                              <span
                                key={agent}
                                className="rounded-full bg-[#eef0f3] px-2.5 py-0.5 text-[11px] font-medium text-[#4b5563]"
                              >
                                {agentLabel(agent)}
                              </span>
                            ))}
                          </div>
                        </div>
                        {section.source_files.length ? (
                          <div className="mt-2">
                            <p className="mb-1 text-[11px] font-medium text-text-secondary">Source document(s)</p>
                            <div className="flex flex-wrap gap-1.5">
                              {section.source_files.map((file) => (
                                <span
                                  key={`${section.idx}-${file}`}
                                  className="rounded border border-[#e5e7eb] bg-white px-2 py-0.5 text-[11px] text-[#4b5563]"
                                >
                                  {file}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        <button
                          type="button"
                          onClick={() =>
                            setOpenDecision((prev) => ({ ...prev, [section.idx]: !prev[section.idx] }))
                          }
                          className="mt-2 inline-flex items-center gap-1 text-[12px] font-medium text-[#2563eb]"
                        >
                          <span>{openDecision[section.idx] ? "▾" : "▸"}</span>
                          Decision chain — source + calculation for every number
                        </button>
                        {openDecision[section.idx] ? (
                          <DecisionChainPanel
                            key={`dc-panel-${section.idx}`}
                            entries={section.decision_chain}
                            sectionAgents={section.agents}
                          />
                        ) : null}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
