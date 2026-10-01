"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ApiError,
  agentDocumentGetRequest,
  agentDocumentMessagesRequest,
  agentDocumentPostMessageRequest,
  agentDocumentPostMessageStream,
  agentDocumentPutRequest,
  agentDocumentSuggestionsRequest,
  agentDocumentVersionGetRequest,
  agentDocumentVersionsRequest,
  cddCapabilitiesRequest,
  documentExportRequest,
  documentGetRequest,
  documentMessagesRequest,
  documentPostMessageRequest,
  documentPostMessageStream,
  documentPutRequest,
  documentSuggestionsRequest,
  type AgentDocumentVersion,
  type DocumentCapability,
  type DocumentDecisionStep,
  type DocumentCopilotMeta,
  type DocumentMessage,
  type DocumentMessageSource,
  type DocumentNextStep,
  type DocumentSuggestionCard,
  type DocumentTask,
  type DocumentTaskSource,
} from "@/lib/api";
import { CapabilityCatalogPanel } from "@/components/deal/CapabilityCatalogPanel";
import { DocumentChartExhibit } from "@/components/deal/DocumentChartExhibit";
import type { DocumentChartSpec } from "@/lib/documentChart";

type DocTab = "preview" | "edit" | "sources" | "chain" | "versions" | "settings";

function kindBadge(kind: string): string {
  if (kind === "internal") return "Data room";
  if (kind === "web") return "Web";
  if (kind === "algo") return "Algo";
  return kind;
}

function formatTaskMs(ms?: number): string {
  if (ms == null || ms < 0) return "";
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1).replace(/\.0$/, "")}s`;
}

function truncateTitle(title: string, max = 28): string {
  const t = title.replace(/^Run analysis:\s*/i, "").replace(/^Web research:\s*/i, "");
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function collectTaskSources(tasks: DocumentTask[]): DocumentTaskSource[] {
  const seen = new Set<string>();
  const out: DocumentTaskSource[] = [];
  for (const task of tasks) {
    for (const src of task.detail?.sources || []) {
      const key = src.title;
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(src);
    }
  }
  return out;
}

function parseSourceLines(markdown: string): string[] {
  const idx = markdown.search(/^## Sources\s*$/m);
  if (idx < 0) return [];
  const block = markdown.slice(idx).split("\n").slice(1);
  return block
    .map((line) => line.trim())
    .filter((line) => /^(\*\*)?\[\d+]/.test(line) || line.startsWith("**["));
}

function buildChainFromMessages(messages: DocumentMessage[]): DocumentDecisionStep[] {
  const steps: DocumentDecisionStep[] = [];
  let pending: DocumentMessage | null = null;
  for (const msg of messages) {
    if (msg.role === "user") {
      pending = msg;
      continue;
    }
    if (msg.role !== "assistant") continue;
    steps.push({
      id: msg.id,
      ts: msg.ts || pending?.ts,
      prompt: pending?.content || "",
      answer: msg.content || "",
      tasks: (msg.tasks || []).map((t) => ({
        id: t.id,
        title: t.title,
        label: t.label,
        tool: t.tool,
        status: t.status,
        capability_id: t.detail?.capability_id,
        ms: t.ms,
      })),
      source_count: (msg.sources || []).length,
    });
    pending = null;
  }
  return steps;
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function MarkdownDoc({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const lines = text.replace(/\r\n/g, "\n").split("\n");
    const out: Array<{
      type: string;
      text: string;
      chart?: DocumentChartSpec;
      rows?: string[][];
    }> = [];
    let para: string[] = [];
    const flushPara = () => {
      if (!para.length) return;
      out.push({ type: "p", text: para.join(" ").trim() });
      para = [];
    };
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i].trimEnd();
      if (!line.trim()) {
        flushPara();
        continue;
      }
      if (line.startsWith("|") && line.includes("|", 1)) {
        flushPara();
        const collected: string[][] = [];
        let j = i;
        while (j < lines.length && lines[j].trim().startsWith("|")) {
          const cells = lines[j]
            .trim()
            .replace(/^\|/, "")
            .replace(/\|$/, "")
            .split("|")
            .map((c) => c.trim());
          if (!cells.every((c) => /^:?-{3,}:?$/.test(c))) {
            collected.push(cells);
          }
          j += 1;
        }
        if (collected.length) {
          out.push({ type: "table", text: "", rows: collected });
        }
        i = j - 1;
        continue;
      }
      if (line.startsWith("> ")) {
        flushPara();
        out.push({ type: "quote", text: line.replace(/^>\s*/, "").replace(/^\*\*Insight Snapshot:\*\*\s*/i, "") });
        continue;
      }
      if (line.startsWith("### ")) {
        flushPara();
        out.push({ type: "h3", text: line.slice(4) });
        continue;
      }
      if (line.startsWith("## ")) {
        flushPara();
        out.push({ type: "h2", text: line.slice(3) });
        continue;
      }
      if (line.startsWith("# ")) {
        flushPara();
        out.push({ type: "h1", text: line.slice(2) });
        continue;
      }
      if (line.startsWith("- ") || line.startsWith("* ")) {
        flushPara();
        out.push({ type: "li", text: line.slice(2) });
        continue;
      }
      if (line.startsWith("[[CHART:")) {
        flushPara();
        const label = line.replace(/^\[\[CHART:\s*/i, "").replace(/\]\]$/, "");
        let chart: DocumentChartSpec | undefined;
        const next = lines[i + 1]?.trim() || "";
        if (next.startsWith("<!-- cdd:chart ")) {
          const raw = next.replace(/^<!--\s*cdd:chart\s*/, "").replace(/\s*-->$/, "");
          try {
            chart = JSON.parse(raw) as DocumentChartSpec;
          } catch {
            chart = undefined;
          }
          i += 1;
        }
        out.push({ type: "chart", text: label, chart });
        continue;
      }
      if (line.startsWith("<!--")) {
        flushPara();
        continue;
      }
      para.push(line.trim());
    }
    flushPara();
    return out;
  }, [text]);

  return (
    <div className="prose-doc space-y-3 text-[14px] leading-relaxed text-text-primary">
      {blocks.map((block, i) => {
        if (block.type === "h1") {
          return (
            <h1 key={i} className="text-[22px] font-semibold tracking-tight text-text-primary">
              {renderInline(block.text)}
            </h1>
          );
        }
        if (block.type === "h2") {
          return (
            <h2 key={i} className="mt-4 text-[17px] font-semibold text-text-primary">
              {renderInline(block.text)}
            </h2>
          );
        }
        if (block.type === "h3") {
          return (
            <h3 key={i} className="mt-3 text-[15px] font-semibold text-text-primary">
              {renderInline(block.text)}
            </h3>
          );
        }
        if (block.type === "li") {
          return (
            <li key={i} className="ml-5 list-disc text-[14px]">
              {renderInline(block.text)}
            </li>
          );
        }
        if (block.type === "quote") {
          return (
            <div
              key={i}
              className="rounded-r-md border-l-4 border-[#1F3864] bg-[#E8EEF7] px-3 py-2 text-[13px] text-[#374151]"
            >
              <span className="font-semibold text-[#1F3864]">Insight Snapshot: </span>
              {renderInline(block.text)}
            </div>
          );
        }
        if (block.type === "table" && block.rows?.length) {
          return (
            <div key={i} className="overflow-x-auto rounded-md border border-[#e5e7eb]">
              <table className="min-w-full border-collapse text-left text-[12px]">
                <tbody>
                  {block.rows.map((row, ri) => (
                    <tr
                      key={ri}
                      className={ri === 0 ? "bg-[#1F3864] text-white" : ri % 2 ? "bg-[#F3F6FB]" : "bg-white"}
                    >
                      {row.map((cell, ci) => (
                        <td key={ci} className="border border-[#e5e7eb] px-2.5 py-1.5 align-top">
                          {renderInline(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.type === "chart") {
          return (
            <DocumentChartExhibit key={i} label={block.text} chart={block.chart} />
          );
        }
        return (
          <p key={i} className="text-[14px]">
            {renderInline(block.text)}
          </p>
        );
      })}
    </div>
  );
}

function renderInline(text: string) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    if (/^\[\d+]$/.test(part)) {
      return (
        <span
          key={i}
          className="mx-0.5 inline-flex rounded bg-[#eff6ff] px-1 text-[11px] font-medium text-[#1d4ed8]"
        >
          {part}
        </span>
      );
    }
    // Strip leftover markdown bold markers for insight lines
    const cleaned = part.replace(/\*\*/g, "");
    return <span key={i}>{cleaned}</span>;
  });
}

function PlanExecution({
  tasks,
  defaultOpen = true,
}: {
  tasks: DocumentTask[];
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  if (!tasks.length) return null;
  const done = tasks.filter((t) => t.status === "done" || t.status === "completed").length;
  const total = tasks.length;
  const pct = Math.round((done / Math.max(total, 1)) * 100);

  return (
    <div className="overflow-hidden rounded-lg border border-border-primary bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
      >
        <span className="text-[11px] text-text-secondary">{open ? "▾" : "▸"}</span>
        <span className="text-[12px] font-semibold text-text-primary">Plan &amp; execution</span>
        <span className="ml-auto text-[11px] tabular-nums text-text-secondary">
          {done}/{total}
        </span>
      </button>
      <div className="px-3 pb-2">
        <div className="h-1.5 overflow-hidden rounded-full bg-[#eef0f3]">
          <div className="h-full rounded-full bg-[#22c55e] transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
      {open ? (
        <ul className="space-y-1 border-t border-border-primary px-2 py-2">
          {tasks.map((task) => {
            const running = task.status === "running" || task.status === "pending";
            const failed = task.status === "failed" || task.status === "error";
            return (
              <li
                key={task.id}
                className="flex items-center gap-2 rounded-md px-1.5 py-1.5 text-[12px]"
              >
                <span
                  className={`inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[10px] font-bold text-white ${
                    failed ? "bg-[#dc2626]" : running ? "bg-[#93c5fd]" : "bg-[#22c55e]"
                  }`}
                >
                  {failed ? "!" : running ? "…" : "✓"}
                </span>
                <span className="min-w-0 flex-1 truncate text-text-primary">
                  <span className="text-text-secondary">{task.label || "Data room"} </span>
                  {truncateTitle(task.title)}
                </span>
                {task.ms != null && !running ? (
                  <span className="shrink-0 tabular-nums text-[10px] text-text-secondary">
                    {formatTaskMs(task.ms)}
                  </span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

function formatSourceCitation(
  sectionLabel?: string | null,
  chunkIndex?: number | null,
): string | null {
  const parts: string[] = [];
  if (sectionLabel?.trim()) parts.push(sectionLabel.trim());
  if (chunkIndex != null && chunkIndex >= 0) parts.push(`chunk ${chunkIndex + 1}`);
  return parts.length ? parts.join(" · ") : null;
}

function SourceCards({
  taskSources,
  messageSources,
}: {
  taskSources: DocumentTaskSource[];
  messageSources?: DocumentMessageSource[];
}) {
  const cards =
    taskSources.length > 0
      ? taskSources.map((s) => ({
          title: s.title,
          snippet: s.snippet || "",
          url: s.url,
          citation: formatSourceCitation(s.section_label, s.chunk_index),
        }))
      : (messageSources || []).map((s) => ({
          title: s.title,
          snippet: s.snippet || "",
          url: s.url || undefined,
          citation: formatSourceCitation(s.section_label, s.chunk_index),
        }));
  if (!cards.length) return null;
  return (
    <div className="space-y-2">
      {cards.slice(0, 8).map((card, i) => (
        <div
          key={`${card.title}-${i}`}
          className="rounded-lg border border-border-primary bg-white px-3 py-2.5 shadow-sm"
        >
          <p className="truncate text-[12px] font-semibold text-text-primary">
            {card.url ? (
              <a href={card.url} target="_blank" rel="noreferrer" className="hover:underline">
                {card.title}
              </a>
            ) : (
              card.title
            )}
          </p>
          {card.citation ? (
            <p className="mt-0.5 text-[10px] font-medium uppercase tracking-wide text-[#64748b]">
              {card.citation}
            </p>
          ) : null}
          {card.snippet ? (
            <p className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-text-secondary">
              {card.snippet}
            </p>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function NextStepIcon({ icon }: { icon?: string }) {
  const common = {
    viewBox: "0 0 24 24",
    width: 14,
    height: 14,
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
  } as const;
  if (icon === "business") {
    return (
      <svg {...common}>
        <rect x="3" y="7" width="18" height="13" rx="1.5" />
        <path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      </svg>
    );
  }
  if (icon === "growth") {
    return (
      <svg {...common}>
        <path d="M4 18 10 10l4 3 6-8" />
        <path d="M16 5h4v4" />
      </svg>
    );
  }
  if (icon === "risks") {
    return (
      <svg {...common}>
        <path d="M12 3 2 20h20L12 3Z" />
        <path d="M12 10v4" />
        <path d="M12 17h.01" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <path d="M12 2a10 10 0 1 0 10 10h-10V2Z" />
      <path d="M14 2.2A10 10 0 0 1 21.8 10H14V2.2Z" />
    </svg>
  );
}

function SmartCopilotChip({
  meta,
  open,
  onClick,
}: {
  meta: DocumentCopilotMeta | null;
  open?: boolean;
  onClick?: () => void;
}) {
  if (!meta) return null;
  const title = meta.model ? `${meta.mode_label} · ${meta.model}` : meta.mode_label;
  return (
    <button
      type="button"
      title={title}
      aria-label={`${title}. Open capability catalog.`}
      aria-expanded={open}
      onClick={onClick}
      className={`mb-2 inline-flex max-w-full items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] font-medium transition ${
        open
          ? "border-[#93c5fd] bg-[#dbeafe] text-[#1e40af]"
          : "border-[#dbeafe] bg-[#eff6ff] text-[#1d4ed8] hover:border-[#93c5fd] hover:bg-[#dbeafe]"
      }`}
    >
      <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden>
        <path d="M12 2 9.5 9.5 2 12l7.5 2.5L12 22l2.5-7.5L22 12l-7.5-2.5L12 2Z" />
      </svg>
      <span className="truncate">{meta.mode_label}</span>
      <span className="text-[#64748b]">·</span>
      <span className="shrink-0 tabular-nums text-[#475569]">{meta.capability_count}</span>
      <svg
        viewBox="0 0 24 24"
        width="12"
        height="12"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden
      >
        <path d="m9 6 6 6-6 6" />
      </svg>
    </button>
  );
}

function SuggestedNextSteps({
  steps,
  disabled,
  onSelect,
}: {
  steps: DocumentNextStep[];
  disabled?: boolean;
  onSelect: (prompt: string) => void;
}) {
  if (!steps.length) return null;
  return (
    <div className="pt-1">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-text-secondary">
        # Suggested next steps
      </p>
      <div className="flex flex-wrap gap-2">
        {steps.map((step) => (
          <button
            key={step.title}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(step.prompt)}
            className="inline-flex items-center gap-1.5 rounded-full border border-border-primary bg-white px-3 py-1.5 text-[12px] font-medium text-text-primary shadow-sm transition hover:border-[#93c5fd] hover:bg-[#f8fbff] disabled:opacity-50"
          >
            <span className="text-[#1d4ed8]">
              <NextStepIcon icon={step.icon} />
            </span>
            {step.title}
          </button>
        ))}
      </div>
    </div>
  );
}

function AssistantTurn({
  message,
  fallbackNextSteps,
  showNextSteps,
  sending,
  onNextStep,
}: {
  message: DocumentMessage;
  fallbackNextSteps: DocumentNextStep[];
  showNextSteps: boolean;
  sending: boolean;
  onNextStep: (prompt: string) => void;
}) {
  const tasks = message.tasks || [];
  const taskSources = collectTaskSources(tasks);
  const steps = fallbackNextSteps.length
    ? fallbackNextSteps
    : message.next_steps?.length
      ? message.next_steps
      : [];
  return (
    <div className="space-y-3">
      {message.content ? (
        <div className="rounded-[10px] border border-border-primary bg-white px-3 py-2 text-[13px] text-text-primary">
          {message.content}
        </div>
      ) : null}
      <PlanExecution tasks={tasks} />
      <SourceCards taskSources={taskSources} messageSources={message.sources} />
      {showNextSteps ? (
        <SuggestedNextSteps steps={steps} disabled={sending} onSelect={onNextStep} />
      ) : null}
    </div>
  );
}

export function DealDocumentWorkspace({
  dealId,
  dealName,
  accessToken,
  onError,
  agentKey,
}: {
  dealId: string;
  dealName: string;
  accessToken?: string;
  onError?: (message: string | null) => void;
  agentKey?: string | null;
}) {
  const [tab, setTab] = useState<DocTab>("preview");
  const [markdown, setMarkdown] = useState("");
  const [exists, setExists] = useState(false);
  const [agentName, setAgentName] = useState<string>("");
  const [messages, setMessages] = useState<DocumentMessage[]>([]);
  const [cards, setCards] = useState<DocumentSuggestionCard[]>([]);
  const [nextSteps, setNextSteps] = useState<DocumentNextStep[]>([]);
  const [copilotMeta, setCopilotMeta] = useState<DocumentCopilotMeta | null>(null);
  const [versions, setVersions] = useState<AgentDocumentVersion[]>([]);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [capabilities, setCapabilities] = useState<DocumentCapability[]>([]);
  const [capabilitiesLoading, setCapabilitiesLoading] = useState(false);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editBuffer, setEditBuffer] = useState("");
  const [liveTasks, setLiveTasks] = useState<DocumentTask[]>([]);
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    onError?.(null);
    try {
      if (agentKey) {
        const [doc, msgs, suggestions, vers] = await Promise.all([
          agentDocumentGetRequest(accessToken, dealId, agentKey),
          agentDocumentMessagesRequest(accessToken, dealId, agentKey),
          agentDocumentSuggestionsRequest(accessToken, dealId, agentKey),
          agentDocumentVersionsRequest(accessToken, dealId, agentKey),
        ]);
        setMarkdown(doc.document);
        setExists(doc.exists);
        setAgentName(doc.agent_name || suggestions.agent_name || agentKey);
        setMessages(msgs.data || []);
        setCards(suggestions.cards || []);
        setNextSteps(suggestions.next_steps || []);
        setCopilotMeta(suggestions.copilot || null);
        setVersions(vers.data || []);
      } else {
        const [doc, msgs, suggestions] = await Promise.all([
          documentGetRequest(accessToken, dealId),
          documentMessagesRequest(accessToken, dealId),
          documentSuggestionsRequest(accessToken, dealId),
        ]);
        setMarkdown(doc.document);
        setExists(doc.exists);
        setAgentName("");
        setMessages(msgs.data || []);
        setCards(suggestions.cards || []);
        setNextSteps(suggestions.next_steps || []);
        setCopilotMeta(suggestions.copilot || null);
        setVersions([]);
      }
      setEditing(false);
      // DiligenceIQ agent docs open on Edit; deal-level doc stays on Preview.
      setTab(agentKey ? "edit" : "preview");
    } catch (err) {
      onError?.(err instanceof ApiError ? err.message : "Failed to load document workspace");
    } finally {
      setLoading(false);
    }
  }, [accessToken, dealId, agentKey, onError]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending, liveTasks]);

  const loadCapabilities = useCallback(async () => {
    if (!accessToken) return;
    setCapabilitiesLoading(true);
    try {
      const rows = await cddCapabilitiesRequest(accessToken, dealId);
      setCapabilities(rows || []);
    } catch (err) {
      onError?.(err instanceof ApiError ? err.message : "Failed to load capability catalog");
    } finally {
      setCapabilitiesLoading(false);
    }
  }, [accessToken, dealId, onError]);

  useEffect(() => {
    if (!catalogOpen || capabilities.length || capabilitiesLoading) return;
    void loadCapabilities();
  }, [catalogOpen, capabilities.length, capabilitiesLoading, loadCapabilities]);

  const sourceLines = useMemo(() => parseSourceLines(markdown), [markdown]);
  const chainSteps = useMemo(() => buildChainFromMessages(messages), [messages]);
  const emptyChat = messages.length === 0 && liveTasks.length === 0;
  const lastAssistantId = useMemo(() => {
    for (let i = messages.length - 1; i >= 0; i -= 1) {
      if (messages[i].role === "assistant") return messages[i].id;
    }
    return null;
  }, [messages]);

  async function sendPrompt(content: string, capabilityIds?: string[]) {
    const text = content.trim();
    if (!text || !accessToken || sending) return;
    setCatalogOpen(false);
    setSending(true);
    onError?.(null);
    setLiveTasks([]);
    setStatusLine("Starting research…");
    const optimistic: DocumentMessage = {
      id: `local-${Date.now()}`,
      role: "user",
      content: text,
      ts: Date.now() / 1000,
    };
    setMessages((prev) => [...prev, optimistic]);
    setDraft("");

    const finalize = (
      user: DocumentMessage,
      assistant: DocumentMessage,
      document: { document: string; exists: boolean },
    ) => {
      setMessages((prev) => {
        const withoutOptimistic = prev.filter((m) => m.id !== optimistic.id);
        return [...withoutOptimistic, user, assistant];
      });
      setMarkdown(document.document);
      setExists(document.exists);
      setLiveTasks([]);
      setStatusLine(null);
      setTab("preview");
      const refreshSuggestions = agentKey
        ? agentDocumentSuggestionsRequest(accessToken, dealId, agentKey, user.content)
        : documentSuggestionsRequest(accessToken, dealId, user.content);
      void refreshSuggestions.then((suggestions) => {
        setNextSteps(suggestions.next_steps || []);
        setCopilotMeta(suggestions.copilot || null);
      });
      if (agentKey) {
        void agentDocumentVersionsRequest(accessToken, dealId, agentKey).then((vers) => {
          setVersions(vers.data || []);
        });
      }
    };

    try {
      if (agentKey) {
        await agentDocumentPostMessageStream(
          accessToken,
          dealId,
          agentKey,
          text,
          {
            onStatus: (message) => setStatusLine(message || "Working…"),
            onTask: (task) => {
              setLiveTasks((prev) => {
                const idx = prev.findIndex((t) => t.id === task.id);
                if (idx < 0) return [...prev, task];
                const next = [...prev];
                next[idx] = task;
                return next;
              });
            },
            onDone: ({ user, assistant, document }) => finalize(user, assistant, document),
            onError: (message) => {
              throw new ApiError(message, 500, null);
            },
          },
          capabilityIds,
        );
      } else {
        await documentPostMessageStream(
          accessToken,
          dealId,
          text,
          {
            onStatus: (message) => setStatusLine(message || "Working…"),
            onTask: (task) => {
              setLiveTasks((prev) => {
                const idx = prev.findIndex((t) => t.id === task.id);
                if (idx < 0) return [...prev, task];
                const next = [...prev];
                next[idx] = task;
                return next;
              });
            },
            onDone: ({ user, assistant, document }) => finalize(user, assistant, document),
            onError: (message) => {
              throw new ApiError(message, 500, null);
            },
          },
          capabilityIds,
        );
      }
    } catch (streamErr) {
      try {
        if (agentKey) {
          const res = await agentDocumentPostMessageRequest(
            accessToken,
            dealId,
            agentKey,
            text,
            capabilityIds,
          );
          finalize(res.data.user, res.data.assistant, res.data.document);
        } else {
          const res = await documentPostMessageRequest(accessToken, dealId, text, capabilityIds);
          finalize(res.data.user, res.data.assistant, res.data.document);
        }
      } catch (err) {
        setMessages((prev) => prev.filter((m) => m.id !== optimistic.id));
        setLiveTasks([]);
        setStatusLine(null);
        onError?.(
          err instanceof ApiError
            ? err.message
            : streamErr instanceof ApiError
              ? streamErr.message
              : "Failed to send message",
        );
      }
    } finally {
      setSending(false);
    }
  }

  async function saveDocument() {
    if (!accessToken) return;
    setSaving(true);
    onError?.(null);
    try {
      const res = agentKey
        ? await agentDocumentPutRequest(accessToken, dealId, agentKey, editBuffer)
        : await documentPutRequest(accessToken, dealId, editBuffer);
      setMarkdown(res.document);
      setExists(res.exists);
      setEditing(false);
      setTab("preview");
      if (agentKey) {
        const vers = await agentDocumentVersionsRequest(accessToken, dealId, agentKey);
        setVersions(vers.data || []);
      }
    } catch (err) {
      onError?.(err instanceof ApiError ? err.message : "Failed to save document");
    } finally {
      setSaving(false);
    }
  }

  async function restoreVersion(n: number) {
    if (!accessToken || !agentKey) return;
    onError?.(null);
    try {
      const res = await agentDocumentVersionGetRequest(accessToken, dealId, agentKey, n);
      setEditBuffer(res.document);
      setMarkdown(res.document);
      setTab("edit");
      setEditing(true);
    } catch (err) {
      onError?.(err instanceof ApiError ? err.message : "Failed to load version");
    }
  }

  async function exportMarkdown() {
    downloadBlob(
      `${dealName.replace(/\s+/g, "-").toLowerCase()}-cdd.md`,
      new Blob([markdown], { type: "text/markdown;charset=utf-8" }),
    );
  }

  async function exportBundle() {
    if (!accessToken) return;
    setExporting(true);
    onError?.(null);
    try {
      const bundle = await documentExportRequest(accessToken, dealId);
      downloadBlob(
        `${dealName.replace(/\s+/g, "-").toLowerCase()}-cdd-export.json`,
        new Blob([JSON.stringify(bundle, null, 2)], { type: "application/json" }),
      );
    } catch (err) {
      onError?.(err instanceof ApiError ? err.message : "Failed to export");
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="-mx-1 flex min-h-[calc(100vh-7rem)] overflow-hidden rounded-[12px] border border-border-primary bg-white md:-mx-2">
      <aside className="flex w-full max-w-[400px] shrink-0 flex-col border-r border-border-primary bg-[#fafbfc]">
        <header className="border-b border-border-primary px-4 py-3">
          <h2 className="text-[15px] font-semibold text-text-primary">Document copilot</h2>
          <p className="mt-0.5 text-[12px] text-text-secondary">
            {agentKey
              ? `Editing ${agentName || agentKey} — research · compute · write.`
              : "Research · compute · write · straight into the document."}
          </p>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          {loading ? (
            <p className="text-[13px] text-text-secondary">Loading workspace…</p>
          ) : emptyChat ? (
            <div>
              <h3 className="text-[16px] font-semibold text-text-primary">
                {agentKey ? `Edit this agent's document` : "Build this deal's document"}
              </h3>
              <p className="mt-1 text-[13px] text-text-secondary">
                {agentKey
                  ? "Ask the copilot to research, run the numbers, or rewrite a section. Every turn is saved as a new version."
                  : "Ask it to research the market or draft sections from the data room."}
              </p>
              <div className="mt-4 grid gap-2">
                {cards.map((card) => (
                  <button
                    key={card.title}
                    type="button"
                    disabled={sending}
                    onClick={() => void sendPrompt(card.prompt)}
                    className="rounded-[10px] border border-border-primary bg-white px-3 py-2.5 text-left transition hover:border-[#93c5fd] hover:bg-[#f8fbff]"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-[13px] font-medium text-text-primary">{card.title}</p>
                      <span className="rounded-full bg-[#eef0f3] px-2 py-0.5 text-[10px] font-medium uppercase text-[#4b5563]">
                        {kindBadge(card.kind)}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-[11px] text-text-secondary">{card.prompt}</p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg) => (
                <div key={msg.id} className={msg.role === "user" ? "ml-2" : ""}>
                  {msg.role === "user" ? (
                    <div className="rounded-[12px] bg-[#dbeafe] px-3 py-2.5 text-[13px] leading-relaxed text-[#1e3a5f]">
                      {msg.content}
                    </div>
                  ) : (
                    <AssistantTurn
                      message={msg}
                      fallbackNextSteps={nextSteps}
                      showNextSteps={!sending && msg.id === lastAssistantId}
                      sending={sending}
                      onNextStep={(prompt) => void sendPrompt(prompt)}
                    />
                  )}
                </div>
              ))}
              {sending ? (
                <div className="space-y-3">
                  {statusLine ? (
                    <p className="text-[12px] text-text-secondary">{statusLine}</p>
                  ) : null}
                  <PlanExecution tasks={liveTasks} defaultOpen />
                  <SourceCards taskSources={collectTaskSources(liveTasks)} />
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        <footer className="relative border-t border-border-primary p-3">
          <CapabilityCatalogPanel
            open={catalogOpen}
            capabilities={capabilities}
            dealName={dealName}
            loading={capabilitiesLoading}
            disabled={sending || !accessToken}
            onClose={() => setCatalogOpen(false)}
            onSelect={(cap, prompt) => void sendPrompt(prompt, [cap.id])}
          />
          <SmartCopilotChip
            meta={copilotMeta}
            open={catalogOpen}
            onClick={() => setCatalogOpen((prev) => !prev)}
          />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void sendPrompt(draft);
            }}
            className="flex gap-2"
          >
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={sending || !accessToken}
              placeholder="Tell the copilot what to research, compute, or write…"
              className="min-w-0 flex-1 rounded-lg border border-border-primary bg-white px-3 py-2 text-[13px] text-text-primary outline-none placeholder:text-text-secondary focus:border-[#93c5fd]"
            />
            <button
              type="submit"
              disabled={sending || !draft.trim() || !accessToken}
              className="rounded-lg bg-[#1d4ed8] px-3 py-2 text-[13px] font-medium text-white disabled:opacity-50"
            >
              {sending ? "…" : "Send"}
            </button>
          </form>
        </footer>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border-primary px-4 py-3">
          <div>
            <h2 className="text-[15px] font-semibold text-text-primary">
              {agentKey ? agentName || agentKey : `${dealName} — Commercial Due Diligence`}
            </h2>
            <p className="text-[11px] text-text-secondary">
              {agentKey
                ? `${exists ? "Agent document" : "Draft"} · ${versions.length ? `Version ${versions.length}` : "Unversioned"} · ${markdown.split(/\s+/).filter(Boolean).length} words approx`
                : exists
                  ? "Saved on deal"
                  : "Draft (not yet persisted)"}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              title="Download markdown"
              aria-label="Download markdown"
              onClick={() => void exportMarkdown()}
              className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-border-primary text-text-secondary hover:bg-[#f8fafc] hover:text-text-primary"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M12 3v12" />
                <path d="m7 10 5 5 5-5" />
                <path d="M5 19h14" />
              </svg>
            </button>
            <div className="flex rounded-lg border border-border-primary bg-[#f8fafc] p-0.5 text-[12px]">
              {(
                [
                  ["preview", "Preview"],
                  ["edit", "Edit"],
                  ["sources", `Sources${sourceLines.length ? ` (${sourceLines.length})` : ""}`],
                  ["chain", `Decision chain${chainSteps.length ? ` (${chainSteps.length})` : ""}`],
                  ...(agentKey
                    ? ([["versions", `Versions${versions.length ? ` (${versions.length})` : ""}`]] as [DocTab, string][])
                    : ([] as [DocTab, string][])),
                  ["settings", "Settings"],
                ] as [DocTab, string][]
              ).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => {
                    setTab(id);
                    if (id === "edit") {
                      setEditing(true);
                      setEditBuffer(markdown);
                    } else if (id === "preview") {
                      setEditing(false);
                    }
                  }}
                  className={`rounded-md px-2.5 py-1 ${
                    tab === id ? "bg-white font-medium text-text-primary shadow-sm" : "text-text-secondary"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            {tab === "edit" ? (
              <>
                <button
                  type="button"
                  onClick={() => {
                    setEditing(false);
                    setEditBuffer(markdown);
                    setTab("preview");
                  }}
                  className="rounded-lg border border-border-primary px-2.5 py-1.5 text-[12px] text-text-secondary"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={saving}
                  onClick={() => void saveDocument()}
                  className="rounded-lg bg-[#1d4ed8] px-2.5 py-1.5 text-[12px] font-medium text-white disabled:opacity-50"
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </>
            ) : null}
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          {loading ? (
            <p className="text-[13px] text-text-secondary">Loading document…</p>
          ) : tab === "edit" ? (
            <textarea
              value={editBuffer}
              onChange={(e) => setEditBuffer(e.target.value)}
              className="h-full min-h-[28rem] w-full resize-y rounded-lg border border-border-primary p-3 font-mono text-[12px] text-text-primary outline-none focus:border-[#93c5fd]"
            />
          ) : tab === "preview" ? (
            <MarkdownDoc text={markdown} />
          ) : tab === "sources" ? (
            <div>
              <h3 className="text-[15px] font-semibold text-text-primary">Sources</h3>
              <p className="mt-1 text-[12px] text-text-secondary">
                Citations maintained by the document copilot (data room + web).
              </p>
              {sourceLines.length === 0 ? (
                <p className="mt-4 text-[13px] text-text-secondary">No sources yet.</p>
              ) : (
                <ul className="mt-4 space-y-2">
                  {sourceLines.map((line) => (
                    <li
                      key={line}
                      className="rounded-lg border border-border-primary bg-[#fafbfc] px-3 py-2 text-[13px] text-text-primary"
                    >
                      {line.replace(/^\*\*/, "").replace(/\*\*/, "")}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : tab === "chain" ? (
            <div>
              <h3 className="text-[15px] font-semibold text-text-primary">Decision chain</h3>
              <p className="mt-1 text-[12px] text-text-secondary">
                Chronological research turns that shaped this document.
              </p>
              {chainSteps.length === 0 ? (
                <p className="mt-4 text-[13px] text-text-secondary">No research turns yet.</p>
              ) : (
                <ol className="mt-4 space-y-3">
                  {chainSteps.map((step, idx) => (
                    <li
                      key={step.id}
                      className="rounded-lg border border-border-primary bg-[#fafbfc] px-4 py-3"
                    >
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
                        Step {idx + 1}
                      </p>
                      <p className="mt-1 text-[13px] font-medium text-text-primary">{step.prompt}</p>
                      <p className="mt-1 text-[12px] text-text-secondary line-clamp-3">{step.answer}</p>
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {step.tasks.map((t) => (
                          <span
                            key={t.id || t.title}
                            className="rounded-full bg-white px-2 py-0.5 text-[10px] text-text-secondary ring-1 ring-border-primary"
                          >
                            {t.label || t.tool}: {t.title}
                          </span>
                        ))}
                        {typeof step.source_count === "number" ? (
                          <span className="rounded-full bg-white px-2 py-0.5 text-[10px] text-text-secondary ring-1 ring-border-primary">
                            {step.source_count} sources
                          </span>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          ) : tab === "versions" ? (
            <div>
              <h3 className="text-[15px] font-semibold text-text-primary">Versions</h3>
              <p className="mt-1 text-[12px] text-text-secondary">
                Snapshots from agent runs, saves, and copilot turns.
              </p>
              {versions.length === 0 ? (
                <p className="mt-4 text-[13px] text-text-secondary">No versions yet.</p>
              ) : (
                <ul className="mt-4 space-y-2">
                  {[...versions].reverse().map((v) => (
                    <li
                      key={v.n}
                      className="flex items-center justify-between gap-3 rounded-lg border border-border-primary bg-[#fafbfc] px-3 py-2"
                    >
                      <div>
                        <p className="text-[13px] font-medium text-text-primary">Version {v.n}</p>
                        <p className="text-[11px] text-text-secondary">
                          {v.source || "snapshot"}
                          {v.word_count != null ? ` · ${v.word_count} words` : ""}
                          {v.citation_count != null ? ` · ${v.citation_count} citations` : ""}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => void restoreVersion(v.n)}
                        className="rounded-md border border-border-primary bg-white px-2.5 py-1 text-[12px] font-medium text-text-primary"
                      >
                        Open
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : (
            <div>
              <h3 className="text-[15px] font-semibold text-text-primary">Settings & export</h3>
              <p className="mt-2 text-[13px] text-text-secondary">
                Document content is stored under this deal&apos;s library on the API. Export the live
                markdown or a JSON bundle (document + messages + decision chain).
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void exportMarkdown()}
                  className="rounded-lg border border-border-primary bg-white px-3 py-2 text-[13px] font-medium text-text-primary hover:bg-[#f8fafc]"
                >
                  Download markdown
                </button>
                <button
                  type="button"
                  disabled={exporting || !accessToken}
                  onClick={() => void exportBundle()}
                  className="rounded-lg bg-[#1d4ed8] px-3 py-2 text-[13px] font-medium text-white disabled:opacity-50"
                >
                  {exporting ? "Exporting…" : "Download JSON bundle"}
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
