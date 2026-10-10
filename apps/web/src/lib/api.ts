"use client";

import { API_BASE_URL, ENDPOINTS } from "./config";
import type { ApiSuccess, AuthPayload } from "./auth-types";
import type { Deal, PortfolioMetrics, SectorOption, UsageStats } from "./deal-types";
import type { EvidenceAnalyzePayload } from "./evidence-types";

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(message: string, status: number, body: unknown) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function messageFromBody(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const b = body as Record<string, unknown>;
  if (typeof b.message === "string") return b.message;
  if (typeof b.detail === "string") return b.detail;
  // FastAPI 422 validation errors: { detail: [{ loc, msg, type }, ...] }
  if (Array.isArray(b.detail) && b.detail.length > 0) {
    const parts = b.detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        const d = item as Record<string, unknown>;
        return typeof d.msg === "string" ? d.msg : null;
      })
      .filter((m): m is string => Boolean(m));
    if (parts.length) return parts.join("; ");
  }
  if (b.detail && typeof b.detail === "object") {
    const d = b.detail as Record<string, unknown>;
    if (typeof d.message === "string" && d.message.trim()) return d.message;
    if (typeof d.error === "string" && d.error.trim()) return d.error;
  }
  return fallback;
}

export async function apiRequest<T>(
  path: string,
  options: RequestInit & { accessToken?: string } = {},
): Promise<T> {
  const { accessToken, headers, ...rest } = options;
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(messageFromBody(body, res.statusText), res.status, body);
  }
  return body as T;
}

export async function loginRequest(email: string, password: string) {
  return apiRequest<ApiSuccess<AuthPayload>>(ENDPOINTS.AUTH.LOGIN, {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function registerRequest(input: {
  email: string;
  password: string;
  firstName?: string;
  lastName?: string;
  organizationName?: string;
}) {
  return apiRequest<ApiSuccess<AuthPayload>>(ENDPOINTS.AUTH.REGISTER, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function meRequest(accessToken: string) {
  return apiRequest<ApiSuccess<AuthPayload>>(ENDPOINTS.AUTH.ME, {
    method: "GET",
    accessToken,
  });
}

export async function logoutRequest(accessToken: string, refreshToken?: string) {
  return apiRequest<ApiSuccess<{ ok: boolean }>>(ENDPOINTS.AUTH.LOGOUT, {
    method: "POST",
    accessToken,
    body: JSON.stringify({ refreshToken }),
  });
}

export async function listDealsRequest(accessToken: string) {
  return apiRequest<ApiSuccess<Deal[]> & { metrics: PortfolioMetrics }>(ENDPOINTS.DEALS, {
    method: "GET",
    accessToken,
  });
}

export async function createDealRequest(
  accessToken: string,
  input: {
    name: string;
    slug?: string;
    description?: string;
    tags?: string;
    industry?: string;
  },
) {
  return apiRequest<ApiSuccess<Deal>>(ENDPOINTS.DEALS, {
    method: "POST",
    accessToken,
    body: JSON.stringify(input),
  });
}

export async function usageRequest(accessToken: string) {
  return apiRequest<ApiSuccess<UsageStats>>(ENDPOINTS.USAGE, {
    method: "GET",
    accessToken,
  });
}

export async function sectorsRequest(accessToken: string) {
  return apiRequest<SectorOption[]>(ENDPOINTS.SECTORS, {
    method: "GET",
    accessToken,
  });
}

export type DashboardPayload = {
  dealRoom: {
    id: string;
    uuid: string;
    name: string;
    status: string;
    slug?: string;
    sector?: string;
  };
  deal: Deal;
  workflowCompletion: {
    totalAgents: number;
    completedAgents: number;
    completionPercentage: number;
  };
  dataRoomStatus: {
    processedDocuments: number;
    totalDocuments: number;
    totalSizeBytes: number;
  };
  workflowRoadmap: Array<{
    phaseName: string;
    phaseUuid: string;
    order: number;
    totalAgents: number;
    completedAgents: number;
    status: string;
    stages: Array<{
      stageTitle: string;
      stageKey: string;
      description?: string;
      agents: Array<{
        agentName: string;
        agent_key: string;
        status: string;
        description?: string;
      }>;
    }>;
  }>;
  reportStatus: { hasReports: boolean; generatedReports: unknown[] };
};

export async function dealDashboardRequest(accessToken: string, dealId: string) {
  return apiRequest<{ success: boolean; data: DashboardPayload }>(
    ENDPOINTS.dealDashboard(dealId),
    { method: "GET", accessToken },
  );
}

export async function vdrListRequest(accessToken: string, dealId: string) {
  return apiRequest<{
    vdr: string[];
    data: VdrDoc[];
    ingestion?: IngestionStatus;
  }>(ENDPOINTS.cddVdr(dealId), { method: "GET", accessToken });
}

export type VdrDoc = {
  name: string;
  filename: string;
  size?: number;
  format?: string;
  status?: string;
  category?: string;
  integrity?: string;
  uploaded_at?: string | null;
  classified_at?: string | null;
  routed_agents?: string[];
};

export type IngestionStatus = {
  running: boolean;
  completed: boolean;
  processed_chunks: number;
  document_count?: number;
  ready_count?: number;
};

export async function vdrAnalyzeRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<{ queued: boolean; document_count: number }>>(
    ENDPOINTS.cddAnalyze(dealId),
    { method: "POST", accessToken },
  );
}

export async function vdrEvidenceAnalyzeRequest(accessToken: string, dealId: string) {
  return apiRequest<EvidenceAnalyzePayload>(ENDPOINTS.cddVdrAnalyze(dealId), {
    method: "POST",
    accessToken,
  });
}

export async function vdrEvidenceGraphRequest(accessToken: string, dealId: string) {
  return apiRequest<EvidenceAnalyzePayload>(ENDPOINTS.cddVdrGraph(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function vdrIngestionRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<IngestionStatus>>(ENDPOINTS.cddIngestion(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function vdrUploadRequest(
  accessToken: string,
  dealId: string,
  file: File,
) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.cddVdrUpload(dealId)}`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: form,
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(
      (body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : res.statusText) || "Upload failed",
      res.status,
      body,
    );
  }
  return body as ApiSuccess<{ deal: Deal; vdr: Array<{ name: string; filename: string; size?: number }> }>;
}

export async function vdrDownloadRequest(
  accessToken: string,
  dealId: string,
  filename: string,
) {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.cddVdrDownload(dealId, filename)}`, {
    method: "GET",
    headers: {
      Accept: "application/octet-stream",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(messageFromBody(body, res.statusText), res.status, body);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function vdrDeleteRequest(
  accessToken: string,
  dealId: string,
  filename: string,
) {
  return apiRequest<ApiSuccess<{ deal: Deal; vdr: Array<{ name: string; filename: string; size?: number }> }>>(
    ENDPOINTS.cddVdrDelete(dealId, filename),
    { method: "DELETE", accessToken },
  );
}

export async function vdrSyncRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<{ ok: boolean; vdr_files: number }>>(
    ENDPOINTS.cddSync(dealId),
    { method: "POST", accessToken },
  );
}

export type DatabookReleaseSummary = {
  release_id: string;
  version: number;
  created_at: string;
  source?: string;
  note?: string | null;
  counts?: {
    proven?: number;
    doubtful?: number;
    missing?: number;
    requests?: number;
  };
  request_count?: number;
  coverage?: {
    keys?: string[];
    years?: number[];
    source?: string;
  } | null;
  missing_required_docs?: string[];
};

export type DatabookSummary = {
  deal_id: string;
  meta: {
    version: number;
    last_rescan_at?: string | null;
    last_deep_at?: string | null;
    row_count: number;
    promoted_count: number;
    held_out_count: number;
    issue_count: number;
    current_release_id?: string | null;
    current_release_version?: number | null;
    last_release_at?: string | null;
    release_stale?: boolean;
    mapping_memory_count?: number;
    trap_count?: number;
    last_validation_pack_at?: string | null;
  };
  flags: Record<string, number>;
  promoted_preview: Array<Record<string, unknown>>;
  release?: DatabookReleaseSummary | null;
  freshness?: {
    up_to_date: boolean;
    label: string;
    stale_reason?: string | null;
    library_generated_at?: string | null;
    last_rescan_at?: string | null;
    last_deep_at?: string | null;
    action?: "none" | "rescan";
  };
  validation_pack?: {
    ready_for_review: boolean;
    release_id?: string | null;
    release_version?: number | null;
    counts?: Record<string, number>;
    generated_at?: string;
  } | null;
};

export type DatabookRow = {
  row_id: string;
  caption: string;
  metric_key?: string | null;
  fiscal_year?: number | null;
  value: number;
  status: string;
  source_name: string;
  assumption?: boolean;
};

export type DatabookFinding = {
  source_name: string;
  doc_id: string;
  row_count: number;
  held_out: number;
  promoted: number;
  dropped: number;
  vouched?: number;
  conflicts: number;
  assumptions?: number;
  unmapped?: number;
  checks_passed?: number | null;
  checks_failed?: number | null;
  checks_total?: number;
  no_table?: boolean;
  flags?: string[];
  triage?: string | null;
  note?: string;
  relevance?: string | null;
  role?: string | null;
  basis?: string | null;
  ladder_score?: number | null;
  actual_forecast?: string | null;
  set_aside_reason?: string | null;
};

export type DataQualityCandidate = {
  value: number;
  sources: string[];
  captions: string[];
  chosen: boolean;
  stated_by: number;
  source_facts?: number;
  source_total_facts?: number;
  row_ids?: string[];
};

export type DataQualityItem =
  | {
      kind: "conflict";
      metric: string;
      fiscal_year?: number | null;
      chosen?: number | null;
      candidates: DataQualityCandidate[];
      scope: string;
      rule: string;
    }
  | {
      kind: "dropped";
      source: string;
      reason: string;
      detail?: { metric?: string; fiscal_year?: number; value?: number };
    }
  | {
      kind: "failed_check";
      source?: string;
      block_id?: string;
      fiscal_year?: number | null;
      period?: string | null;
      printed_subtotal?: number | null;
      computed_sum?: number | null;
      row_ids?: string[];
      reason?: string;
    }
  | {
      kind: "assumed";
      metric: string;
      fiscal_year?: number | null;
      value?: number;
      source?: string;
      caption?: string;
      row_id?: string;
      unit?: string | null;
      currency?: string | null;
      scale?: string | null;
      reason: string;
    };

export type DataQualityPayload = {
  items: DataQualityItem[];
  summary: {
    total: number;
    by_kind: Record<string, number>;
    needs_review: number;
  };
};

export async function databookSummaryRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<DatabookSummary>>(ENDPOINTS.cddDatabook(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function databookRescanRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<DatabookSummary>>(ENDPOINTS.cddDatabookRescan(dealId), {
    method: "POST",
    accessToken,
  });
}

export async function databookReleaseRequest(
  accessToken: string,
  dealId: string,
  note?: string,
) {
  return apiRequest<
    ApiSuccess<{ release: Record<string, unknown>; summary: DatabookSummary }>
  >(ENDPOINTS.cddDatabookRelease(dealId), {
    method: "POST",
    accessToken,
    body: JSON.stringify(note?.trim() ? { note: note.trim() } : {}),
  });
}

export async function databookDeepRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<DatabookSummary>>(ENDPOINTS.cddDatabookDeep(dealId), {
    method: "POST",
    accessToken,
  });
}

export async function databookRowsRequest(
  accessToken: string,
  dealId: string,
  opts?: { material?: boolean; minAbs?: number; status?: string; metric?: string },
) {
  const params = new URLSearchParams();
  if (opts?.material) params.set("material", "true");
  if (opts?.minAbs != null) params.set("min_abs", String(opts.minAbs));
  if (opts?.status) params.set("status", opts.status);
  if (opts?.metric) params.set("metric", opts.metric);
  const q = params.toString();
  return apiRequest<ApiSuccess<{ items: DatabookRow[]; total: number }>>(
    `${ENDPOINTS.cddDatabookRows(dealId)}${q ? `?${q}` : ""}`,
    { method: "GET", accessToken },
  );
}

export async function databookFindingsRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<{ items: DatabookFinding[]; total: number }>>(
    ENDPOINTS.cddDatabookFindings(dealId),
    { method: "GET", accessToken },
  );
}

export async function databookExportPromotedCsv(
  accessToken: string,
  dealId: string,
  opts?: { material?: boolean },
) {
  const params = new URLSearchParams();
  if (opts?.material) params.set("material", "true");
  const q = params.toString();
  const res = await fetch(
    `${API_BASE_URL}${ENDPOINTS.cddDatabookPromotedCsv(dealId)}${q ? `?${q}` : ""}`,
    {
      method: "GET",
      headers: {
        Accept: "text/csv",
        Authorization: `Bearer ${accessToken}`,
      },
    },
  );
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(messageFromBody(body, res.statusText), res.status, body);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `promoted-${dealId}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function databookExportExcelRequest(accessToken: string, dealId: string) {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.cddDatabookExportXlsx(dealId)}`, {
    method: "GET",
    headers: {
      Accept: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(messageFromBody(body, res.statusText), res.status, body);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `databook-${dealId}.xlsx`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function databookImportExcelRequest(
  accessToken: string,
  dealId: string,
  file: File,
  reason?: string,
) {
  const params = new URLSearchParams();
  if (reason?.trim()) params.set("reason", reason.trim());
  const q = params.toString();
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(
    `${API_BASE_URL}${ENDPOINTS.cddDatabookImportXlsx(dealId)}${q ? `?${q}` : ""}`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      body: form,
    },
  );
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(messageFromBody(body, res.statusText), res.status, body);
  }
  return body as ApiSuccess<{
    applied: number;
    skipped: number;
    errors: number;
    reason: string;
    summary: DatabookSummary;
  }>;
}

export async function dataQualityRequest(accessToken: string, dealId: string) {
  return apiRequest<DataQualityPayload>(ENDPOINTS.cddDataQuality(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function databookCorrectRequest(
  accessToken: string,
  dealId: string,
  rowId: string,
  body: {
    reason: string;
    value?: number;
    metric_key?: string;
    unit?: string;
    currency?: string;
    scale?: string;
    caption?: string;
  },
) {
  return apiRequest<ApiSuccess<Record<string, unknown>>>(ENDPOINTS.cddDatabookCorrect(dealId, rowId), {
    method: "POST",
    accessToken,
    body: JSON.stringify(body),
  });
}

export async function databookDropRequest(
  accessToken: string,
  dealId: string,
  rowId: string,
  reason: string,
) {
  return apiRequest<ApiSuccess<Record<string, unknown>>>(ENDPOINTS.cddDatabookDrop(dealId, rowId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({ reason }),
  });
}

export async function databookVouchRequest(
  accessToken: string,
  dealId: string,
  rowId: string,
  reason: string,
) {
  return apiRequest<ApiSuccess<Record<string, unknown>>>(ENDPOINTS.cddDatabookVouch(dealId, rowId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({ reason }),
  });
}

export async function databookConfirmRequest(
  accessToken: string,
  dealId: string,
  rowId: string,
  reason: string,
) {
  return apiRequest<ApiSuccess<Record<string, unknown>>>(ENDPOINTS.cddDatabookConfirm(dealId, rowId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({ reason }),
  });
}

export async function databookExcludeRequest(
  accessToken: string,
  dealId: string,
  rowId: string,
  reason: string,
) {
  return apiRequest<ApiSuccess<Record<string, unknown>>>(ENDPOINTS.cddDatabookExclude(dealId, rowId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({ reason }),
  });
}

export async function databookRemapRequest(
  accessToken: string,
  dealId: string,
  rowId: string,
  body: { reason: string; metric_key: string; value?: number },
) {
  return apiRequest<ApiSuccess<Record<string, unknown>>>(ENDPOINTS.cddDatabookRemap(dealId, rowId), {
    method: "POST",
    accessToken,
    body: JSON.stringify(body),
  });
}

export type ValidationCard = {
  card_id: string;
  kind: "doubtful" | "conflict" | "missing" | "calibration";
  metric_key: string;
  fiscal_year: number;
  status: string;
  value?: number | null;
  unit?: string | null;
  currency?: string | null;
  scale?: string | null;
  row_id?: string | null;
  sources?: string[];
  captions?: string[];
  reason?: string | null;
  alternatives?: Array<Record<string, unknown>>;
  scope?: string | null;
  statement?: string | null;
  period_end?: string | null;
  period_length?: string | null;
  source_basis?: string | null;
  proof_level?: string | null;
  proof_checks?: string[];
  dependents?: string[];
  release_id?: string | null;
  release_version?: number | null;
  source_ref?: {
    doc?: string | null;
    page?: number | null;
    table?: string | null;
    row?: number | null;
    col?: number | null;
    rule?: string | null;
    bbox?: number[] | null;
    crop_ref?: string | null;
    crop_status?: "available" | "unavailable" | "pending" | null;
    crop_reason?: string | null;
  } | null;
  crop_ref?: string | null;
  crop_status?: "available" | "unavailable" | "pending";
  crop_reason?: string | null;
  request_id?: string | null;
  document_request?: {
    request_id: string;
    doc_kind: string;
    label: string;
    reason: string;
    metric_keys?: string[];
    fiscal_years?: number[];
    priority?: string;
    status?: string;
  } | null;
};

export type ValidationPack = {
  deal_slug: string;
  release_id?: string | null;
  release_version?: number | null;
  generated_at: string;
  cards: ValidationCard[];
  counts: Record<string, number>;
  ready_for_review: boolean;
};

export async function databookValidationPackRequest(
  accessToken: string,
  dealId: string,
  calibration = 5,
) {
  const qs = new URLSearchParams({ calibration: String(calibration) });
  return apiRequest<ApiSuccess<ValidationPack>>(
    `${ENDPOINTS.cddDatabookValidationPack(dealId)}?${qs.toString()}`,
    { method: "GET", accessToken },
  );
}

/** Fetch a rendered page crop as an object URL (caller must revoke). */
export async function databookCropObjectUrl(
  accessToken: string,
  dealId: string,
  cropRef: string,
): Promise<string> {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.cddDatabookCrop(dealId, cropRef)}`, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!res.ok) {
    throw new Error(`Crop fetch failed (${res.status})`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export async function databookAcceptConflictRequest(
  accessToken: string,
  dealId: string,
  body: {
    reason: string;
    metric_key: string;
    fiscal_year: number;
    value: number;
    row_id?: string;
  },
) {
  return apiRequest<ApiSuccess<Record<string, unknown>>>(ENDPOINTS.cddDatabookAccept(dealId), {
    method: "POST",
    accessToken,
    body: JSON.stringify(body),
  });
}

export async function databookRereadRequest(
  accessToken: string,
  dealId: string,
  filename: string,
) {
  return apiRequest<ApiSuccess<DatabookSummary>>(ENDPOINTS.cddDatabookReread(dealId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({ filename }),
  });
}

export type PipelineAgent = {
  agentName: string;
  agent_key: string;
  status: string;
  description?: string;
  category?: string;
  stageTitle?: string;
  src?: string;
};

export type PipelinePhase = {
  phaseName: string;
  phaseUuid: string;
  phase_id: string;
  order: number;
  totalAgents: number;
  completedAgents: number;
  status: string;
  stages: Array<{
    stageTitle: string;
    stageKey: string;
    description?: string;
    agents: PipelineAgent[];
  }>;
  agents: PipelineAgent[];
};

export type PipelinePayload = {
  deal_id: string;
  running: boolean;
  totalAgents: number;
  completedAgents: number;
  completionPercentage: number;
  next_phase_id: string | null;
  next_phase_name: string | null;
  running_agent_key?: string | null;
  running_agent_name?: string | null;
  phases: PipelinePhase[];
};

export async function pipelineRequest(accessToken: string, dealId: string) {
  return apiRequest<ApiSuccess<PipelinePayload>>(ENDPOINTS.pipeline(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function pipelineRunRequest(
  accessToken: string,
  dealId: string,
  body: { phase_id?: string; agent_key?: string; restart?: boolean } = {},
) {
  return apiRequest<ApiSuccess<{ queued: boolean; phase_id?: string; agent_keys: string[]; restart?: boolean }>>(
    ENDPOINTS.pipelineRun(dealId),
    { method: "POST", accessToken, body: JSON.stringify(body) },
  );
}

export type PipelinePhaseStreamHandlers = {
  onEvent?: (event: Record<string, unknown>) => void;
  onLog?: (message: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

/** SSE phase run (DiligenceIQ-shaped). Prefer for Deep Dive. */
export async function pipelinePhaseRunStream(
  accessToken: string,
  dealId: string,
  phaseId: string,
  handlers: PipelinePhaseStreamHandlers = {},
) {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.pipelinePhaseRun(dealId, phaseId)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: "{}",
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      detail = messageFromBody(body, detail);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status, null);
  }
  if (!res.body) {
    throw new ApiError("Empty stream response", res.status, null);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const dispatchBlock = (block: string) => {
    const lines = block.split("\n");
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    } catch {
      return;
    }
    const type = String(payload.type || eventName);
    handlers.onEvent?.({ ...payload, type });
    if (type === "log") {
      handlers.onLog?.(String(payload.message || ""));
    } else if (type === "error") {
      const message = String(payload.message || payload.error || "Phase run failed");
      handlers.onError?.(message);
      throw new ApiError(message, Number(payload.status_code) || 500, null);
    } else if (type === "done" || type === "pipeline_completed") {
      finished = true;
      handlers.onDone?.();
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) dispatchBlock(part);
    }
  }
  if (buffer.trim()) dispatchBlock(buffer);
  if (!finished) handlers.onDone?.();
}

export async function pipelineAgentOutputRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
) {
  return apiRequest<
    ApiSuccess<{
      agent_key: string;
      status: string;
      output: Record<string, unknown>;
      file_output?: Record<string, unknown> | null;
      agentName?: string;
    }>
  >(ENDPOINTS.pipelineAgentOutput(dealId, agentKey), { method: "GET", accessToken });
}

export type DocumentSuggestionCard = {
  title: string;
  kind: "internal" | "web" | "algo" | string;
  prompt: string;
};

export type DocumentNextStep = {
  title: string;
  icon?: string;
  prompt: string;
};

export type DocumentCopilotMeta = {
  mode_label: string;
  model?: string | null;
  capability_count: number;
  synthesis_enabled: boolean;
};

export type DocumentCapability = {
  id: string;
  kind: string;
  section: string;
  exhibit?: string;
  description: string;
  src: string;
  title: string;
  blurb?: string;
  method?: string;
};

export type DocumentTaskSource = {
  origin?: string;
  title: string;
  snippet?: string;
  url?: string;
  domain?: string;
  chunk_ids?: string[];
  section_label?: string | null;
  chunk_index?: number | null;
};

export type DocumentChartSpec = {
  type?: string;
  title?: string;
  series?: Array<{ label: string; value: number }>;
  placeholder?: boolean;
  unit?: string;
};

export type DocumentTask = {
  id: string;
  tool?: string;
  title: string;
  label: string;
  status: string;
  summary?: string;
  detail?: {
    sources?: DocumentTaskSource[];
    evidence?: string;
    capability_id?: string;
    queries?: string[];
    exhibit?: string;
    chart?: DocumentChartSpec;
  };
  ms?: number;
};

export type DocumentMessageSource = {
  id: number;
  type: string;
  title: string;
  url?: string | null;
  domain?: string | null;
  snippet?: string | null;
  used?: boolean;
  chunk_ids?: string[];
  section_label?: string | null;
  chunk_index?: number | null;
};

export type DocumentMessage = {
  id: string;
  role: "user" | "assistant" | string;
  content: string;
  ts?: number;
  tasks?: DocumentTask[];
  sources?: DocumentMessageSource[];
  next_steps?: DocumentNextStep[];
};

export type DealDocumentPayload = {
  document: string;
  exists: boolean;
  agent_key?: string;
  agent_name?: string;
  seeded_from_output?: boolean;
};

export type AgentDocumentVersion = {
  n: number;
  filename?: string;
  ts?: number;
  word_count?: number;
  citation_count?: number;
  source?: string;
};

export type DocumentDecisionStep = {
  id: string;
  ts?: number;
  prompt: string;
  answer: string;
  tasks: Array<{
    id?: string;
    title?: string;
    label?: string;
    tool?: string;
    status?: string;
    capability_id?: string;
    ms?: number;
  }>;
  source_count?: number;
};

export type DocumentExportBundle = {
  deal_id: string;
  deal_name: string;
  company?: string | null;
  document: string;
  exists: boolean;
  messages: DocumentMessage[];
  decision_chain: { steps: DocumentDecisionStep[]; count: number };
  exported_at: number;
};

export async function documentGetRequest(accessToken: string, dealId: string) {
  return apiRequest<DealDocumentPayload>(ENDPOINTS.documents(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function documentPutRequest(
  accessToken: string,
  dealId: string,
  document: string,
) {
  return apiRequest<DealDocumentPayload>(ENDPOINTS.documents(dealId), {
    method: "PUT",
    accessToken,
    body: JSON.stringify({ document }),
  });
}

export async function documentMessagesRequest(accessToken: string, dealId: string) {
  return apiRequest<{ success: boolean; data: DocumentMessage[] }>(
    ENDPOINTS.documentMessages(dealId),
    { method: "GET", accessToken },
  );
}

export async function documentPostMessageRequest(
  accessToken: string,
  dealId: string,
  content: string,
  capabilityIds?: string[],
) {
  return apiRequest<{
    success: boolean;
    data: {
      user: DocumentMessage;
      assistant: DocumentMessage;
      document: DealDocumentPayload;
    };
  }>(ENDPOINTS.documentMessages(dealId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({
      content,
      ...(capabilityIds?.length ? { capability_ids: capabilityIds } : {}),
    }),
  });
}

export type DocumentStreamHandlers = {
  onStatus?: (message: string) => void;
  onTask?: (task: DocumentTask) => void;
  onDone?: (payload: {
    user: DocumentMessage;
    assistant: DocumentMessage;
    document: DealDocumentPayload;
  }) => void;
  onError?: (message: string) => void;
};

export async function documentPostMessageStream(
  accessToken: string,
  dealId: string,
  content: string,
  handlers: DocumentStreamHandlers,
  capabilityIds?: string[],
) {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.documentMessagesStream(dealId)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
    },
    body: JSON.stringify({
      content,
      ...(capabilityIds?.length ? { capability_ids: capabilityIds } : {}),
    }),
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status, null);
  }
  if (!res.body) {
    throw new ApiError("Empty stream response", res.status, null);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const dispatchBlock = (block: string) => {
    const lines = block.split("\n");
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    } catch {
      return;
    }
    const type = String(payload.type || eventName);
    if (type === "status") {
      handlers.onStatus?.(String(payload.message || ""));
    } else if (type === "task" && payload.task) {
      handlers.onTask?.(payload.task as DocumentTask);
    } else if (type === "done") {
      finished = true;
      handlers.onDone?.({
        user: payload.user as DocumentMessage,
        assistant: payload.assistant as DocumentMessage,
        document: payload.document as DealDocumentPayload,
      });
    } else if (type === "error") {
      handlers.onError?.(String(payload.message || "Research failed"));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) dispatchBlock(part);
    }
  }
  if (buffer.trim()) dispatchBlock(buffer);
  if (!finished) {
    throw new ApiError("Stream ended before completion", 502, null);
  }
}

export async function cddCapabilitiesRequest(accessToken: string, dealId: string) {
  return apiRequest<DocumentCapability[]>(ENDPOINTS.cddCapabilities(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function documentSuggestionsRequest(
  accessToken: string,
  dealId: string,
  afterPrompt?: string,
) {
  const qs = afterPrompt?.trim()
    ? `?after_prompt=${encodeURIComponent(afterPrompt.trim())}`
    : "";
  return apiRequest<{
    cards: DocumentSuggestionCard[];
    next_steps?: DocumentNextStep[];
    copilot?: DocumentCopilotMeta;
  }>(`${ENDPOINTS.documentSuggestions(dealId)}${qs}`, { method: "GET", accessToken });
}

export async function documentDecisionChainRequest(accessToken: string, dealId: string) {
  return apiRequest<{ steps: DocumentDecisionStep[]; count: number }>(
    ENDPOINTS.documentDecisionChain(dealId),
    { method: "GET", accessToken },
  );
}

export async function documentExportRequest(accessToken: string, dealId: string) {
  return apiRequest<DocumentExportBundle>(ENDPOINTS.documentExport(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function agentDocumentGetRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
  refresh = false,
) {
  const qs = refresh ? "?refresh=true" : "";
  return apiRequest<DealDocumentPayload>(
    `${ENDPOINTS.agentDocuments(dealId, agentKey)}${qs}`,
    { method: "GET", accessToken },
  );
}

export async function agentDocumentPutRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
  document: string,
) {
  return apiRequest<DealDocumentPayload>(ENDPOINTS.agentDocuments(dealId, agentKey), {
    method: "PUT",
    accessToken,
    body: JSON.stringify({ document }),
  });
}

export async function agentDocumentMessagesRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
) {
  return apiRequest<{ success: boolean; data: DocumentMessage[] }>(
    ENDPOINTS.agentDocumentMessages(dealId, agentKey),
    { method: "GET", accessToken },
  );
}

export async function agentDocumentPostMessageRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
  content: string,
  capabilityIds?: string[],
) {
  return apiRequest<{
    success: boolean;
    data: {
      user: DocumentMessage;
      assistant: DocumentMessage;
      document: DealDocumentPayload;
    };
  }>(ENDPOINTS.agentDocumentMessages(dealId, agentKey), {
    method: "POST",
    accessToken,
    body: JSON.stringify({
      content,
      ...(capabilityIds?.length ? { capability_ids: capabilityIds } : {}),
    }),
  });
}

export async function agentDocumentPostMessageStream(
  accessToken: string,
  dealId: string,
  agentKey: string,
  content: string,
  handlers: DocumentStreamHandlers,
  capabilityIds?: string[],
) {
  const res = await fetch(
    `${API_BASE_URL}${ENDPOINTS.agentDocumentMessagesStream(dealId, agentKey)}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        content,
        ...(capabilityIds?.length ? { capability_ids: capabilityIds } : {}),
      }),
    },
  );
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status, null);
  }
  if (!res.body) throw new ApiError("Empty stream response", res.status, null);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const dispatchBlock = (block: string) => {
    const lines = block.split("\n");
    let eventName = "message";
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    } catch {
      return;
    }
    const type = String(payload.type || eventName);
    if (type === "status") handlers.onStatus?.(String(payload.message || ""));
    else if (type === "task" && payload.task) handlers.onTask?.(payload.task as DocumentTask);
    else if (type === "done") {
      finished = true;
      handlers.onDone?.({
        user: payload.user as DocumentMessage,
        assistant: payload.assistant as DocumentMessage,
        document: payload.document as DealDocumentPayload,
      });
    } else if (type === "error") {
      handlers.onError?.(String(payload.message || "Research failed"));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) dispatchBlock(part);
    }
  }
  if (buffer.trim()) dispatchBlock(buffer);
  if (!finished) throw new ApiError("Stream ended before completion", 502, null);
}

export async function agentDocumentSuggestionsRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
  afterPrompt?: string,
) {
  const qs = afterPrompt?.trim()
    ? `?after_prompt=${encodeURIComponent(afterPrompt.trim())}`
    : "";
  return apiRequest<{
    cards: DocumentSuggestionCard[];
    next_steps?: DocumentNextStep[];
    copilot?: DocumentCopilotMeta;
    agent_name?: string;
  }>(`${ENDPOINTS.agentDocumentSuggestions(dealId, agentKey)}${qs}`, {
    method: "GET",
    accessToken,
  });
}

export async function agentDocumentVersionsRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
) {
  return apiRequest<{ success: boolean; data: AgentDocumentVersion[]; count: number }>(
    ENDPOINTS.agentDocumentVersions(dealId, agentKey),
    { method: "GET", accessToken },
  );
}

export async function agentDocumentVersionGetRequest(
  accessToken: string,
  dealId: string,
  agentKey: string,
  versionN: number,
) {
  return apiRequest<{ n: number; document: string; meta: AgentDocumentVersion }>(
    ENDPOINTS.agentDocumentVersion(dealId, agentKey, versionN),
    { method: "GET", accessToken },
  );
}

export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i += 1;
  }
  return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

// ---------------------------------------------------------------------------
// Reports
// ---------------------------------------------------------------------------

export type ReportCatalogEntry = {
  report_type: string;
  label: string;
  format: string;
  export: string;
  description: string;
  status: "not_generated" | "running" | "ready" | "failed" | string;
  job_id?: string | null;
  started_at?: string | null;
  ready_at?: string | null;
  error?: string | null;
  storyline_count?: number;
  implemented?: boolean;
};

export type ReportStorylineSection = {
  idx: number;
  title: string;
  kind: string;
  included: boolean;
  instructions?: string;
  agents: string[];
};

export type ReportPreviewBlock = {
  type:
    | "heading"
    | "paragraph"
    | "bullet"
    | "insight"
    | "page_break"
    | "table"
    | "cover_hero"
    | "divider"
    | "callout"
    | "meta"
    | string;
  text?: string;
  level?: number;
  muted?: boolean;
  rows?: string[][];
};

export type ReportPreviewSlide = {
  index: number;
  kind: string;
  eyebrow?: string;
  title: string;
  subtitle?: string;
  insight?: string;
  bullets?: string[];
  paragraphs?: string[];
  cards?: Array<{ label: string; body: string }>;
  agenda_items?: Array<{ num: string; title: string; blurb: string }>;
  meta_rows?: string[][];
  table?: string[][];
  page?: string;
  number?: string;
};

export type ReportPreviewPayload = {
  success: boolean;
  report_type: string;
  format?: "xlsx" | "docx" | "pdf" | "pptx" | string;
  // xlsx
  sheets?: string[];
  active_sheet?: string;
  rows?: Array<Array<string | number | boolean>>;
  // docx / pdf / pptx
  blocks?: ReportPreviewBlock[];
  slides?: ReportPreviewSlide[];
  block_count?: number;
  page_count?: number;
  slide_count?: number;
};

export type ReportDecisionChainBlock = {
  plain_english?: string;
  inputs?: Array<{ label: string; key?: string; value: string; source?: string }>;
  calculations?: Array<{
    label: string;
    key?: string;
    formula?: string;
    trace?: string;
    result?: string;
  }>;
  reads?: Array<{ label: string; value: string; source?: string }>;
  gaps?: Array<{ label: string; detail: string }>;
  source_entries?: Array<{ file: string; role?: string; used_by?: string }>;
  counts?: { chain?: number; sources?: number; gaps?: number; reads?: number };
};

export type ReportDecisionChainEntry = {
  agent: string;
  resolved?: string;
  available?: boolean;
  status?: string;
  coverage?: string;
  extract_source?: string;
  sources?: string[];
  chain?: ReportDecisionChainBlock;
};

export type ReportSourcesPayload = {
  success: boolean;
  report_type: string;
  sources: {
    data_room_files?: number;
    files?: string[];
    cited_files?: string[];
    cited_file_count?: number;
    web_research?: boolean;
    workflow_agents?: number;
    agent_keys?: string[];
    sections?: Array<{
      title: string;
      agents: string[];
      source_files?: string[];
      decision_chain?: ReportDecisionChainEntry[];
    }>;
    analyst_document?: boolean;
  };
};

export type ReportStreamHandlers = {
  onEvent?: (event: Record<string, unknown>) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
};

export async function reportsCatalogRequest(accessToken: string, dealId: string) {
  return apiRequest<{ success: boolean; data: ReportCatalogEntry[] }>(ENDPOINTS.reports(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function reportGenerateRequest(accessToken: string, dealId: string, reportType: string) {
  return apiRequest<{ job: string; report_type: string; status: string }>(
    ENDPOINTS.reportGenerate(dealId, reportType),
    { method: "POST", accessToken },
  );
}

export async function reportStatusRequest(accessToken: string, dealId: string, reportType: string) {
  return apiRequest<ReportCatalogEntry>(ENDPOINTS.reportStatus(dealId, reportType), {
    method: "GET",
    accessToken,
  });
}

export async function reportStorylineRequest(accessToken: string, dealId: string, reportType: string) {
  return apiRequest<{ success: boolean; report_type: string; sections: ReportStorylineSection[] }>(
    ENDPOINTS.reportStoryline(dealId, reportType),
    { method: "GET", accessToken },
  );
}

export async function reportSourcesRequest(accessToken: string, dealId: string, reportType: string) {
  return apiRequest<ReportSourcesPayload>(ENDPOINTS.reportSources(dealId, reportType), {
    method: "GET",
    accessToken,
  });
}

export async function reportPreviewRequest(
  accessToken: string,
  dealId: string,
  reportType: string,
  sheet?: string,
) {
  return apiRequest<ReportPreviewPayload>(ENDPOINTS.reportPreview(dealId, reportType, sheet), {
    method: "GET",
    accessToken,
  });
}

/** Fetch report artifact as an object URL (for in-browser PDF preview). Caller must revoke. */
export async function reportArtifactBlobUrlRequest(
  accessToken: string,
  dealId: string,
  reportType: string,
): Promise<string> {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.reportDownload(dealId, reportType)}`, {
    method: "GET",
    headers: {
      Accept: "application/pdf,application/octet-stream",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(messageFromBody(body, res.statusText), res.status, body);
  }
  const blob = await res.blob();
  const type = blob.type || res.headers.get("content-type") || "application/pdf";
  const pdfBlob = type.includes("pdf") ? blob : new Blob([blob], { type: "application/pdf" });
  return URL.createObjectURL(pdfBlob);
}

export async function reportDownloadRequest(
  accessToken: string,
  dealId: string,
  reportType: string,
  filename?: string,
) {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.reportDownload(dealId, reportType)}`, {
    method: "GET",
    headers: {
      Accept: "application/octet-stream",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(messageFromBody(body, res.statusText), res.status, body);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || `${reportType}.${res.headers.get("content-type")?.includes("sheet") ? "xlsx" : "bin"}`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export async function reportEventsStream(
  accessToken: string,
  dealId: string,
  reportType: string,
  handlers: ReportStreamHandlers = {},
) {
  const res = await fetch(`${API_BASE_URL}${ENDPOINTS.reportEvents(dealId, reportType)}`, {
    method: "GET",
    headers: {
      Accept: "text/event-stream",
      Authorization: `Bearer ${accessToken}`,
    },
  });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status, null);
  }
  if (!res.body) {
    throw new ApiError("Empty stream response", res.status, null);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const dispatchBlock = (block: string) => {
    const lines = block.split("\n");
    const dataLines: string[] = [];
    for (const line of lines) {
      if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let payload: Record<string, unknown>;
    try {
      payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    } catch {
      return;
    }
    handlers.onEvent?.(payload);
    const stage = String(payload.stage || "");
    if (stage === "error") {
      handlers.onError?.(String(payload.message || "Report generation failed"));
    } else if (stage === "done") {
      finished = true;
      handlers.onDone?.();
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      if (part.trim()) dispatchBlock(part);
    }
  }
  if (buffer.trim()) dispatchBlock(buffer);
  if (!finished) handlers.onDone?.();
}

// ---------------------------------------------------------------------------
// FDD workspace (scope editor, G2 claims gate)
// ---------------------------------------------------------------------------

export type FddScopeProfile = {
  profile_id: string;
  deal_slug: string;
  run_id?: string | null;
  status?: string;
  entities_in: string[];
  entities_out: string[];
  deal_type?: string | null;
  periods: string[];
  currency: string;
  scale?: string | null;
  materiality_m?: number | null;
  materiality_basis?: string;
  materiality_pct?: number;
  sections_in_scope: string[];
  notes?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
};

export type FddRunSummary = {
  run_id: string;
  status?: string;
  stage?: string;
  draft_mode?: boolean;
  g0_passed?: boolean;
  g1_approved?: boolean;
  g2_passed?: boolean;
  claims_built?: boolean;
  unreliable_modules?: string[];
  is_current?: boolean;
  created_at?: string;
  updated_at?: string | null;
};

export type FddGateState = {
  passed?: boolean;
  approved?: boolean;
  ready?: boolean;
  blocked?: boolean;
  blockers?: string[];
  unreliable_modules?: string[];
  auto_ok?: boolean;
  acknowledged?: boolean;
  claim_count?: number;
  financial_count?: number;
  contradicted?: number;
  unverifiable?: number;
  approval?: Record<string, unknown> | null;
  score?: number | null;
  held_back_exhibits?: string[];
};

export type FddClaimsLedger = {
  run_id: string;
  deal_slug: string;
  claim_count: number;
  financial_count: number;
  qualitative_count: number;
  agrees: number;
  contradicted: number;
  unverifiable: number;
  pending: number;
  unreliable_modules: string[];
  modules: Array<{
    source_agent: string;
    total: number;
    financial_total: number;
    failed: number;
    fail_rate: number;
    unreliable: boolean;
  }>;
  claims: Array<{
    claim_id: string;
    source_agent?: string | null;
    text: string;
    kind: string;
    test_result: string;
    failed: boolean;
    claimed_value?: number | null;
    databook_value?: number | null;
  }>;
};

export async function fddListRunsRequest(accessToken: string, dealId: string) {
  return apiRequest<{ success: boolean; data: FddRunSummary[] }>(ENDPOINTS.fddRuns(dealId), {
    method: "GET",
    accessToken,
  });
}

export async function fddCreateRunRequest(accessToken: string, dealId: string) {
  return apiRequest<{ success: boolean; data: Record<string, unknown> }>(ENDPOINTS.fddRuns(dealId), {
    method: "POST",
    accessToken,
    body: JSON.stringify({}),
  });
}

export async function fddGetScopeRequest(accessToken: string, dealId: string, runId: string) {
  return apiRequest<{
    success: boolean;
    data: { scope: FddScopeProfile; g1_ready: boolean; g1_blockers: string[] };
  }>(ENDPOINTS.fddScope(dealId, runId), { method: "GET", accessToken });
}

export async function fddPutScopeRequest(
  accessToken: string,
  dealId: string,
  runId: string,
  body: Partial<FddScopeProfile> & { allow_edit_approved?: boolean },
) {
  return apiRequest<{
    success: boolean;
    data: { scope: FddScopeProfile; g1_ready: boolean; g1_blockers: string[] };
  }>(ENDPOINTS.fddScope(dealId, runId), {
    method: "PUT",
    accessToken,
    body: JSON.stringify(body),
  });
}

export async function fddApproveG1Request(
  accessToken: string,
  dealId: string,
  runId: string,
  note?: string,
) {
  return apiRequest<{ success: boolean; data: Record<string, unknown> }>(
    ENDPOINTS.fddGateG1Approve(dealId, runId),
    { method: "POST", accessToken, body: JSON.stringify({ note, require_g0: true }) },
  );
}

export async function fddGetGatesRequest(accessToken: string, dealId: string, runId: string) {
  return apiRequest<{ success: boolean; data: Record<string, FddGateState> }>(
    ENDPOINTS.fddGates(dealId, runId),
    { method: "GET", accessToken },
  );
}

export async function fddAcknowledgeG2Request(
  accessToken: string,
  dealId: string,
  runId: string,
  opts: { note?: string; allow_unreliable?: boolean } = {},
) {
  return apiRequest<{ success: boolean; data: Record<string, unknown> }>(
    ENDPOINTS.fddGateG2Acknowledge(dealId, runId),
    {
      method: "POST",
      accessToken,
      body: JSON.stringify({
        note: opts.note,
        allow_unreliable: opts.allow_unreliable ?? true,
      }),
    },
  );
}

export async function fddGetClaimsRequest(accessToken: string, dealId: string, runId: string) {
  return apiRequest<{ success: boolean; data: FddClaimsLedger }>(ENDPOINTS.fddClaims(dealId, runId), {
    method: "GET",
    accessToken,
  });
}

export async function fddBuildClaimsRequest(accessToken: string, dealId: string, runId: string) {
  return apiRequest<{ success: boolean; data: { claims: FddClaimsLedger } }>(
    ENDPOINTS.fddClaimsBuild(dealId, runId),
    { method: "POST", accessToken, body: JSON.stringify({ open_requests: true }) },
  );
}

export async function fddPhase2Request(accessToken: string, dealId: string, runId: string) {
  return apiRequest<{ success: boolean; data: Record<string, unknown> }>(
    ENDPOINTS.fddPhase2(dealId, runId),
    { method: "POST", accessToken },
  );
}
