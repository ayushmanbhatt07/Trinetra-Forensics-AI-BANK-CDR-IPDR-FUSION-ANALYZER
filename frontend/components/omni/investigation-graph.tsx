"use client";

/**
 * Premium 3D Forensic Investigation Graph
 * 
 * Uses react-force-graph-3d (Three.js under the hood) to render a stunning
 * 3D force-directed linked-transactions tree. Nodes are color-coded by type
 * (account / phone / entity), sized by centrality, and glow by risk level.
 * Edges animate particle flow along money transfer directions.
 *
 * PHASE 3 OPTIMIZATION:
 * Decouples the 3D WebGL Canvas (ForceGraph3D) from the Hover Tooltip Overlay.
 * Mouse movements across nodes update only the lightweight overlay without
 * triggering Three.js / WebGL canvas reconciliation.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Search, Loader2, AlertTriangle, Network, Shield } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api';
import { EntityDetailsOverlay } from './entity-details';

// Force-graph must be loaded client-side only (Three.js + WebGL)
const ForceGraph3D = dynamic(() => import('react-force-graph-3d'), { ssr: false });

// ─── colour palette ──────────────────────────────────────────────────────
const NODE_COLORS: Record<string, string> = {
  account: '#3b82f6',   // blue
  phone:   '#a855f7',   // purple
  txn:     '#ea580c',   // orange
  imei:    '#06b6d4',   // cyan
  ip:      '#ec4899',   // pink
  unknown: '#6b7280',   // gray
};
const EDGE_COLORS: Record<string, string> = {
  TRANSFERRED_TO: '#10b981',
  CALLED:         '#8b5cf6',
  LINKED:         '#64748b',
};

// ─── types ────────────────────────────────────────────────────────────────
interface GraphNode {
  id: string;
  kind: string;
  label: string;
  hop_distance: number;
  risk: number;
  centrality: number;
  role?: string;
  suspicion?: string;
  // force-graph internals
  x?: number;
  y?: number;
  z?: number;
  fx?: number;
  fy?: number;
  fz?: number;
}

interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
  kind: string;
  amount: number;
  duration: number;
  reason?: string;
  tx_id?: string;
  cdr_id?: string;
}

interface Insights {
  executive_summary: string;
  primary_findings: string[];
  recommended_actions: string[];
  metrics?: Record<string, number>;
}

// ─── isolated memoized 3d canvas ─────────────────────────────────────────
interface GraphCanvasProps {
  graphData: { nodes: GraphNode[]; links: GraphEdge[] };
  nodeLabel: (node: any) => string;
  nodeColor: (node: any) => string;
  nodeVal: (node: any) => number;
  linkLabel: (link: any) => string;
  linkColor: (link: any) => string;
  linkWidth: (link: any) => number;
  linkDirectionalParticles: (link: any) => number;
  linkDirectionalParticleSpeed: (link: any) => number;
  linkDirectionalParticleColor: (link: any) => string;
  onNodeClick: (node: any) => void;
  onNodeHover: (node: any) => void;
  onNodeRightClick: (node: any) => void;
  fgRef: React.RefObject<any>;
}

const GraphCanvas = React.memo(function GraphCanvas({
  graphData,
  nodeLabel,
  nodeColor,
  nodeVal,
  linkLabel,
  linkColor,
  linkWidth,
  linkDirectionalParticles,
  linkDirectionalParticleSpeed,
  linkDirectionalParticleColor,
  onNodeClick,
  onNodeHover,
  onNodeRightClick,
  fgRef,
}: GraphCanvasProps) {
  if (graphData.nodes.length === 0) return null;

  return (
    <ForceGraph3D
      ref={fgRef}
      graphData={graphData}
      nodeId="id"
      nodeLabel={nodeLabel}
      nodeColor={nodeColor}
      nodeVal={nodeVal}
      nodeOpacity={0.92}
      nodeResolution={16}
      linkSource="source"
      linkTarget="target"
      linkLabel={linkLabel}
      linkColor={linkColor}
      linkWidth={linkWidth}
      linkOpacity={0.6}
      linkDirectionalParticles={linkDirectionalParticles}
      linkDirectionalParticleSpeed={linkDirectionalParticleSpeed}
      linkDirectionalParticleColor={linkDirectionalParticleColor}
      linkDirectionalParticleWidth={2}
      linkDirectionalArrowLength={4}
      linkDirectionalArrowRelPos={1}
      linkDirectionalArrowColor={linkColor}
      linkCurvature={0.15}
      onNodeClick={onNodeClick}
      onNodeHover={onNodeHover}
      onNodeRightClick={onNodeRightClick}
      backgroundColor="rgba(0,0,0,0)"
      showNavInfo={false}
      enableNodeDrag={true}
      enableNavigationControls={true}
      warmupTicks={80}
      cooldownTicks={120}
      d3AlphaDecay={0.02}
      d3VelocityDecay={0.3}
    />
  );
});

// ─── isolated memoized hover overlay ─────────────────────────────────────
const GraphHoverOverlay = React.memo(function GraphHoverOverlay({
  node,
  color,
}: {
  node: GraphNode | null;
  color: string;
}) {
  if (!node) return null;

  return (
    <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 w-[350px] pointer-events-none transition-opacity duration-150">
      <div className="bg-slate-900/95 backdrop-blur-md p-4 rounded-xl border border-slate-700 shadow-2xl">
        <div className="flex items-center gap-3 mb-2">
          <span className="w-3 h-3 rounded-full" style={{ background: color }}></span>
          <strong className="text-sm text-slate-100 font-mono break-all">{node.label || node.id}</strong>
        </div>
        <div className="grid grid-cols-2 gap-2 mb-2">
          <div className="bg-slate-800/50 p-2 rounded">
            <p className="text-[10px] uppercase text-slate-500">Kind</p>
            <p className="text-xs text-slate-300 capitalize">{node.kind}</p>
          </div>
          <div className="bg-slate-800/50 p-2 rounded">
            <p className="text-[10px] uppercase text-slate-500">Risk / Suspicion</p>
            <p className="text-xs text-slate-300 capitalize">{node.suspicion || (node.risk > 0 ? node.risk : 'None')}</p>
          </div>
        </div>
        {node.role && (
          <div className="bg-cyan-900/20 p-2 rounded mb-1">
            <p className="text-[10px] uppercase text-cyan-500">Role</p>
            <p className="text-xs text-cyan-300">{node.role}</p>
          </div>
        )}
        <div className="bg-slate-800/50 p-2 rounded mt-1">
          <p className="text-[10px] uppercase text-slate-500">
            {node.kind === 'account' ? 'Account No' : node.kind === 'txn' ? 'Txn ID' : node.kind === 'phone' ? 'Phone No' : 'Entity ID'}
          </p>
          <p className="text-xs text-slate-300 font-mono break-all">{node.id}</p>
        </div>
        {node.centrality > 0.5 && (
          <p className="text-[10px] text-purple-400 mt-2">🔗 High Centrality Hub</p>
        )}
      </div>
    </div>
  );
});

// ─── main component ───────────────────────────────────────────────────────
export function InvestigationGraph({ initialEntity = '' }: { initialEntity?: string }) {
  const fgRef = useRef<any>(null);
  const [entityId, setEntityId] = useState(initialEntity);
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphEdge[] }>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(false);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [error, setError] = useState('');

  const loadGraph = useCallback(async (eid?: string) => {
    const target = (eid || entityId).trim();
    if (!target) return;
    setLoading(true);
    setError('');
    setInsights(null);
    setSelectedNode(null);
    try {
      const data = await api.copilotGraphBuild(target, 3);
      if (!data.found || !data.nodes?.length) {
        setGraphData({ nodes: [], links: [] });
        setError(`Entity "${target}" not found in the network.`);
        return;
      }

      // Map to force-graph format
      const nodes: GraphNode[] = data.nodes
        .filter((n: any) => n.id === target || (n.kind !== 'unknown' && n.label !== 'Unknown Entity' && !String(n.id).toLowerCase().includes('unknown')))
        .map((n: any) => ({
          id: n.id,
          kind: (n.kind || 'unknown').toLowerCase(),
          label: n.label || n.id,
          hop_distance: n.hop_distance || 0,
          risk: n.risk || 0,
          centrality: n.centrality || 0,
          role: n.role || '',
          suspicion: n.suspicion || '',
        }));

      const nodeIds = new Set(nodes.map(n => n.id));
      let links: GraphEdge[] = data.edges
        .filter((e: any) => nodeIds.has(String(e.source)) && nodeIds.has(String(e.target)))
        .map((e: any) => ({
          source: String(e.source),
          target: String(e.target),
          kind: (e.kind || 'LINKED').toUpperCase(),
          amount: e.amount || 0,
          duration: e.duration || 0,
          reason: e.reason || '',
          tx_id: e.tx_id,
          cdr_id: e.cdr_id,
        }));

      // Inject transaction/call as a node if it was searched (to show Txn node and Amber root color)
      const targetIsEdge = links.find((e: any) => e.tx_id === target || e.cdr_id === target);
      if (targetIsEdge && !nodes.find(n => n.id === target)) {
        const isTxn = targetIsEdge.tx_id === target;
        nodes.push({
          id: target,
          kind: isTxn ? 'txn' : 'phone',
          label: (isTxn ? 'Txn ' : 'Call ') + target,
          hop_distance: 0,
          risk: 100,
          centrality: 1,
          role: 'Queried Node',
          suspicion: 'Root of Investigation'
        });
        
        // Reroute the edge through this node
        links = links.filter(e => e !== targetIsEdge);
        links.push({
          source: targetIsEdge.source,
          target: target,
          kind: targetIsEdge.kind,
          amount: targetIsEdge.amount,
          duration: targetIsEdge.duration,
          reason: targetIsEdge.reason,
        });
        links.push({
          source: target,
          target: targetIsEdge.target,
          kind: targetIsEdge.kind,
          amount: targetIsEdge.amount,
          duration: targetIsEdge.duration,
          reason: targetIsEdge.reason,
        });
      }

      setGraphData({ nodes, links });
      setEntityId(target); // Update state to the actual queried target so Amber coloring works

      // Generate insights
      try {
        const ins = await api.copilotInsightsGenerate({
          root_entity: target,
          nodes: data.nodes,
          edges: data.edges,
        });
        if (ins && !ins.error) setInsights(ins);
      } catch {
        /* insights are best-effort */
      }
    } catch (err: any) {
      console.error(err);
      setError(err?.message || 'Failed to load graph');
    } finally {
      setLoading(false);
    }
  }, [entityId]);

  useEffect(() => {
    if (initialEntity) {
      loadGraph(initialEntity);
    } else {
      api.alerts(0, 10).then((res) => {
        const top = res.results?.[0]?.transaction_id || res.results?.[0]?.sender_customer_id || res.results?.[0]?.customer_phone;
        if (top) {
          setEntityId(top);
          loadGraph(top);
        }
      }).catch(() => {});
    }
  }, [initialEntity, loadGraph]);

  // ─── 3D node styling (memoized) ───────────────────────────────────
  const nodeColor = useCallback((node: any) => {
    if (node.role === 'Master Node' || (node.id && entityId && String(node.id).trim().toLowerCase() === String(entityId).trim().toLowerCase())) {
      return '#fbbf24'; // Centered Master Node: Amber/Yellow glow
    }
    const hasSuspicion = node.suspicion && typeof node.suspicion === 'string' && node.suspicion.trim().length > 3 && node.suspicion.toLowerCase() !== 'none';
    if (hasSuspicion || node.risk >= 40 || node.role === 'Anomalous') return '#ef4444'; // Anomalous: Red glow!
    if (node.role && node.role.toLowerCase().includes('mule')) return '#ec4899'; // Pink for mules
    return NODE_COLORS[node.kind] || NODE_COLORS.unknown;
  }, [entityId]);

  const nodeVal = useCallback((node: any) => {
    if (node.role === 'Master Node' || (node.id && entityId && String(node.id).trim().toLowerCase() === String(entityId).trim().toLowerCase())) {
      return 25; // Root master node is static and large
    }
    if (node.kind === 'account') return 12 + (node.centrality || 0) * 8;
    if (node.kind === 'txn') return 10;
    if (node.kind === 'phone') return 8;
    return 6; // Addon nodes (imei, ip)
  }, [entityId]);

  const nodeLabel = useCallback((_node: any) => {
    return '';
  }, []);

  const linkColor = useCallback((link: any) => {
    return EDGE_COLORS[link.kind] || EDGE_COLORS.LINKED;
  }, []);

  const linkWidth = useCallback((link: any) => {
    if (link.kind === 'TRANSFERRED_TO') {
      return link.amount > 50000 ? 3 : 1.5;
    }
    return 0.8;
  }, []);

  const linkLabel = useCallback((link: any) => {
    const parts = [`<div style="background:rgba(15,23,42,0.9);color:#f8fafc;padding:6px 10px;border-radius:6px;font-family:monospace;font-size:11px;border:1px solid rgba(100,116,139,0.3)">`];
    if (link.amount > 0) parts.push(`<b>₹${Number(link.amount).toLocaleString('en-IN')}</b> `);
    if (link.duration > 0) parts.push(`<span style="color:#a78bfa">${link.duration}s call</span> `);
    parts.push(`<span style="color:#64748b">${link.kind}</span>`);
    if (link.reason) parts.push(`<div style="color:#fbbf24;margin-top:3px;font-size:10px">💡 ${link.reason}</div>`);
    parts.push(`</div>`);
    return parts.join('');
  }, []);

  const handleNodeClick = useCallback((node: any) => {
    setSelectedNode(node);
    if (fgRef.current) {
      const distance = 120;
      const distRatio = 1 + distance / Math.hypot(node.x || 0, node.y || 0, node.z || 0);
      fgRef.current.cameraPosition(
        { x: (node.x || 0) * distRatio, y: (node.y || 0) * distRatio, z: (node.z || 0) * distRatio },
        node,
        1500
      );
    }
  }, []);

  const handleNodeHover = useCallback((node: any) => {
    setHoveredNode(node as GraphNode | null);
  }, []);

  const handleNodeDoubleClick = useCallback((node: any) => {
    setEntityId(node.id);
    loadGraph(node.id);
  }, [loadGraph]);

  const linkDirectionalParticles = useCallback((link: any) => {
    return link.kind === 'TRANSFERRED_TO' ? 4 : (link.kind === 'CALLED' ? 2 : 0);
  }, []);

  const linkDirectionalParticleSpeed = useCallback((link: any) => {
    return link.kind === 'TRANSFERRED_TO' ? 0.006 : 0.003;
  }, []);

  const linkDirectionalParticleColor = useCallback((link: any) => {
    return link.kind === 'TRANSFERRED_TO' ? '#10b981' : '#a78bfa';
  }, []);

  const hoveredColor = useMemo(() => {
    return hoveredNode ? nodeColor(hoveredNode) : '#ffffff';
  }, [hoveredNode, nodeColor]);

  return (
    <div className="w-full h-full min-h-[600px] flex flex-col relative overflow-hidden bg-background">
      {/* ── search bar ─────────────────────────────────────────────────── */}
      <div className="absolute top-4 left-4 z-20 flex gap-2 w-[400px]">
        <Input
          value={entityId}
          onChange={(e) => setEntityId(e.target.value)}
          placeholder="Enter Entity ID (Account, Phone, TXN…)"
          className="bg-slate-900/90 border-slate-700 text-slate-200 placeholder:text-slate-500 backdrop-blur-md shadow-xl focus:border-cyan-500/60 focus:ring-cyan-500/20"
          onKeyDown={(e) => e.key === 'Enter' && loadGraph()}
        />
        <Button
          onClick={() => loadGraph()}
          disabled={loading}
          className="bg-cyan-600 hover:bg-cyan-500 shadow-lg shadow-cyan-500/20"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
        </Button>
      </div>

      {/* ── legend ────────────────────────────────────────────────────── */}
      <div className="absolute top-4 right-4 z-20 rounded-xl border border-slate-700/60 bg-slate-900/80 backdrop-blur-xl p-3 shadow-2xl">
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">Node Types</p>
        <div className="space-y-1">
          {Object.entries(NODE_COLORS).filter(([k]) => k !== 'unknown').map(([k, c]) => (
            <div key={k} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} />
              <span className="text-[11px] text-slate-400 capitalize">{k}</span>
            </div>
          ))}
        </div>
        
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mt-3 mb-2">Flags</p>
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full shadow-[0_0_8px_rgba(251,191,36,0.8)]" style={{ background: '#fbbf24' }} />
            <span className="text-[11px] text-amber-400 font-medium">Master Node</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full shadow-[0_0_8px_rgba(239,68,68,0.8)]" style={{ background: '#ef4444' }} />
            <span className="text-[11px] text-red-400 font-medium">Anomalous</span>
          </div>
        </div>

        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mt-3 mb-2">Edges</p>
        <div className="space-y-1">
          {Object.entries(EDGE_COLORS).map(([k, c]) => (
            <div key={k} className="flex items-center gap-2">
              <span className="w-4 h-[2px] rounded" style={{ background: c }} />
              <span className="text-[11px] text-slate-400">{k.replace(/_/g, ' ')}</span>
            </div>
          ))}
        </div>
        {graphData.nodes.length > 0 && (
          <div className="mt-3 pt-2 border-t border-slate-700/50">
            <p className="text-[10px] text-cyan-400 font-mono">{graphData.nodes.length} nodes · {graphData.links.length} edges</p>
          </div>
        )}
      </div>

      {/* ── error state ───────────────────────────────────────────────── */}
      {error && (
        <div className="absolute top-20 left-4 z-20 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-950/80 backdrop-blur-md px-4 py-2.5 text-sm text-red-300 shadow-xl">
          <AlertTriangle className="w-4 h-4" />
          {error}
        </div>
      )}

      {/* ── empty state ───────────────────────────────────────────────── */}
      {!loading && graphData.nodes.length === 0 && !error && (
        <div className="absolute inset-0 flex flex-col items-center justify-center z-10">
          <div className="rounded-full bg-slate-800/60 p-6 mb-4">
            <Network className="w-12 h-12 text-cyan-500/50" />
          </div>
          <p className="text-slate-500 text-sm font-mono">Enter an entity ID to visualize the 3D forensic network</p>
          <p className="text-slate-600 text-xs mt-1">Account number, phone, transaction ID, IMEI…</p>
        </div>
      )}

      {/* ── 3D force graph (isolated canvas, zero hover re-renders) ── */}
      <GraphCanvas
        fgRef={fgRef}
        graphData={graphData}
        nodeLabel={nodeLabel}
        nodeColor={nodeColor}
        nodeVal={nodeVal}
        linkLabel={linkLabel}
        linkColor={linkColor}
        linkWidth={linkWidth}
        linkDirectionalParticles={linkDirectionalParticles}
        linkDirectionalParticleSpeed={linkDirectionalParticleSpeed}
        linkDirectionalParticleColor={linkDirectionalParticleColor}
        onNodeClick={handleNodeClick}
        onNodeHover={handleNodeHover}
        onNodeRightClick={handleNodeDoubleClick}
      />

      {/* ── hover kpi card (decoupled overlay) ────────────────────────── */}
      {!selectedNode && (
        <GraphHoverOverlay node={hoveredNode} color={hoveredColor} />
      )}

      {/* ── selected node detail ──────────────────────────────────────── */}
      {selectedNode && (
        <EntityDetailsOverlay 
          entityId={selectedNode.id} 
          onClose={() => setSelectedNode(null)}
          onInvestigate={(id) => {
            setSelectedNode(null);
            setEntityId(id);
            loadGraph(id);
          }}
        />
      )}

      {/* ── AI insights panel ─────────────────────────────────────────── */}
      {insights && (
        <div className="absolute top-20 left-4 z-20 w-[360px] rounded-xl border border-slate-700/60 bg-slate-900/90 backdrop-blur-xl shadow-2xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/50 bg-gradient-to-r from-cyan-500/10 via-transparent to-violet-500/10">
            <div className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-cyan-400" />
              <span className="text-xs font-mono font-bold text-slate-200 tracking-wide">AI INVESTIGATION REPORT</span>
            </div>
          </div>
          <div className="p-4 space-y-4 max-h-[50vh] overflow-y-auto">
            <div>
              <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Executive Summary</p>
              <p className="text-xs text-slate-300 leading-relaxed">{insights.executive_summary}</p>
            </div>
            {insights.primary_findings?.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">Key Findings</p>
                <ul className="space-y-1">
                  {insights.primary_findings.map((f, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-slate-400">
                      <span className="text-cyan-500 mt-0.5">▸</span>
                      {f}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {insights.recommended_actions?.length > 0 && (
              <div>
                <p className="text-[10px] uppercase tracking-widest text-red-400 mb-1">Recommended Actions</p>
                <ul className="space-y-1">
                  {insights.recommended_actions.map((r, i) => (
                    <li key={i} className="flex items-start gap-1.5 text-xs text-red-300 font-medium">
                      <span className="text-red-500 mt-0.5">⚡</span>
                      {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
