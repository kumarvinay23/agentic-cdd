export const product = {
  name: "Agentic CDD",
  shortName: "ACDD",
} as const;

/** Backend base URL (no trailing slash). Default matches B3 local API port. */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ||
  "http://127.0.0.1:4600";

export const AUTH_ROUTES = {
  LOGIN: "/login",
  REGISTER: "/register",
  DASHBOARD: "/",
} as const;

export const ENDPOINTS = {
  HEALTH: "/api/v1/health",
  AUTH: {
    LOGIN: "/api/v1/auth/login",
    REGISTER: "/api/v1/auth/register",
    REFRESH: "/api/v1/auth/refresh",
    LOGOUT: "/api/v1/auth/logout",
    ME: "/api/v1/auth/me",
  },
  DEALS: "/api/v1/deals",
  USAGE: "/api/v1/me/usage",
  SECTORS: "/api/v1/portfolios/cdd/sectors",
  dealDashboard: (id: string) => `/api/v1/deal-rooms/${id}/dashboard`,
  cddHealth: (id: string) => `/api/v1/portfolios/${id}/cdd/health`,
  cddVdr: (id: string) => `/api/v1/portfolios/${id}/cdd/vdr`,
  cddVdrUpload: (id: string) => `/api/v1/portfolios/${id}/cdd/vdr/upload`,
  cddVdrDelete: (id: string, filename: string) =>
    `/api/v1/portfolios/${id}/cdd/vdr/${encodeURIComponent(filename)}`,
  cddVdrDownload: (id: string, filename: string) =>
    `/api/v1/portfolios/${id}/cdd/vdr/files/${encodeURIComponent(filename)}`,
  cddSync: (id: string) => `/api/v1/portfolios/${id}/cdd/sync`,
  cddAnalyze: (id: string) => `/api/v1/portfolios/${id}/cdd/analyze`,
  cddVdrAnalyze: (id: string) => `/api/v1/portfolios/${id}/cdd/vdr/analyze`,
  cddVdrGraph: (id: string) => `/api/v1/portfolios/${id}/cdd/vdr/graph`,
  cddIngestion: (id: string) => `/api/v1/portfolios/${id}/cdd/ingestion`,
  cddDatabook: (id: string) => `/api/v1/portfolios/${id}/cdd/databook`,
  cddDatabookRescan: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/rescan`,
  cddDatabookDeep: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/deep`,
  cddDatabookRows: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/rows`,
  cddDatabookFindings: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/findings`,
  cddDatabookPromoted: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/promoted`,
  cddDatabookPromotedCsv: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/promoted.csv`,
  cddDatabookExportXlsx: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/export.xlsx`,
  cddDatabookImportXlsx: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/import.xlsx`,
  cddDatabookCorrect: (id: string, rowId: string) =>
    `/api/v1/portfolios/${id}/cdd/databook/rows/${encodeURIComponent(rowId)}/correct`,
  cddDatabookDrop: (id: string, rowId: string) =>
    `/api/v1/portfolios/${id}/cdd/databook/rows/${encodeURIComponent(rowId)}/drop`,
  cddDatabookVouch: (id: string, rowId: string) =>
    `/api/v1/portfolios/${id}/cdd/databook/rows/${encodeURIComponent(rowId)}/vouch`,
  cddDatabookAccept: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/conflicts/accept`,
  cddDatabookReread: (id: string) => `/api/v1/portfolios/${id}/cdd/databook/reread`,
  cddDataQuality: (id: string) => `/api/v1/portfolios/${id}/cdd/data-quality`,
  pipeline: (id: string) => `/api/v1/portfolios/${id}/pipeline`,
  pipelinePhases: (id: string) => `/api/v1/portfolios/${id}/pipeline/phases`,
  pipelineRun: (id: string) => `/api/v1/portfolios/${id}/pipeline/run`,
  pipelinePhaseRun: (id: string, phaseId: string) =>
    `/api/v1/portfolios/${id}/pipeline/phase/${encodeURIComponent(phaseId)}/run`,
  pipelineAgentOutput: (id: string, agentKey: string) =>
    `/api/v1/portfolios/${id}/pipeline/agents/${encodeURIComponent(agentKey)}/output`,
  documents: (id: string) => `/api/v1/portfolios/${id}/documents`,
  documentMessages: (id: string) => `/api/v1/portfolios/${id}/documents/messages`,
  documentMessagesStream: (id: string) => `/api/v1/portfolios/${id}/documents/messages/stream`,
  documentSuggestions: (id: string) => `/api/v1/portfolios/${id}/documents/suggestions`,
  documentDecisionChain: (id: string) => `/api/v1/portfolios/${id}/documents/decision-chain`,
  documentExport: (id: string) => `/api/v1/portfolios/${id}/documents/export`,
  agentDocuments: (id: string, agentKey: string) =>
    `/api/v1/portfolios/${id}/agents/${encodeURIComponent(agentKey)}/documents`,
  agentDocumentMessages: (id: string, agentKey: string) =>
    `/api/v1/portfolios/${id}/agents/${encodeURIComponent(agentKey)}/documents/messages`,
  agentDocumentMessagesStream: (id: string, agentKey: string) =>
    `/api/v1/portfolios/${id}/agents/${encodeURIComponent(agentKey)}/documents/messages/stream`,
  agentDocumentSuggestions: (id: string, agentKey: string) =>
    `/api/v1/portfolios/${id}/agents/${encodeURIComponent(agentKey)}/documents/suggestions`,
  agentDocumentDecisionChain: (id: string, agentKey: string) =>
    `/api/v1/portfolios/${id}/agents/${encodeURIComponent(agentKey)}/documents/decision-chain`,
  agentDocumentVersions: (id: string, agentKey: string) =>
    `/api/v1/portfolios/${id}/agents/${encodeURIComponent(agentKey)}/documents/versions`,
  agentDocumentVersion: (id: string, agentKey: string, n: number) =>
    `/api/v1/portfolios/${id}/agents/${encodeURIComponent(agentKey)}/documents/versions/${n}`,
  cddCapabilities: (id: string) => `/api/v1/portfolios/${id}/cdd/capabilities`,
  reports: (id: string) => `/api/v1/portfolios/${id}/reports`,
  reportGenerate: (id: string, reportType: string) =>
    `/api/v1/portfolios/${id}/reports/${encodeURIComponent(reportType)}/generate`,
  reportEvents: (id: string, reportType: string) =>
    `/api/v1/portfolios/${id}/reports/${encodeURIComponent(reportType)}/events`,
  reportStatus: (id: string, reportType: string) =>
    `/api/v1/portfolios/${id}/reports/${encodeURIComponent(reportType)}/status`,
  reportDownload: (id: string, reportType: string) =>
    `/api/v1/portfolios/${id}/reports/${encodeURIComponent(reportType)}/download`,
  reportPreview: (id: string, reportType: string, sheet?: string) => {
    const base = `/api/v1/portfolios/${id}/reports/${encodeURIComponent(reportType)}/preview`;
    return sheet ? `${base}?sheet=${encodeURIComponent(sheet)}` : base;
  },
  reportStoryline: (id: string, reportType: string) =>
    `/api/v1/portfolios/${id}/reports/${encodeURIComponent(reportType)}/storyline`,
  reportSources: (id: string, reportType: string) =>
    `/api/v1/portfolios/${id}/reports/${encodeURIComponent(reportType)}/sources`,
} as const;
