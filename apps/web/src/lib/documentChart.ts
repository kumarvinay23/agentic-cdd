/** Chart exhibit helpers for Document Workspace [[CHART]] markers. */

export type ChartSeriesPoint = {
  label: string;
  value: number;
};

export type DocumentChartSpec = {
  type?: string;
  title?: string;
  series?: ChartSeriesPoint[];
  placeholder?: boolean;
  unit?: string;
};

export function normalizeChartSpec(
  label: string,
  chart?: DocumentChartSpec | null,
): Required<Pick<DocumentChartSpec, "type" | "title" | "series" | "placeholder" | "unit">> {
  const title = chart?.title || label || "Exhibit";
  const series = chart?.series || [];
  const lower = title.toLowerCase();
  const type =
    chart?.type ||
    (lower.includes("growth") || (lower.includes("trend") && !lower.includes("share"))
      ? "line"
      : "bar");
  return {
    type,
    title,
    series,
    placeholder: chart?.placeholder ?? series.length === 0,
    unit: chart?.unit || "%",
  };
}

export function chartMaxValue(series: ChartSeriesPoint[]): number {
  if (!series.length) return 100;
  const peak = Math.max(...series.map((s) => s.value));
  if (peak <= 0) return 100;
  if (peak <= 100) return 100;
  return Math.ceil(peak / 10) * 10;
}

export function truncateChartLabel(label: string, max = 14): string {
  const t = label.trim();
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

export function formatChartValue(value: number, unit: string): string {
  const rounded = Number.isInteger(value) ? String(value) : value.toFixed(1);
  return unit === "%" ? `${rounded}%` : `${rounded}${unit}`;
}
