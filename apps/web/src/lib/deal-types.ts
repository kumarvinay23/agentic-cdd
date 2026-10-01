export type Deal = {
  id: string;
  uuid: string;
  slug: string;
  name: string;
  company: string;
  description: string;
  sector: string;
  status: string;
  tags: string[];
  docs_count: number;
  agents_running: number;
  reports_ready: number;
  summary?: string;
  team_label?: string;
  created_at?: string | null;
};

export type PortfolioMetrics = {
  active_deals: number;
  agents_running_now: number;
  reports_ready: number;
  total_deals: number;
};

export type UsageStats = {
  agent_runs: number;
  vdr_files: number;
  vdr_bytes: number;
};

export type SectorOption = {
  id: string;
  label: string;
  has_pack?: boolean;
};
