"use client";

import {
  chartMaxValue,
  formatChartValue,
  normalizeChartSpec,
  truncateChartLabel,
  type DocumentChartSpec,
} from "@/lib/documentChart";

function EmptyChartExhibit({ title }: { title: string }) {
  return (
    <div className="overflow-hidden rounded-lg border border-border-primary bg-white">
      <div className="border-b border-border-primary bg-[#f8fafc] px-4 py-2.5">
        <p className="text-[13px] font-semibold text-text-primary">{title}</p>
        <p className="text-[11px] text-text-secondary">Exhibit · awaiting numeric evidence</p>
      </div>
      <div className="flex h-[200px] items-end justify-center gap-3 px-6 pb-6 pt-4">
        {[0.35, 0.55, 0.42, 0.68, 0.48].map((h, i) => (
          <div
            key={i}
            className="w-10 rounded-t bg-[#e5e7eb]"
            style={{ height: `${Math.round(h * 100)}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function BarChartSvg({
  series,
  unit,
  max,
}: {
  series: Array<{ label: string; value: number }>;
  unit: string;
  max: number;
}) {
  const width = 560;
  const height = 220;
  const padL = 44;
  const padR = 16;
  const padT = 16;
  const padB = 52;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const barGap = 12;
  const barW = Math.min(56, (plotW - barGap * (series.length - 1)) / series.length);

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-[220px] w-full"
      role="img"
      aria-label="Bar chart exhibit"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const y = padT + plotH * (1 - tick);
        const val = Math.round(max * tick);
        return (
          <g key={tick}>
            <line x1={padL} y1={y} x2={width - padR} y2={y} stroke="#eef0f3" strokeWidth="1" />
            <text x={padL - 8} y={y + 4} textAnchor="end" className="fill-[#6b7280] text-[10px]">
              {val}
              {unit === "%" ? "%" : ""}
            </text>
          </g>
        );
      })}
      {series.map((row, i) => {
        const x = padL + i * (barW + barGap);
        const h = Math.max(4, (row.value / max) * plotH);
        const y = padT + plotH - h;
        return (
          <g key={`${row.label}-${i}`}>
            <rect x={x} y={y} width={barW} height={h} rx="4" fill="#1d4ed8" opacity="0.92" />
            <text
              x={x + barW / 2}
              y={y - 6}
              textAnchor="middle"
              className="fill-[#1e3a5f] text-[10px] font-medium"
            >
              {formatChartValue(row.value, unit)}
            </text>
            <text
              x={x + barW / 2}
              y={height - padB + 16}
              textAnchor="middle"
              className="fill-[#4b5563] text-[10px]"
            >
              {truncateChartLabel(row.label)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function LineChartSvg({
  series,
  unit,
  max,
}: {
  series: Array<{ label: string; value: number }>;
  unit: string;
  max: number;
}) {
  const width = 560;
  const height = 220;
  const padL = 44;
  const padR = 16;
  const padT = 16;
  const padB = 52;
  const plotW = width - padL - padR;
  const plotH = height - padT - padB;
  const step = series.length > 1 ? plotW / (series.length - 1) : 0;

  const points = series.map((row, i) => {
    const x = padL + i * step;
    const y = padT + plotH - Math.max(4, (row.value / max) * plotH);
    return { ...row, x, y };
  });
  const polyline = points.map((p) => `${p.x},${p.y}`).join(" ");
  const area = `${points[0]?.x ?? padL},${padT + plotH} ${polyline} ${points[points.length - 1]?.x ?? padL},${padT + plotH}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-[220px] w-full"
      role="img"
      aria-label="Line chart exhibit"
    >
      {[0, 0.25, 0.5, 0.75, 1].map((tick) => {
        const y = padT + plotH * (1 - tick);
        const val = Math.round(max * tick);
        return (
          <g key={tick}>
            <line x1={padL} y1={y} x2={width - padR} y2={y} stroke="#eef0f3" strokeWidth="1" />
            <text x={padL - 8} y={y + 4} textAnchor="end" className="fill-[#6b7280] text-[10px]">
              {val}
              {unit === "%" ? "%" : ""}
            </text>
          </g>
        );
      })}
      {points.length > 1 ? (
        <>
          <polygon points={area} fill="#1d4ed8" fillOpacity="0.08" />
          <polyline
            points={polyline}
            fill="none"
            stroke="#1d4ed8"
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </>
      ) : null}
      {points.map((p, i) => (
        <g key={`${p.label}-${i}`}>
          <circle cx={p.x} cy={p.y} r="4.5" fill="#1d4ed8" />
          <text x={p.x} y={p.y - 10} textAnchor="middle" className="fill-[#1e3a5f] text-[10px] font-medium">
            {formatChartValue(p.value, unit)}
          </text>
          <text
            x={p.x}
            y={height - padB + 16}
            textAnchor="middle"
            className="fill-[#4b5563] text-[10px]"
          >
            {truncateChartLabel(p.label)}
          </text>
        </g>
      ))}
    </svg>
  );
}

export function DocumentChartExhibit({
  label,
  chart,
}: {
  label: string;
  chart?: DocumentChartSpec | null;
}) {
  const spec = normalizeChartSpec(label, chart);
  if (spec.placeholder || !spec.series.length) {
    return <EmptyChartExhibit title={spec.title} />;
  }

  const max = chartMaxValue(spec.series);
  const isLine = spec.type === "line";

  return (
    <div className="overflow-hidden rounded-lg border border-border-primary bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-border-primary bg-[#f8fafc] px-4 py-2.5">
        <div>
          <p className="text-[13px] font-semibold text-text-primary">{spec.title}</p>
          <p className="text-[11px] text-text-secondary">
            {isLine ? "Line exhibit" : "Bar exhibit"} · data room evidence
          </p>
        </div>
        <span className="rounded-full bg-[#eff6ff] px-2 py-0.5 text-[10px] font-medium text-[#1d4ed8]">
          {spec.series.length} points
        </span>
      </div>
      <div className="px-3 py-3">
        {isLine ? (
          <LineChartSvg series={spec.series} unit={spec.unit} max={max} />
        ) : (
          <BarChartSvg series={spec.series} unit={spec.unit} max={max} />
        )}
      </div>
    </div>
  );
}
