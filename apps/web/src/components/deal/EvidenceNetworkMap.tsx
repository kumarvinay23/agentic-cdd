"use client";

import { useMemo } from "react";
import type { EvidenceGraph, EvidenceNode, EvidenceStatus } from "@/lib/evidence-types";

type Props = {
  graph: EvidenceGraph;
  selectedId: string | null;
  onSelect: (node: EvidenceNode) => void;
};

type Point = { x: number; y: number; r: number; node: EvidenceNode; color: string; angle: number };

const WIDTH = 1120;
const HEIGHT = 960;
const CX = WIDTH / 2;
const CY = HEIGHT / 2;
const WS_RADIUS = 188;
const REQ_RADIUS = 338;
const PATH_COLOR = "#1e3a5f";

function polar(radius: number, angle: number) {
  return { x: CX + radius * Math.cos(angle), y: CY + radius * Math.sin(angle) };
}

function nodeRadius(node: EvidenceNode): number {
  if (node.kind === "root") return 34;
  if (node.kind === "workstream") return 28;
  return 5.5 + Math.max(1, node.weight || 1) * 2.2;
}

function nodeColor(node: EvidenceNode, legend: EvidenceGraph["status_legend"]): string {
  if (node.kind === "root") return PATH_COLOR;
  if (node.kind === "workstream") return "#ffffff";
  return legend[(node.status || "request_vdr") as EvidenceStatus]?.color || "#94908A";
}

function wrapLabel(label: string, maxChars: number): string[] {
  if (label.length <= maxChars) return [label];
  const words = label.split(/\s+/);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (next.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, 3);
}

function gapCount(roll: EvidenceGraph["workstreams"][number]["roll"]): number {
  return (roll.web || 0) + (roll.request_vdr || 0) + (roll.primary || 0);
}

function pathSet(graph: EvidenceGraph, selectedId: string | null): Set<string> {
  const ids = new Set<string>();
  if (!selectedId) return ids;
  const node = graph.nodes.find((n) => n.id === selectedId);
  if (!node) return ids;
  ids.add(node.id);
  if (node.kind === "req" && node.ws) {
    ids.add(`ws:${node.ws}`);
    ids.add("root");
  } else if (node.kind === "workstream") {
    ids.add("root");
  }
  return ids;
}

export function EvidenceNetworkMap({ graph, selectedId, onSelect }: Props) {
  const { points, lines } = useMemo(() => {
    const workstreams = graph.nodes.filter((n) => n.kind === "workstream");
    const reqs = graph.nodes.filter((n) => n.kind === "req");
    const laid: Point[] = [];
    const pos = new Map<string, { x: number; y: number }>();
    const root = graph.nodes.find((n) => n.kind === "root");

    if (root) {
      laid.push({
        node: root,
        x: CX,
        y: CY,
        r: nodeRadius(root),
        color: nodeColor(root, graph.status_legend),
        angle: 0,
      });
      pos.set("root", { x: CX, y: CY });
    }

    const childCounts = workstreams.map((ws) => reqs.filter((r) => r.ws === ws.ws).length);
    const totalChildren = childCounts.reduce((sum, n) => sum + n, 0) || 1;
    const gap = 0.08;
    let cursor = -Math.PI / 2;

    workstreams.forEach((ws, index) => {
      const children = reqs.filter((r) => r.ws === ws.ws);
      const slice = (childCounts[index] / totalChildren) * (2 * Math.PI - gap * workstreams.length);
      const wsAngle = cursor + slice / 2;
      const wp = polar(WS_RADIUS, wsAngle);
      laid.push({
        node: ws,
        x: wp.x,
        y: wp.y,
        r: nodeRadius(ws),
        color: nodeColor(ws, graph.status_legend),
        angle: wsAngle,
      });
      pos.set(ws.id, wp);

      children.forEach((req, j) => {
        const t = children.length === 1 ? 0.5 : (j + 0.5) / children.length;
        const reqAngle = cursor + t * slice;
        const rp = polar(REQ_RADIUS, reqAngle);
        laid.push({
          node: req,
          x: rp.x,
          y: rp.y,
          r: nodeRadius(req),
          color: nodeColor(req, graph.status_legend),
          angle: reqAngle,
        });
        pos.set(req.id, rp);
      });
      cursor += slice + gap;
    });

    const edges = graph.edges
      .map((edge) => {
        const a = pos.get(edge.source);
        const b = pos.get(edge.target);
        if (!a || !b) return null;
        return { ...edge, a, b };
      })
      .filter(
        (e): e is { source: string; target: string; a: { x: number; y: number }; b: { x: number; y: number } } =>
          Boolean(e),
      );

    return { points: laid, lines: edges };
  }, [graph]);

  const highlighted = pathSet(graph, selectedId);
  const hasSelection = highlighted.size > 0;

  const wsGaps = useMemo(() => {
    const map = new Map<string, number>();
    for (const ws of graph.workstreams) map.set(ws.id, gapCount(ws.roll));
    return map;
  }, [graph.workstreams]);

  return (
    <div className="overflow-hidden rounded-xl border border-[#e6e1d6] bg-[#f7f4ee]">
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="h-auto w-full" role="img" aria-label="Evidence network map">
        {lines.map((line) => {
          const onPath = hasSelection && highlighted.has(line.source) && highlighted.has(line.target);
          return (
            <line
              key={`${line.source}-${line.target}`}
              x1={line.a.x}
              y1={line.a.y}
              x2={line.b.x}
              y2={line.b.y}
              stroke={onPath ? PATH_COLOR : "#d4cec2"}
              strokeWidth={onPath ? 3.2 : 1.35}
              opacity={hasSelection && !onPath ? 0.28 : 1}
            />
          );
        })}
        {points.map((point) => {
          const selected = selectedId === point.node.id;
          const onPath = !hasSelection || highlighted.has(point.node.id);
          const rightSide = Math.cos(point.angle) >= 0;
          const linesOfText =
            point.node.kind === "root"
              ? ["Data room"]
              : wrapLabel(point.node.label, point.node.kind === "workstream" ? 14 : 22);
          const labelRadius =
            point.node.kind === "req"
              ? REQ_RADIUS + point.r + 10
              : point.node.kind === "workstream"
                ? WS_RADIUS + 42
                : 0;
          const ancestor = hasSelection && highlighted.has(point.node.id) && point.node.kind !== "req";
          const labelPos =
            point.node.kind === "root"
              ? { x: point.x, y: point.y + 52 }
              : polar(labelRadius, point.angle);
          const anchor =
            point.node.kind === "req" ? (rightSide ? "start" : "end") : "middle";
          const labelDx = point.node.kind === "req" ? (rightSide ? 6 : -6) : 0;
          let stroke = "#fff";
          let strokeWidth = 1.5;
          if (point.node.kind === "workstream") {
            stroke = ancestor || selected ? PATH_COLOR : "#cfc8bb";
            strokeWidth = ancestor || selected ? 2.6 : 1.5;
          } else if (selected) {
            stroke = PATH_COLOR;
            strokeWidth = 3.2;
          } else if (point.node.kind === "root") {
            stroke = PATH_COLOR;
            strokeWidth = 0;
          }

          return (
            <g
              key={point.node.id}
              className="cursor-pointer"
              opacity={onPath ? 1 : 0.28}
              onClick={() => onSelect(point.node)}
            >
              <circle cx={point.x} cy={point.y} r={point.r + 10} fill="transparent" />
              <circle
                cx={point.x}
                cy={point.y}
                r={point.r + (selected ? 3 : 0)}
                fill={point.node.kind === "workstream" ? "#fff" : point.color}
                stroke={stroke}
                strokeWidth={strokeWidth}
              />
              {point.node.kind === "workstream" ? (
                <text
                  x={point.x}
                  y={point.y + 4}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight="700"
                  fill="#1f2937"
                >
                  {wsGaps.get(point.node.ws || "") ?? 0}
                </text>
              ) : null}
              {linesOfText.map((line, i) => (
                <text
                  key={`${point.node.id}-${i}`}
                  x={labelPos.x + labelDx}
                  y={labelPos.y + i * 12}
                  textAnchor={anchor}
                  fontSize={point.node.kind === "req" ? 11 : 12}
                  fontWeight={point.node.kind === "req" ? 500 : 650}
                  fill={selected ? PATH_COLOR : "#374151"}
                >
                  {line}
                </text>
              ))}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
