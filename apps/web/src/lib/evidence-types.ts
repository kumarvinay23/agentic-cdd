export type EvidenceStatus = "have" | "partial" | "web" | "request_vdr" | "primary";
export type EvidenceDataClass = "vdr" | "web" | "primary";

export type EvidenceCounts = Record<EvidenceStatus, number>;

export type EvidenceScorecard = {
  readiness: number;
  tier: string;
  counts: EvidenceCounts;
  total_reqs: number;
  primary_gap: number;
  web_fillable: number;
  request_vdr: number;
};

export type EvidenceLegendItem = {
  label: string;
  color: string;
  remedy: string;
};

export type EvidenceNode = {
  id: string;
  kind: "root" | "workstream" | "req";
  label: string;
  ws?: string | null;
  desc?: string;
  data_class?: EvidenceDataClass;
  status?: EvidenceStatus;
  weight?: number;
  so_what?: string;
  remedy?: string;
  trail?: string[];
  evidence_type?: string;
};

export type EvidenceWorkstream = {
  id: string;
  label: string;
  desc: string;
  roll: EvidenceCounts;
};

export type EvidenceGraph = {
  company: string;
  vdr_files: string[];
  nodes: EvidenceNode[];
  edges: Array<{ source: string; target: string }>;
  status_legend: Record<EvidenceStatus, EvidenceLegendItem>;
  workstreams: EvidenceWorkstream[];
  scorecard: EvidenceScorecard;
};

export type EvidenceAnalyzePayload = {
  status: string;
  scorecard: EvidenceScorecard;
  vdr: string[];
  graph: EvidenceGraph;
  generated_at?: string;
};

export const STATUS_ORDER: EvidenceStatus[] = [
  "have",
  "partial",
  "web",
  "request_vdr",
  "primary",
];

export function isAvailable(status?: EvidenceStatus): boolean {
  return status === "have" || status === "partial";
}

export function dataClassLabel(dataClass?: EvidenceDataClass): string {
  if (dataClass === "vdr") return "Data room";
  if (dataClass === "web") return "Web";
  if (dataClass === "primary") return "Primary";
  return dataClass || "";
}
