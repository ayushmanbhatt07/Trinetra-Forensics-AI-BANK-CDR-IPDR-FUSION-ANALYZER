"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Network,
  Phone,
  Landmark,
  GitFork,
  RotateCw,
  Crosshair,
  Smartphone,
  Filter,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Search,
  X,
  Layers,
  Eye,
  EyeOff,
  ArrowRight,
  ShieldAlert,
  CheckCircle2,
  CircleDot,
  Flame,
  Info
} from "lucide-react";
import { api, type EgoNet, type Phone as PhoneProfile, type MoneyGraph, type DossierIntelligence, type RelationshipIntel } from "@/lib/api";
import { toast } from "sonner";
import { InvestigationPanel } from "@/components/dashboard/investigation-panel";
import { RadialIntro, type OrbitItem } from "@/components/ui/radial-intro";
import { usePipeline } from "@/lib/pipeline-context";

type Tab = "calls" | "money" | "link" | "coincidence";
type PanelPayload =
  | { type: "entity"; info: DossierIntelligence }
  | { type: "relationship"; rel: RelationshipIntel };

/** DFS cycle detection over a money-flow graph. */
function findCycle(graph: MoneyGraph | null): string[] {
  if (!graph || graph.edges.length === 0) return [];
  const adj = new Map<string, string[]>();
  for (const e of graph.edges) {
    if (!adj.has(e.source)) adj.set(e.source, []);
    adj.get(e.source)!.push(e.target);
  }
  const state = new Map<string, 0 | 1 | 2>();
  const stack: string[] = [];
  const found: string[] = [];
  const dfs = (v: string): boolean => {
    state.set(v, 1);
    stack.push(v);
    for (const w of adj.get(v) ?? []) {
      if (!state.has(w)) {
        if (dfs(w)) return true;
      } else if (state.get(w) === 1) {
        found.push(...stack.slice(stack.indexOf(w)));
        return true;
      }
    }
    stack.pop();
    state.set(v, 2);
    return false;
  };
  for (const v of adj.keys()) {
    if (!state.has(v) && dfs(v)) break;
  }
  return found.slice(0, 10);
}

const fmtMoney = (n: number) => "₹" + Math.round(n || 0).toLocaleString("en-IN");
const fmtCompact = (n: number) => {
  if (!n) return "₹0";
  if (n >= 10000000) return `₹${(n / 10000000).toFixed(1)} Cr`;
  if (n >= 100000) return `₹${(n / 100000).toFixed(1)} L`;
  if (n >= 1000) return `₹${(n / 1000).toFixed(0)}k`;
  return `₹${n.toFixed(0)}`;
};

const riskColor = (risk?: number) => {
  if ((risk ?? 0) >= 75) return "#ef4444";
  if ((risk ?? 0) >= 50) return "#f97316";
  if ((risk ?? 0) >= 25) return "#eab308";
  return "#10b981";
};

// ---------------------------------------------------------------------------
// VIEWPORT PAN & ZOOM WRAPPER
// ---------------------------------------------------------------------------
function GraphViewport({
  children,
  viewWidth = 900,
  viewHeight = 650,
  zoom,
  setZoom,
  pan,
  setPan,
}: {
  children: React.ReactNode;
  viewWidth?: number;
  viewHeight?: number;
  zoom: number;
  setZoom: React.Dispatch<React.SetStateAction<number>>;
  pan: { x: number; y: number };
  setPan: React.Dispatch<React.SetStateAction<{ x: number; y: number }>>;
}) {
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });

  const handleMouseDown = (e: React.MouseEvent) => {
    // Only drag on background, not on buttons or nodes
    if ((e.target as HTMLElement).tagName === "svg" || (e.target as HTMLElement).id === "graph-bg") {
      isDragging.current = true;
      dragStart.current = { x: e.clientX - pan.x, y: e.clientY - pan.y };
    }
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (isDragging.current) {
      setPan({
        x: e.clientX - dragStart.current.x,
        y: e.clientY - dragStart.current.y,
      });
    }
  };

  const handleMouseUp = () => {
    isDragging.current = false;
  };

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.1 : -0.1;
    setZoom((z) => Math.min(3.5, Math.max(0.4, Number((z + delta).toFixed(2)))));
  };

  const resetView = () => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  };

  return (
    <div
      className="relative w-full overflow-hidden bg-slate-950/70 border border-border/80 rounded-xl cursor-grab active:cursor-grabbing select-none"
      style={{ height: `${viewHeight}px` }}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onWheel={handleWheel}
    >
      {/* Interactive Zoom Toolbar */}
      <div className="absolute bottom-3 right-3 z-20 flex items-center gap-1 bg-slate-900/90 backdrop-blur border border-border/80 p-1 rounded-lg shadow-xl font-mono text-xs">
        <button
          onClick={() => setZoom((z) => Math.min(3.5, z + 0.2))}
          className="p-1.5 hover:bg-slate-800 rounded text-slate-300 hover:text-white transition-colors"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <span className="text-[11px] font-bold text-cyan-400 px-1.5 min-w-[42px] text-center">
          {Math.round(zoom * 100)}%
        </span>
        <button
          onClick={() => setZoom((z) => Math.max(0.4, z - 0.2))}
          className="p-1.5 hover:bg-slate-800 rounded text-slate-300 hover:text-white transition-colors"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <div className="w-px h-4 bg-border/60 mx-1" />
        <button
          onClick={resetView}
          className="p-1.5 hover:bg-slate-800 rounded text-slate-300 hover:text-white transition-colors"
          title="Reset Zoom & Pan"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* SVG Canvas */}
      <svg
        id="graph-bg"
        viewBox={`${-viewWidth / 2} ${-viewHeight / 2} ${viewWidth} ${viewHeight}`}
        className="w-full h-full"
      >
        <g transform={`translate(${pan.x}, ${pan.y}) scale(${zoom})`}>
          {children}
        </g>
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MONEY FLOW GRAPH (CLUSTERED PHYSICS & SMART LABELS)
// ---------------------------------------------------------------------------
const MoneyGraphView = React.memo(function MoneyGraphView({
  graph,
  onNodeClick,
  onEdgeClick,
  minAmount = 0,
  searchQuery = "",
  showAllLabels = false,
  maxNodes = 60,
}: {
  graph: MoneyGraph;
  onNodeClick: (id: string, kind?: string) => void;
  onEdgeClick: (a: string, b: string) => void;
  minAmount?: number;
  searchQuery?: string;
  showAllLabels?: boolean;
  maxNodes?: number;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Filter edges by minimum amount threshold
  const filteredEdges = useMemo(() => {
    return (graph.edges || []).filter((e) => e.amount >= minAmount);
  }, [graph.edges, minAmount]);

  // Aggregate in/out flow volume per node
  const nodeFlows = useMemo(() => {
    const flows: Record<string, { inAmount: number; outAmount: number; total: number; degree: number }> = {};
    for (const e of filteredEdges) {
      if (!flows[e.source]) flows[e.source] = { inAmount: 0, outAmount: 0, total: 0, degree: 0 };
      if (!flows[e.target]) flows[e.target] = { inAmount: 0, outAmount: 0, total: 0, degree: 0 };
      flows[e.source].outAmount += e.amount;
      flows[e.source].total += e.amount;
      flows[e.source].degree += 1;
      flows[e.target].inAmount += e.amount;
      flows[e.target].total += e.amount;
      flows[e.target].degree += 1;
    }
    return flows;
  }, [filteredEdges]);

  // Top nodes sorted by transaction turnover
  const activeNodes = useMemo(() => {
    const all = graph.nodes || [];
    const scored = all.map((n) => ({
      ...n,
      turnover: nodeFlows[n.id]?.total || 0,
      degree: nodeFlows[n.id]?.degree || 0,
    }));
    // Sort by turnover, prioritize nodes with active edges
    scored.sort((a, b) => b.turnover - a.turnover || b.degree - a.degree);
    return scored.slice(0, maxNodes);
  }, [graph.nodes, nodeFlows, maxNodes]);

  const activeNodeIds = useMemo(() => new Set(activeNodes.map((n) => n.id)), [activeNodes]);

  const visibleEdges = useMemo(() => {
    return filteredEdges.filter((e) => activeNodeIds.has(e.source) && activeNodeIds.has(e.target));
  }, [filteredEdges, activeNodeIds]);

  // Top 8 hubs for automatic label display
  const topHubIds = useMemo(() => {
    return new Set(activeNodes.slice(0, 8).map((n) => n.id));
  }, [activeNodes]);

  // Calculate Clustered Layout Coordinates (Concentric Multi-Orbital Layout)
  const positions: Record<string, { x: number; y: number; r: number }> = useMemo(() => {
    const pos: Record<string, { x: number; y: number; r: number }> = {};
    const n = activeNodes.length;
    if (n === 0) return pos;

    // Center Core (Top 4 Highest Volume Nodes)
    const coreCount = Math.min(4, n);
    for (let i = 0; i < coreCount; i++) {
      const angle = (i / coreCount) * 2 * Math.PI - Math.PI / 4;
      pos[activeNodes[i].id] = {
        x: Math.cos(angle) * 75,
        y: Math.sin(angle) * 75,
        r: 16,
      };
    }

    // Inner Ring (Nodes 5 to 16)
    const ring1Start = coreCount;
    const ring1End = Math.min(16, n);
    const ring1Count = ring1End - ring1Start;
    for (let i = 0; i < ring1Count; i++) {
      const angle = (i / ring1Count) * 2 * Math.PI;
      pos[activeNodes[ring1Start + i].id] = {
        x: Math.cos(angle) * 190,
        y: Math.sin(angle) * 190,
        r: 13,
      };
    }

    // Outer Ring (Nodes 17 to 40)
    const ring2Start = ring1End;
    const ring2End = Math.min(40, n);
    const ring2Count = ring2End - ring2Start;
    for (let i = 0; i < ring2Count; i++) {
      const angle = (i / ring2Count) * 2 * Math.PI + Math.PI / 12;
      pos[activeNodes[ring2Start + i].id] = {
        x: Math.cos(angle) * 310,
        y: Math.sin(angle) * 310,
        r: 10,
      };
    }

    // Peripheral Ring (Nodes 41+)
    const ring3Start = ring2End;
    const ring3Count = n - ring3Start;
    for (let i = 0; i < ring3Count; i++) {
      const angle = (i / ring3Count) * 2 * Math.PI;
      pos[activeNodes[ring3Start + i].id] = {
        x: Math.cos(angle) * 410,
        y: Math.sin(angle) * 410,
        r: 8,
      };
    }

    return pos;
  }, [activeNodes]);

  // Connected neighbors for hover highlighting
  const connectedNeighbors = useMemo(() => {
    if (!hoveredNode) return null;
    const neighbors = new Set<string>([hoveredNode]);
    const edges = new Set<string>();
    for (const e of visibleEdges) {
      if (e.source === hoveredNode) {
        neighbors.add(e.target);
        edges.add(`${e.source}->${e.target}`);
      } else if (e.target === hoveredNode) {
        neighbors.add(e.source);
        edges.add(`${e.source}->${e.target}`);
      }
    }
    return { nodes: neighbors, edges };
  }, [hoveredNode, visibleEdges]);

  const maxEdgeAmount = Math.max(1, ...visibleEdges.map((e) => e.amount));

  // Hovered node details for HUD
  const hoveredDetails = useMemo(() => {
    if (!hoveredNode) return null;
    const node = activeNodes.find((n) => n.id === hoveredNode);
    const flow = nodeFlows[hoveredNode] || { inAmount: 0, outAmount: 0, total: 0, degree: 0 };
    return {
      id: hoveredNode,
      kind: node?.kind || "account",
      inflow: flow.inAmount,
      outflow: flow.outAmount,
      total: flow.total,
      degree: flow.degree,
    };
  }, [hoveredNode, activeNodes, nodeFlows]);

  return (
    <div className="relative w-full">
      {/* Floating HUD Inspector */}
      {hoveredDetails && (
        <div className="absolute top-3 left-3 z-30 p-3 bg-slate-900/95 backdrop-blur-md border border-cyan-500/50 rounded-xl shadow-2xl font-mono text-xs space-y-1.5 min-w-[240px] pointer-events-none animate-in fade-in zoom-in-95 duration-150">
          <div className="flex items-center justify-between gap-2 border-b border-border/60 pb-1.5">
            <span className="font-bold text-cyan-300 truncate max-w-[170px]">
              {hoveredDetails.id}
            </span>
            <Badge variant="outline" className="text-[9px] uppercase font-bold text-cyan-400 border-cyan-800">
              {hoveredDetails.kind}
            </Badge>
          </div>
          <div className="flex justify-between text-[11px] text-slate-300 pt-0.5">
            <span className="text-slate-400">Total Flow:</span>
            <b className="text-emerald-400">{fmtMoney(hoveredDetails.total)}</b>
          </div>
          <div className="flex justify-between text-[11px] text-slate-400">
            <span>In: <b className="text-emerald-300">{fmtMoney(hoveredDetails.inflow)}</b></span>
            <span>Out: <b className="text-red-400">{fmtMoney(hoveredDetails.outflow)}</b></span>
          </div>
          <div className="flex justify-between text-[10px] text-slate-400 pt-1 border-t border-border/40">
            <span>Connections: <b className="text-white">{hoveredDetails.degree}</b> peers</span>
            <span className="text-cyan-400 italic">Click to inspect</span>
          </div>
        </div>
      )}

      <GraphViewport
        viewWidth={960}
        viewHeight={580}
        zoom={zoom}
        setZoom={setZoom}
        pan={pan}
        setPan={setPan}
      >
        {/* DEFINE SVG ARROW MARKERS & GLOW FILTERS */}
        <defs>
          <filter id="cyan-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="crimson-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* DRAW CURVED EDGES */}
        {visibleEdges.map((e, i) => {
          const p1 = positions[e.source];
          const p2 = positions[e.target];
          if (!p1 || !p2) return null;

          const edgeKey = `${e.source}->${e.target}`;
          const isHighlighted = connectedNeighbors?.edges.has(edgeKey);
          const isDimmed = connectedNeighbors && !isHighlighted;

          // Compute gentle curved control point
          const midX = (p1.x + p2.x) / 2;
          const midY = (p1.y + p2.y) / 2;
          const dx = p2.x - p1.x;
          const dy = p2.y - p1.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const curvature = 0.15;
          const cx = midX - (dy / dist) * (dist * curvature);
          const cy = midY + (dx / dist) * (dist * curvature);

          const weightRatio = e.amount / maxEdgeAmount;
          const strokeWidth = isHighlighted ? 3 : Math.max(0.8, weightRatio * 4.5);
          const strokeOpacity = isDimmed ? 0.05 : isHighlighted ? 0.95 : 0.25 + 0.5 * weightRatio;
          const strokeColor = isHighlighted ? "#38bdf8" : weightRatio > 0.4 ? "#f43f5e" : "#e11d48";

          return (
            <g key={i}>
              <path
                d={`M ${p1.x},${p1.y} Q ${cx},${cy} ${p2.x},${p2.y}`}
                fill="none"
                stroke={strokeColor}
                strokeWidth={strokeWidth}
                strokeOpacity={strokeOpacity}
                filter={isHighlighted ? "url(#cyan-glow)" : undefined}
                className="transition-all duration-150"
              />
              {/* Invisible wide hit-area for clicking */}
              <path
                d={`M ${p1.x},${p1.y} Q ${cx},${cy} ${p2.x},${p2.y}`}
                fill="none"
                stroke="transparent"
                strokeWidth={14}
                className="cursor-pointer"
                onClick={() => onEdgeClick(e.source, e.target)}
              >
                <title>{`${e.source} → ${e.target} : ${fmtMoney(e.amount)}`}</title>
              </path>
            </g>
          );
        })}

        {/* DRAW NODES */}
        {activeNodes.map((node) => {
          const p = positions[node.id];
          if (!p) return null;

          const isHovered = hoveredNode === node.id;
          const isConnected = connectedNeighbors?.nodes.has(node.id);
          const isDimmed = connectedNeighbors && !isConnected;
          const isSearched = searchQuery && node.id.toLowerCase().includes(searchQuery.toLowerCase());
          const isHub = topHubIds.has(node.id);
          const shouldShowLabel = showAllLabels || isHovered || isSearched || isHub;

          const isAccount = node.kind === "account";
          const nodeColor = isAccount ? "#06b6d4" : "#a855f7";
          const fillColor = isSearched ? "#facc15" : isHovered ? "#38bdf8" : isAccount ? "#0f172a" : "#1e1b4b";
          const strokeColor = isSearched ? "#facc15" : isHovered ? "#38bdf8" : isAccount ? "#06b6d4" : "#a855f7";

          return (
            <g
              key={node.id}
              transform={`translate(${p.x}, ${p.y})`}
              className="cursor-pointer transition-all duration-150"
              opacity={isDimmed ? 0.15 : 1}
              onMouseEnter={() => setHoveredNode(node.id)}
              onMouseLeave={() => setHoveredNode(null)}
              onClick={() => onNodeClick(node.id, node.kind)}
            >
              {/* Node Outer Halo on Hub or Hover */}
              {(isHovered || isHub || isSearched) && (
                <circle
                  r={p.r + 6}
                  fill="none"
                  stroke={strokeColor}
                  strokeWidth={1.5}
                  strokeDasharray={isSearched ? "2 2" : undefined}
                  className="animate-pulse"
                />
              )}

              {/* Node Body */}
              <circle
                r={p.r}
                fill={fillColor}
                stroke={strokeColor}
                strokeWidth={isHovered ? 3 : 2}
                filter={isHovered ? "url(#cyan-glow)" : undefined}
              />

              {/* Node Center Glyph */}
              <circle r={p.r * 0.4} fill={strokeColor} />

              {/* Smart Adaptive Text Label (Rendered only on Hubs, Hover, Search, or when toggled) */}
              {shouldShowLabel && (
                <g transform={`translate(0, ${p.r + 12})`}>
                  {/* Label Background Badge */}
                  <rect
                    x={-42}
                    y={-8}
                    width={84}
                    height={16}
                    rx={4}
                    fill="#020617"
                    fillOpacity={0.9}
                    stroke={isHovered ? "#38bdf8" : "#334155"}
                    strokeWidth={1}
                  />
                  <text
                    x={0}
                    y={3}
                    textAnchor="middle"
                    fontSize="9"
                    fontWeight={isHovered || isHub ? "bold" : "normal"}
                    fill={isHovered ? "#38bdf8" : isSearched ? "#facc15" : "#e2e8f0"}
                    className="font-mono pointer-events-none select-none"
                  >
                    {node.id.length > 10 ? `${node.id.slice(0, 9)}…` : node.id}
                  </text>
                </g>
              )}
            </g>
          );
        })}
      </GraphViewport>
    </div>
  );
});

// ---------------------------------------------------------------------------
// ACCOUNTS <-> PHONES BIPARTITE GRAPH (CLUSTERED & READABLE)
// ---------------------------------------------------------------------------
const LinkGraphView = React.memo(function LinkGraphView({
  graph,
  onNodeClick,
  onEdgeClick,
  searchQuery = "",
  maxEntities = 40,
}: {
  graph: MoneyGraph;
  onNodeClick: (id: string, kind?: string) => void;
  onEdgeClick: (a: string, b: string) => void;
  searchQuery?: string;
  maxEntities?: number;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Filter accounts and phones with degree counts
  const { accounts, phones, edges } = useMemo(() => {
    const rawAccounts = (graph.nodes || []).filter((n) => n.kind === "account");
    const rawPhones = (graph.nodes || []).filter((n) => n.kind !== "account");

    const edgeCount: Record<string, number> = {};
    for (const e of graph.edges || []) {
      edgeCount[e.source] = (edgeCount[e.source] || 0) + 1;
      edgeCount[e.target] = (edgeCount[e.target] || 0) + 1;
    }

    // Sort by degree to show the most connected mule nodes first
    const sortedAccounts = [...rawAccounts].sort(
      (a, b) => (edgeCount[b.id] || 0) - (edgeCount[a.id] || 0)
    ).slice(0, Math.floor(maxEntities / 2));

    const sortedPhones = [...rawPhones].sort(
      (a, b) => (edgeCount[b.id] || 0) - (edgeCount[a.id] || 0)
    ).slice(0, Math.floor(maxEntities / 2));

    const activeAccSet = new Set(sortedAccounts.map((a) => a.id));
    const activePhSet = new Set(sortedPhones.map((p) => p.id));

    const filteredEdges = (graph.edges || []).filter(
      (e) => (activeAccSet.has(e.source) && activePhSet.has(e.target)) ||
             (activePhSet.has(e.source) && activeAccSet.has(e.target))
    );

    return { accounts: sortedAccounts, phones: sortedPhones, edges: filteredEdges };
  }, [graph.nodes, graph.edges, maxEntities]);

  // Positions with generous vertical spacing (at least 28px per node)
  const positions = useMemo(() => {
    const pos: Record<string, { x: number; y: number; kind: string }> = {};
    const accHeight = accounts.length * 28;
    const phHeight = phones.length * 28;

    accounts.forEach((node, i) => {
      pos[node.id] = {
        x: -260,
        y: -accHeight / 2 + i * 28,
        kind: "account",
      };
    });

    phones.forEach((node, i) => {
      pos[node.id] = {
        x: 260,
        y: -phHeight / 2 + i * 28,
        kind: "phone",
      };
    });

    return pos;
  }, [accounts, phones]);

  // Neighbor highlighting
  const connectedNeighbors = useMemo(() => {
    if (!hoveredNode) return null;
    const neighbors = new Set<string>([hoveredNode]);
    const edgeSet = new Set<string>();
    for (const e of edges) {
      if (e.source === hoveredNode) {
        neighbors.add(e.target);
        edgeSet.add(`${e.source}<->${e.target}`);
      } else if (e.target === hoveredNode) {
        neighbors.add(e.source);
        edgeSet.add(`${e.source}<->${e.target}`);
      }
    }
    return { nodes: neighbors, edges: edgeSet };
  }, [hoveredNode, edges]);

  return (
    <GraphViewport
      viewWidth={960}
      viewHeight={580}
      zoom={zoom}
      setZoom={setZoom}
      pan={pan}
      setPan={setPan}
    >
      {/* COLUMN HEADERS */}
      <g transform="translate(-260, -260)">
        <rect x={-80} y={-14} width={160} height={28} rx={6} fill="#082f49" stroke="#0284c7" strokeWidth={1} />
        <text x={0} y={4} textAnchor="middle" fontSize="11" fontWeight="bold" fill="#38bdf8" className="font-mono select-none">
          BANK ACCOUNTS ({accounts.length})
        </text>
      </g>

      <g transform="translate(260, -260)">
        <rect x={-80} y={-14} width={160} height={28} rx={6} fill="#3b0764" stroke="#9333ea" strokeWidth={1} />
        <text x={0} y={4} textAnchor="middle" fontSize="11" fontWeight="bold" fill="#c084fc" className="font-mono select-none">
          PHONE SUBSCRIBERS ({phones.length})
        </text>
      </g>

      {/* DRAW BEZIER LINK LINES */}
      {edges.map((e, i) => {
        const p1 = positions[e.source];
        const p2 = positions[e.target];
        if (!p1 || !p2) return null;

        const isHighlighted =
          connectedNeighbors?.edges.has(`${e.source}<->${e.target}`) ||
          connectedNeighbors?.edges.has(`${e.target}<->${e.source}`);
        const isDimmed = connectedNeighbors && !isHighlighted;

        return (
          <g key={i}>
            <path
              d={`M ${p1.x},${p1.y} C ${(p1.x + p2.x) / 3},${p1.y} ${(p1.x + p2.x) * 2 / 3},${p2.y} ${p2.x},${p2.y}`}
              fill="none"
              stroke={isHighlighted ? "#38bdf8" : "#6366f1"}
              strokeWidth={isHighlighted ? 2.5 : 1}
              strokeOpacity={isDimmed ? 0.05 : isHighlighted ? 0.9 : 0.3}
              className="transition-all duration-150"
            />
            <path
              d={`M ${p1.x},${p1.y} C ${(p1.x + p2.x) / 3},${p1.y} ${(p1.x + p2.x) * 2 / 3},${p2.y} ${p2.x},${p2.y}`}
              fill="none"
              stroke="transparent"
              strokeWidth={10}
              className="cursor-pointer"
              onClick={() => onEdgeClick(e.source, e.target)}
            >
              <title>{`${e.source} ↔ ${e.target} link`}</title>
            </path>
          </g>
        );
      })}

      {/* DRAW LEFT COLUMN (ACCOUNTS) */}
      {accounts.map((node) => {
        const p = positions[node.id];
        if (!p) return null;

        const isHovered = hoveredNode === node.id;
        const isConnected = connectedNeighbors?.nodes.has(node.id);
        const isDimmed = connectedNeighbors && !isConnected;
        const isSearched = searchQuery && node.id.toLowerCase().includes(searchQuery.toLowerCase());

        return (
          <g
            key={node.id}
            transform={`translate(${p.x}, ${p.y})`}
            className="cursor-pointer transition-all duration-150"
            opacity={isDimmed ? 0.15 : 1}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
            onClick={() => onNodeClick(node.id, "account")}
          >
            {/* Account Card Badge */}
            <rect
              x={-110}
              y={-10}
              width={120}
              height={20}
              rx={4}
              fill={isHovered ? "#082f49" : "#0f172a"}
              stroke={isHovered ? "#38bdf8" : isSearched ? "#facc15" : "#0284c7"}
              strokeWidth={isHovered ? 1.8 : 1}
            />
            <circle cx={15} cy={0} r={5} fill={isHovered ? "#38bdf8" : "#06b6d4"} />
            <text
              x={-50}
              y={3.5}
              textAnchor="middle"
              fontSize="9"
              fontWeight="bold"
              fill={isHovered ? "#38bdf8" : "#e2e8f0"}
              className="font-mono pointer-events-none select-none"
            >
              {node.id.length > 13 ? `${node.id.slice(0, 12)}…` : node.id}
            </text>
          </g>
        );
      })}

      {/* DRAW RIGHT COLUMN (PHONES) */}
      {phones.map((node) => {
        const p = positions[node.id];
        if (!p) return null;

        const isHovered = hoveredNode === node.id;
        const isConnected = connectedNeighbors?.nodes.has(node.id);
        const isDimmed = connectedNeighbors && !isConnected;
        const isSearched = searchQuery && node.id.toLowerCase().includes(searchQuery.toLowerCase());

        return (
          <g
            key={node.id}
            transform={`translate(${p.x}, ${p.y})`}
            className="cursor-pointer transition-all duration-150"
            opacity={isDimmed ? 0.15 : 1}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
            onClick={() => onNodeClick(node.id, "phone")}
          >
            {/* Phone Card Badge */}
            <circle cx={-15} cy={0} r={5} fill={isHovered ? "#c084fc" : "#a855f7"} />
            <rect
              x={-10}
              y={-10}
              width={120}
              height={20}
              rx={4}
              fill={isHovered ? "#3b0764" : "#1e1b4b"}
              stroke={isHovered ? "#c084fc" : isSearched ? "#facc15" : "#9333ea"}
              strokeWidth={isHovered ? 1.8 : 1}
            />
            <text
              x={50}
              y={3.5}
              textAnchor="middle"
              fontSize="9"
              fontWeight="bold"
              fill={isHovered ? "#c084fc" : "#e2e8f0"}
              className="font-mono pointer-events-none select-none"
            >
              {node.id.length > 13 ? `${node.id.slice(0, 12)}…` : node.id}
            </text>
          </g>
        );
      })}
    </GraphViewport>
  );
});

// ---------------------------------------------------------------------------
// CALL NETWORK VIEW (EGO NET)
// ---------------------------------------------------------------------------
const CallGraphView = React.memo(function CallGraphView({
  graph,
  onNodeClick,
  onEdgeClick,
  searchQuery = "",
}: {
  graph: EgoNet;
  onNodeClick: (id: string) => void;
  onEdgeClick: (a: string, b: string) => void;
  searchQuery?: string;
}) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const nodes = graph.nodes || [];
  const center = graph.node;
  const positions: Record<string, { x: number; y: number }> = { [center]: { x: 0, y: 0 } };
  const n = nodes.length;

  nodes.forEach((node, i) => {
    const angle = (i / Math.max(n, 1)) * 2 * Math.PI - Math.PI / 2;
    const r = 210;
    positions[node.id] = { x: Math.cos(angle) * r, y: Math.sin(angle) * r };
  });

  return (
    <GraphViewport
      viewWidth={960}
      viewHeight={580}
      zoom={zoom}
      setZoom={setZoom}
      pan={pan}
      setPan={setPan}
    >
      {/* EDGES */}
      {graph.edges.map((e, i) => {
        const p1 = positions[e.source];
        const p2 = positions[e.target];
        if (!p1 || !p2) return null;

        const isHighlighted = hoveredNode === e.source || hoveredNode === e.target;
        return (
          <g key={i}>
            <line
              x1={p1.x}
              y1={p1.y}
              x2={p2.x}
              y2={p2.y}
              stroke={isHighlighted ? "#38bdf8" : "#10b981"}
              strokeOpacity={isHighlighted ? 0.9 : Math.min(1, Math.max(0.2, e.weight / 15))}
              strokeWidth={isHighlighted ? 3 : Math.min(5, Math.max(1, e.weight / 4))}
            />
            <line
              x1={p1.x}
              y1={p1.y}
              x2={p2.x}
              y2={p2.y}
              stroke="transparent"
              strokeWidth={12}
              className="cursor-pointer"
              onClick={() => onEdgeClick(e.source, e.target)}
            >
              <title>{`${e.weight} calls between ${e.source} and ${e.target}`}</title>
            </line>
          </g>
        );
      })}

      {/* CENTER NODE */}
      <g
        transform="translate(0, 0)"
        className="cursor-pointer"
        onClick={() => onNodeClick(center)}
        onMouseEnter={() => setHoveredNode(center)}
        onMouseLeave={() => setHoveredNode(null)}
      >
        <circle r={22} fill="#064e3b" stroke="#10b981" strokeWidth={3} className="animate-pulse" />
        <circle r={8} fill="#34d399" />
        <g transform="translate(0, 30)">
          <rect x={-55} y={-8} width={110} height={16} rx={4} fill="#020617" stroke="#10b981" strokeWidth={1} />
          <text x={0} y={3} textAnchor="middle" fontSize="9" fontWeight="bold" fill="#34d399" className="font-mono">
            {center} (TARGET)
          </text>
        </g>
      </g>

      {/* PERIPHERAL CONTACT NODES */}
      {nodes.map((node) => {
        const p = positions[node.id];
        if (!p || node.id === center) return null;

        const isHovered = hoveredNode === node.id;
        const stroke = riskColor(node.risk);
        const r = Math.min(18, 10 + (node.degree ?? 0) * 0.5);

        return (
          <g
            key={node.id}
            transform={`translate(${p.x}, ${p.y})`}
            className="cursor-pointer transition-transform duration-150"
            onClick={() => onNodeClick(node.id)}
            onMouseEnter={() => setHoveredNode(node.id)}
            onMouseLeave={() => setHoveredNode(null)}
          >
            <circle r={r} fill="#0f172a" stroke={stroke} strokeWidth={isHovered ? 3 : 2} />
            <circle r={r * 0.4} fill={stroke} />
            <g transform={`translate(0, ${r + 11})`}>
              <rect x={-45} y={-7} width={90} height={14} rx={3} fill="#020617" stroke={stroke} strokeWidth={0.8} />
              <text x={0} y={3} textAnchor="middle" fontSize="8" fontWeight={isHovered ? "bold" : "normal"} fill="#e2e8f0" className="font-mono">
                {node.id.length > 11 ? `${node.id.slice(0, 10)}…` : node.id}
              </text>
            </g>
          </g>
        );
      })}
    </GraphViewport>
  );
});

// ---------------------------------------------------------------------------
// MAIN NETWORK SECTION
// ---------------------------------------------------------------------------
export const NetworkSection = React.memo(function NetworkSection() {
  const { isGraphReady, pipeline } = usePipeline();
  const [tab, setTab] = useState<Tab>("money");
  const [phones, setPhones] = useState<PhoneProfile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [mode, setMode] = useState<"evidence" | "full">("evidence");
  const [graph, setGraph] = useState<EgoNet | null>(null);
  const [moneyGraph, setMoneyGraph] = useState<MoneyGraph | null>(null);
  const [linkGraph, setLinkGraph] = useState<MoneyGraph | null>(null);
  const [hits, setHits] = useState<{ phone: string; account_no: string; txn_date: string; mode: string; amount: number; phone_cdr_records: number; window_count: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [panel, setPanel] = useState<PanelPayload | null>(null);
  const [panelBusy, setPanelBusy] = useState(false);
  const [cycleItems, setCycleItems] = useState<OrbitItem[]>([]);
  const [cycleVisible, setCycleVisible] = useState(false);
  const [cycleReplay, setCycleReplay] = useState(0);

  // Forensic Filter States
  const [minAmount, setMinAmount] = useState<number>(0);
  const [maxNodes, setMaxNodes] = useState<number>(60);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [showAllLabels, setShowAllLabels] = useState<boolean>(false);

  const networkCacheRef = useRef<Map<string, any>>(new Map());

  const clearNetworkFilter = () => {
    setMinAmount(0);
    setSearchQuery("");
  };

  const revealCycle = useCallback((g: MoneyGraph) => {
    const cycle = findCycle(g);
    if (cycle.length === 0) return;
    setCycleItems(
      cycle.map((id, i) => ({
        id,
        label: id.length > 12 ? `${id.slice(0, 12)}…` : id,
        accent: ["#f43f5e", "#fb923c", "#facc15", "#a78bfa", "#38bdf8"][i % 5],
      }))
    );
    setCycleReplay((k) => k + 1);
    setCycleVisible(true);
  }, []);

  const openEntity = useCallback((kind: string, value: string) => {
    if (!value) return;
    setPanelBusy(true);
    setPanel(null);
    api
      .dossier(kind, value)
      .then((info) => setPanel({ type: "entity", info }))
      .catch((e) => {
        if (e.status !== 409) toast.error(`No evidence card for ${kind} ${value}.`);
      })
      .finally(() => setPanelBusy(false));
  }, []);

  const openRelationship = useCallback((a: string, b: string) => {
    if (!a || !b) return;
    setPanelBusy(true);
    setPanel(null);
    api
      .relationship(a, b)
      .then((rel) => setPanel({ type: "relationship", rel }))
      .catch((e) => {
        if (e.status !== 409) toast.error("Failed to load relationship.");
      })
      .finally(() => setPanelBusy(false));
  }, []);

  const loadTab = useCallback(
    (t: Tab, phone?: string, graphMode?: "evidence" | "full") => {
      const activeMode = graphMode || mode;
      const cacheKey = `${t}:${phone || "all"}:${activeMode}`;
      if (networkCacheRef.current.has(cacheKey)) {
        const cached = networkCacheRef.current.get(cacheKey);
        if (t === "calls") setGraph(cached);
        else if (t === "money") { setMoneyGraph(cached); revealCycle(cached); }
        else if (t === "link") setLinkGraph(cached);
        else if (t === "coincidence") setHits(cached);
        setLoading(false);
        return;
      }

      setLoading(true);
      const loaders: Record<Tab, () => Promise<unknown>> = {
        calls: () =>
          phone
            ? api.egonet(phone, 1, activeMode).then((g) => {
                networkCacheRef.current.set(cacheKey, g);
                setGraph(g);
              })
            : Promise.resolve(),
        money: () =>
          api.moneyGraph(0, 500).then((g) => {
            networkCacheRef.current.set(cacheKey, g);
            setMoneyGraph(g);
            revealCycle(g);
          }),
        link: () =>
          api.accountPhoneGraph(300).then((g) => {
            networkCacheRef.current.set(cacheKey, g);
            setLinkGraph(g);
          }),
        coincidence: () =>
          api.coincidence(3600, 100).then((r) => {
            networkCacheRef.current.set(cacheKey, r.hits);
            setHits(r.hits);
          }),
      };

      loaders[t]()
        .catch((e) => {
          if (e.status !== 409 && e.status !== 425) {
            toast.error(t === "calls" ? "Failed to load network graph." : "Failed to load graph.");
          }
        })
        .finally(() => setLoading(false));
    },
    [mode, revealCycle]
  );

  useEffect(() => {
    if (!isGraphReady && !pipeline?.dataset_id) {
      setLoading(false);
      return;
    }
    api
      .phones(0, 100)
      .then((res) => {
        setPhones(res.phones || []);
        if (res.phones && res.phones.length > 0) {
          const top = res.phones[0].phone;
          setSelected(top);
        }
        loadTab("money");
      })
      .catch((e) => {
        if (e.status !== 409 && e.status !== 425) toast.error("Failed to load phones.");
      })
      .finally(() => setLoading(false));
  }, [pipeline?.dataset_id, isGraphReady]);

  const switchTab = (t: Tab) => {
    setTab(t);
    loadTab(t, selected ?? undefined, mode);
  };

  const loadEgo = (phone: string) => {
    setSelected(phone);
    setTab("calls");
    loadTab("calls", phone, mode);
  };

  const nodeKindOf = (id: string, kind?: string): string => {
    if (kind === "account") return "account";
    if (kind === "device") return "imei";
    if (kind === "ip") return "ip";
    if (kind === "phone") return "phone";
    if (id.includes("@")) return "upi";
    if (/^\d{10,}$/.test(id.replace(/\D/g, ""))) return "phone";
    return "account";
  };

  const tabs: { id: Tab; label: string; icon: React.ElementType }[] = [
    { id: "money", label: "Money Flow Matrix", icon: Landmark },
    { id: "link", label: "Accounts ↔ Phones", icon: GitFork },
    { id: "calls", label: "Call Network", icon: Phone },
    { id: "coincidence", label: "Temporal Correlations", icon: Crosshair },
  ];

  return (
    <div className="space-y-6">
      <Card className="bg-card/45 backdrop-blur border-border/80">
        <CardHeader className="flex flex-col sm:flex-row justify-between sm:items-center gap-4 border-b border-border/60 pb-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <Badge variant="outline" className="text-[10px] font-mono tracking-widest text-cyan-400 border-cyan-500/30 uppercase bg-cyan-950/40">
                GRAPH TOPOLOGY INTELLIGENCE
              </Badge>
            </div>
            <CardTitle className="text-xl font-bold font-mono uppercase tracking-wide flex items-center gap-2">
              <Network className="h-5 w-5 text-cyan-400" />
              Investigation Network Graph
            </CardTitle>
            <CardDescription className="text-xs font-mono">
              Clustered force topology · Smart entity focus · Min-amount flow filters · Interactive zoom &amp; pan
            </CardDescription>
          </div>

          {/* TAB BUTTONS */}
          <div className="flex items-center gap-1.5 flex-wrap font-mono text-xs">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => switchTab(t.id)}
                className={`flex items-center gap-2 px-3.5 py-1.5 rounded-lg font-semibold transition-all ${
                  tab === t.id
                    ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/40 border border-transparent"
                }`}
              >
                <t.icon className="w-3.5 h-3.5" />
                <span>{t.label}</span>
              </button>
            ))}
          </div>
        </CardHeader>

        <CardContent className="pt-4 space-y-4">
          {/* FORENSIC CONTROL TOOLBAR */}
          {(tab === "money" || tab === "link") && (
            <div className="flex flex-wrap items-center justify-between gap-3 p-2.5 bg-slate-950/60 border border-border/70 rounded-xl font-mono text-xs">
              <div className="flex items-center gap-2 flex-wrap">
                {/* Search Input */}
                <div className="relative">
                  <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
                  <Input
                    placeholder="Search node or phone..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="h-8 pl-8 pr-7 text-xs font-mono bg-slate-900 border-border/80 w-48 text-slate-200"
                  />
                  {searchQuery && (
                    <button
                      onClick={() => setSearchQuery("")}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                {/* Min Amount Filter (For Money Flow) */}
                {tab === "money" && (
                  <Select value={minAmount.toString()} onValueChange={(v) => setMinAmount(Number(v))}>
                    <SelectTrigger className="h-8 w-36 text-xs bg-slate-900 border-border/80 font-mono text-slate-200">
                      <SelectValue placeholder="Min Amount" />
                    </SelectTrigger>
                    <SelectContent className="font-mono text-xs">
                      <SelectItem value="0">All Flows (≥ ₹0)</SelectItem>
                      <SelectItem value="10000">≥ ₹10,000</SelectItem>
                      <SelectItem value="50000">≥ ₹50,000 (Smurf)</SelectItem>
                      <SelectItem value="100000">≥ ₹1,00,000</SelectItem>
                      <SelectItem value="500000">≥ ₹5,00,000 (CTR)</SelectItem>
                    </SelectContent>
                  </Select>
                )}

                {/* Max Entities Limit */}
                <Select value={maxNodes.toString()} onValueChange={(v) => setMaxNodes(Number(v))}>
                  <SelectTrigger className="h-8 w-32 text-xs bg-slate-900 border-border/80 font-mono text-slate-200">
                    <SelectValue placeholder="Max Nodes" />
                  </SelectTrigger>
                  <SelectContent className="font-mono text-xs">
                    <SelectItem value="30">Top 30 Nodes</SelectItem>
                    <SelectItem value="60">Top 60 Nodes</SelectItem>
                    <SelectItem value="100">Top 100 Nodes</SelectItem>
                    <SelectItem value="200">Top 200 Nodes</SelectItem>
                  </SelectContent>
                </Select>

                {/* Toggle All Labels */}
                {tab === "money" && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowAllLabels(!showAllLabels)}
                    className={`h-8 font-mono text-xs border-border/80 ${
                      showAllLabels ? "bg-cyan-950 text-cyan-300 border-cyan-600/50" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    {showAllLabels ? <Eye className="w-3.5 h-3.5 mr-1.5 text-cyan-400" /> : <EyeOff className="w-3.5 h-3.5 mr-1.5" />}
                    {showAllLabels ? "Labels: All" : "Labels: Smart"}
                  </Button>
                )}
              </div>

              {/* Reset Controls */}
              {(minAmount > 0 || searchQuery) && (
                <button
                  onClick={clearNetworkFilter}
                  className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1"
                >
                  <X className="w-3 h-3" /> Reset Filters
                </button>
              )}
            </div>
          )}

          {/* TAB 1: MONEY FLOW GRAPH */}
          {tab === "money" && (
            <div className="relative flex flex-col items-center justify-center min-h-[500px]">
              {loading && (
                <div className="flex flex-col items-center gap-2 py-16">
                  <RotateCw className="w-8 h-8 animate-spin text-cyan-400" />
                  <p className="text-xs text-muted-foreground font-mono animate-pulse">Computing Clustered Money Flows...</p>
                </div>
              )}
              {!loading && !moneyGraph && (
                <p className="text-muted-foreground font-mono text-xs">No money-flow graph available.</p>
              )}
              {!loading && moneyGraph && (
                <>
                  <MoneyGraphView
                    graph={moneyGraph}
                    onNodeClick={(id, kind) => openEntity(nodeKindOf(id, kind), id)}
                    onEdgeClick={openRelationship}
                    minAmount={minAmount}
                    searchQuery={searchQuery}
                    showAllLabels={showAllLabels}
                    maxNodes={maxNodes}
                  />

                  {/* Graph Stats Bar */}
                  <div className="w-full flex flex-wrap items-center justify-between gap-4 mt-2 px-1 text-xs font-mono text-slate-400">
                    <div className="flex items-center gap-4">
                      <span>Rendered: <b className="text-cyan-400">{Math.min(maxNodes, moneyGraph.stats.nodes)}</b> / {moneyGraph.stats.nodes} nodes</span>
                      <span>Links: <b className="text-slate-200">{moneyGraph.stats.edges}</b> flows</span>
                      {minAmount > 0 && <Badge variant="outline" className="text-[10px] text-amber-400 border-amber-800">Flows ≥ {fmtMoney(minAmount)}</Badge>}
                    </div>

                    <div className="flex items-center gap-3 text-[11px]">
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-cyan-400 inline-block" /> Bank Account</span>
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-purple-400 inline-block" /> Counterparty</span>
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" /> High Flow Conduits</span>
                    </div>
                  </div>
                </>
              )}

              {/* Radial intro for detected circular loop */}
              {cycleVisible && cycleItems.length > 0 && (
                <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 rounded-xl bg-background/80 backdrop-blur-md">
                  <RadialIntro
                    items={cycleItems}
                    stageSize={340}
                    chipSize={64}
                    duration={26}
                    replayKey={cycleReplay}
                  />
                  <div className="text-center">
                    <p className="font-mono text-xs uppercase tracking-[0.3em] text-rose-400 font-bold">
                      Circular Laundering Loop Discovered
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground font-mono">
                      {cycleItems.length} accounts in a closed circular cycling path ($A \rightarrow B \rightarrow C \rightarrow A$)
                    </p>
                    <button
                      onClick={() => setCycleVisible(false)}
                      className="mt-3 rounded-lg border border-border bg-card/90 px-3.5 py-1.5 text-xs text-cyan-300 font-mono transition-colors hover:bg-cyan-950"
                    >
                      View Clustered Graph
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: ACCOUNTS <-> PHONES BIPARTITE GRAPH */}
          {tab === "link" && (
            <div className="flex flex-col items-center justify-center min-h-[500px]">
              {loading && (
                <div className="flex flex-col items-center gap-2 py-16">
                  <RotateCw className="w-8 h-8 animate-spin text-purple-400" />
                  <p className="text-xs text-muted-foreground font-mono animate-pulse">Mapping Shared Accounts &amp; Phone Lines...</p>
                </div>
              )}
              {!loading && !linkGraph && (
                <p className="text-muted-foreground font-mono text-xs">No account–phone links found.</p>
              )}
              {!loading && linkGraph && (
                <>
                  <LinkGraphView
                    graph={linkGraph}
                    onNodeClick={(id, kind) => openEntity(nodeKindOf(id, kind), id)}
                    onEdgeClick={openRelationship}
                    searchQuery={searchQuery}
                    maxEntities={maxNodes}
                  />
                  <div className="w-full flex items-center justify-between mt-2 px-1 text-xs font-mono text-slate-400">
                    <p>Accounts mapped to shared telecom SIM cards &amp; IPDR mobile numbers</p>
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-cyan-500 inline-block" /> Bank Account</span>
                      <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded bg-purple-500 inline-block" /> Phone / MSISDN</span>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {/* TAB 3: CALL NETWORK EGO-NET */}
          {tab === "calls" && (
            <div className="flex flex-col items-center gap-4">
              <div className="flex items-center gap-2 w-full max-w-2xl flex-wrap justify-center font-mono">
                <Select value={selected || ""} onValueChange={loadEgo} disabled={loading || phones.length === 0}>
                  <SelectTrigger className="w-64 text-xs font-mono bg-slate-900 border-border/80">
                    <SelectValue placeholder="Select target phone" />
                  </SelectTrigger>
                  <SelectContent className="font-mono text-xs">
                    {phones.map((p) => (
                      <SelectItem key={p.phone} value={p.phone}>
                        {p.phone} · {p.records} calls
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <div className="flex items-center rounded-lg border border-border p-0.5 text-xs bg-slate-900">
                  <button
                    onClick={() => { setMode("evidence"); if (selected) loadTab("calls", selected, "evidence"); }}
                    className={`flex items-center gap-1 rounded-md px-2.5 py-1.5 font-medium transition-colors ${
                      mode === "evidence" ? "bg-emerald-500/20 text-emerald-400 font-bold" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    <Filter className="h-3.5 w-3.5" />
                    Evidence
                  </button>
                  <button
                    onClick={() => { setMode("full"); if (selected) loadTab("calls", selected, "full"); }}
                    className={`flex items-center gap-1 rounded-md px-2.5 py-1.5 font-medium transition-colors ${
                      mode === "full" ? "bg-emerald-500/20 text-emerald-400 font-bold" : "text-slate-400 hover:text-slate-200"
                    }`}
                  >
                    Full
                  </button>
                </div>
                <button
                  onClick={() => selected && loadEgo(selected)}
                  className="p-2 rounded-lg border border-border text-slate-400 hover:text-slate-200 transition-colors bg-slate-900"
                  title="Refresh"
                >
                  <RotateCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
                </button>
              </div>

              <div className="flex flex-col items-center justify-center min-h-[460px] w-full">
                {loading && <p className="text-muted-foreground font-mono text-xs animate-pulse">Loading phone ego network...</p>}
                {!loading && !graph && (
                  <p className="text-muted-foreground font-mono text-xs">No network data. Run the ingestion pipeline first.</p>
                )}
                {!loading && graph && (
                  <>
                    <CallGraphView
                      graph={graph}
                      onNodeClick={(id) => openEntity("phone", id)}
                      onEdgeClick={openRelationship}
                      searchQuery={searchQuery}
                    />
                    <div className="mt-2 space-y-1 text-center font-mono text-xs text-slate-400">
                      <p>
                        Target: <b className="text-emerald-400">{graph.node}</b> · {graph.nodes.length} contacts · {graph.edges.length} call links
                      </p>
                    </div>
                  </>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: TEMPORAL CORRELATIONS TABLE */}
          {tab === "coincidence" && (
            <div className="min-h-[460px] p-2 space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 font-mono">
                <div className="bg-slate-950/60 border border-border/80 p-4 rounded-xl flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-emerald-400 font-bold">
                    <Crosshair className="w-4 h-4" />
                    <h3 className="text-xs uppercase tracking-wide">Temporal Overlaps</h3>
                  </div>
                  <p className="text-[11px] text-muted-foreground">Bank ↔ Telecom calls within $\le 15$ min</p>
                  <div className="text-2xl font-bold text-emerald-400 mt-auto">{hits.length}</div>
                </div>

                <div className="bg-slate-950/60 border border-border/80 p-4 rounded-xl flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-purple-400 font-bold">
                    <GitFork className="w-4 h-4" />
                    <h3 className="text-xs uppercase tracking-wide">Cross-Domain Overlap</h3>
                  </div>
                  <p className="text-[11px] text-muted-foreground">Multi-account phone links</p>
                  <div className="text-2xl font-bold text-purple-400 mt-auto">Active</div>
                </div>

                <div className="bg-slate-950/60 border border-border/80 p-4 rounded-xl flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-rose-400 font-bold">
                    <Smartphone className="w-4 h-4" />
                    <h3 className="text-xs uppercase tracking-wide">Shared Hardware</h3>
                  </div>
                  <p className="text-[11px] text-muted-foreground">IMEI &amp; IP multi-subscriber clusters</p>
                  <div className="text-2xl font-bold text-rose-400 mt-auto">Monitored</div>
                </div>

                <div className="bg-slate-950/60 border border-border/80 p-4 rounded-xl flex flex-col gap-2">
                  <div className="flex items-center gap-2 text-amber-400 font-bold">
                    <Landmark className="w-4 h-4" />
                    <h3 className="text-xs uppercase tracking-wide">Money Flow Links</h3>
                  </div>
                  <p className="text-[11px] text-muted-foreground">Inter-bank transfer conduits</p>
                  <div className="text-2xl font-bold text-amber-400 mt-auto">{moneyGraph?.edges.length ?? 0} links</div>
                </div>
              </div>

              <div className="bg-slate-950/40 border border-border/70 rounded-xl p-4 font-mono">
                <h3 className="text-xs font-bold uppercase mb-4 flex items-center gap-2 text-cyan-400">
                  <Crosshair className="w-4 h-4" />
                  Statistically Meaningful Temporal Coincidence Ledger
                </h3>
                {loading && <p className="text-muted-foreground animate-pulse py-4 text-center text-xs">Correlating timeline...</p>}
                {!loading && hits.length === 0 && (
                  <p className="text-muted-foreground py-6 text-center text-xs">
                    No bank↔telecom coincidence windows found (≤ 60 min).
                  </p>
                )}
                {!loading && hits.length > 0 && (
                  <div className="overflow-x-auto rounded-lg border border-border/70">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-muted/60 text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border/60">
                          <th className="px-4 py-2.5 font-medium">Caller Phone</th>
                          <th className="px-4 py-2.5 font-medium">Target Account</th>
                          <th className="px-4 py-2.5 font-medium">Date &amp; Time</th>
                          <th className="px-4 py-2.5 font-medium">Mode</th>
                          <th className="px-4 py-2.5 font-medium text-right">Transfer Amount</th>
                          <th className="px-4 py-2.5 font-medium text-right">CDR Calls</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40">
                        {hits.map((h, i) => (
                          <tr
                            key={i}
                            className="hover:bg-slate-900/50 transition-colors cursor-pointer"
                            onClick={() => openEntity("phone", h.phone)}
                          >
                            <td className="px-4 py-2.5 text-emerald-400 font-bold">{h.phone}</td>
                            <td className="px-4 py-2.5 text-cyan-300 font-semibold">{h.account_no}</td>
                            <td className="px-4 py-2.5 text-slate-400">{h.txn_date}</td>
                            <td className="px-4 py-2.5 text-slate-300">{h.mode}</td>
                            <td className="px-4 py-2.5 text-right text-emerald-400 font-bold">{fmtMoney(h.amount)}</td>
                            <td className="px-4 py-2.5 text-right text-purple-400 font-semibold">{h.phone_cdr_records} calls</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <InvestigationPanel
        data={panel}
        onClose={() => setPanel(null)}
        onEntitySelect={openEntity}
      />
      {panelBusy && (
        <p className="fixed bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-cyan-500/50 bg-slate-900/90 backdrop-blur px-4 py-2 text-xs font-mono text-cyan-300 shadow-2xl animate-pulse">
          Loading forensic intelligence card...
        </p>
      )}
    </div>
  );
});
