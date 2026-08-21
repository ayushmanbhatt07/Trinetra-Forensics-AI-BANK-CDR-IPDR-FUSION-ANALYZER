"use client";

/**
 * Premium 3D Forensic Investigation Graph
 * 
 * Uses react-force-graph-3d (Three.js under the hood) to render a stunning
 * 3D force-directed linked-transactions tree. Nodes are color-coded by type
 * (account / phone / entity), sized by centrality, and glow by risk level.
 * Edges animate particle flow along money transfer directions.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { Search, Loader2, AlertTriangle, Network, Shield, ZoomIn } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/api';
import SpriteText from 'three-spritetext';
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
const RISK_GLOW: Record<string, string> = {
  high:   'rgba(239,68,68,0.6)',
  medium: 'rgba(245,158,11,0.5)',
  low:    'rgba(16,185,129,0.3)',
};

// ─── node painting ───────────────────────────────────────────────────────
function paintNode(node: any, ctx: CanvasRenderingContext2D) {
  const r = 5 + (node.centrality || 0) * 8;
  const color = NODE_COLORS[node.kind] || NODE_COLORS.unknown;

  // Glow halo for high-risk / hub nodes
  if (node.centrality > 0.5 || node.risk > 60) {
    ctx.beginPath();
    ctx.arc(node.x, node.y, r + 4, 0, 2 * Math.PI);
    ctx.fillStyle = node.risk > 60 ? RISK_GLOW.high : RISK_GLOW.medium;
    ctx.fill();
  }

  // Node circle
  ctx.beginPath();
  ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
  ctx.fillStyle = color;
  ctx.fill();
  ctx.strokeStyle = '#ffffff';
  ctx.lineWidth = 1;
  ctx.stroke();

  // Label
  const label = node.label?.length > 14
    ? node.label.slice(0, 12) + '…'
    : (node.label || node.id);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  ctx.font = 'bold 3px Inter, sans-serif';
  ctx.fillStyle = '#e2e8f0';
  ctx.fillText(label, node.x, node.y + r + 2);
}

// ─── types ────────────────────────────────────────────────────────────────
interface GraphNode {
  id: string;
  kind: string;
  label: string;
  name?: string;
  phone?: string;
  hop_distance: number;
  risk: number;
  centrality: number;
  role?: string;
  suspicion?: string;
  sender?: string;
  receiver?: string;
  sender_name?: string;
  receiver_name?: string;
  amount?: number;
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

// ─── component ────────────────────────────────────────────────────────────
export function InvestigationGraph({ initialEntity = '' }: { initialEntity?: string }) {
  const fgRef = useRef<any>(null);
  const [entityId, setEntityId] = useState(initialEntity);
  const [graphData, setGraphData] = useState<{ nodes: GraphNode[]; links: GraphEdge[] }>({ nodes: [], links: [] });
  const [loading, setLoading] = useState(false);
  const [insights, setInsights] = useState<Insights | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [error, setError] = useState('');

  // ── Legend Selection Checkboxes State ──────────────────────────────────
  const [selectedNodeKinds, setSelectedNodeKinds] = useState<Set<string>>(
    new Set(['account', 'phone', 'txn', 'imei', 'ip'])
  );
  const [selectedEdgeKinds, setSelectedEdgeKinds] = useState<Set<string>>(
    new Set(['TRANSFERRED_TO', 'CALLED', 'LINKED'])
  );
  const [showOnlyAnomalous, setShowOnlyAnomalous] = useState(false);
  const [showMasterOnly, setShowMasterOnly] = useState(false);

  const toggleNodeKind = (kind: string) => {
    setSelectedNodeKinds(prev => {
      const next = new Set(prev);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
        // Smart auto-enabling: if turning on 'account' or 'txn', ensure TRANSFERRED_TO is enabled
        if (kind === 'account' || kind === 'txn') {
          setSelectedEdgeKinds(edges => new Set(edges).add('TRANSFERRED_TO'));
        } else if (kind === 'phone') {
          setSelectedEdgeKinds(edges => new Set(edges).add('CALLED'));
        }
      }
      return next;
    });
  };

  const toggleEdgeKind = (kind: string) => {
    setSelectedEdgeKinds(prev => {
      const next = new Set(prev);
      if (next.has(kind)) {
        next.delete(kind);
      } else {
        next.add(kind);
        // Smart auto-enabling nodes required by this edge connection type
        if (kind === 'TRANSFERRED_TO') {
          setSelectedNodeKinds(nodes => new Set(nodes).add('account').add('txn'));
        } else if (kind === 'CALLED') {
          setSelectedNodeKinds(nodes => new Set(nodes).add('phone'));
        } else if (kind === 'LINKED') {
          setSelectedNodeKinds(nodes => new Set(nodes).add('phone').add('imei').add('ip'));
        }
      }
      return next;
    });
  };

  const selectAllFilters = () => {
    setSelectedNodeKinds(new Set(['account', 'phone', 'txn', 'imei', 'ip']));
    setSelectedEdgeKinds(new Set(['TRANSFERRED_TO', 'CALLED', 'LINKED']));
    setShowOnlyAnomalous(false);
    setShowMasterOnly(false);
  };

  const filteredGraphData = useMemo(() => {
    const rawNodes = graphData.nodes || [];
    const rawLinks = graphData.links || [];

    const filteredNodes = rawNodes.filter(n => {
      const isRoot = entityId && String(n.id).trim().toLowerCase() === String(entityId).trim().toLowerCase();
      if (isRoot) return true;

      const kindMatch = selectedNodeKinds.has((n.kind || '').toLowerCase());
      if (!kindMatch) return false;

      if (showOnlyAnomalous) {
        const isRed = (n.risk > 80) || (n.suspicion && typeof n.suspicion === 'string' && n.suspicion.toLowerCase() !== 'none' && n.suspicion.trim().length > 3);
        if (!isRed) return false;
      }

      if (showMasterOnly) {
        const isMaster = n.centrality > 0.5;
        if (!isMaster) return false;
      }

      return true;
    });

    const activeNodeIds = new Set(filteredNodes.map(n => String(n.id)));

    // Clean un-hydrated string IDs for source and target so ForceGraph3D re-simulates cleanly
    const filteredLinks = rawLinks
      .filter(e => {
        const edgeKind = (e.kind || '').toUpperCase();
        if (!selectedEdgeKinds.has(edgeKind)) return false;

        const sId = typeof e.source === 'object' ? (e.source as any).id : String(e.source);
        const tId = typeof e.target === 'object' ? (e.target as any).id : String(e.target);

        return activeNodeIds.has(sId) && activeNodeIds.has(tId);
      })
      .map(e => ({
        ...e,
        source: typeof e.source === 'object' ? (e.source as any).id : String(e.source),
        target: typeof e.target === 'object' ? (e.target as any).id : String(e.target),
      }));

    return { nodes: filteredNodes, links: filteredLinks };
  }, [graphData, selectedNodeKinds, selectedEdgeKinds, showOnlyAnomalous, showMasterOnly, entityId]);

  const filterKey = useMemo(() => {
    return `${Array.from(selectedNodeKinds).sort().join('-')}_${Array.from(selectedEdgeKinds).sort().join('-')}_${showMasterOnly}_${showOnlyAnomalous}_${entityId}_${filteredGraphData.nodes.length}_${filteredGraphData.links.length}`;
  }, [selectedNodeKinds, selectedEdgeKinds, showMasterOnly, showOnlyAnomalous, entityId, filteredGraphData]);

  const loadGraph = useCallback(async (eid?: string) => {
    const target = (eid || entityId || initialEntity).trim();
    if (!target) return;
    setEntityId(target);
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
          name: n.name && n.name !== 'Unknown Entity' ? n.name : (n.label && n.label !== n.id ? n.label : ''),
          phone: n.phone || '',
          hop_distance: n.hop_distance || 0,
          risk: n.risk || 0,
          centrality: n.centrality || 0,
          role: n.role || '',
          suspicion: n.suspicion || '',
        }));

      const nodeMap = new Map(nodes.map(n => [n.id, n]));

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
        const sourceNode = nodeMap.get(String(targetIsEdge.source));
        const targetNode = nodeMap.get(String(targetIsEdge.target));

        const sName = sourceNode?.name || sourceNode?.label || String(targetIsEdge.source);
        const tName = targetNode?.name || targetNode?.label || String(targetIsEdge.target);
        const flowName = `${sName} → ${tName}`;

        nodes.push({
          id: target,
          kind: isTxn ? 'txn' : 'phone',
          label: (isTxn ? 'Txn ' : 'Call ') + target,
          name: flowName,
          sender: String(targetIsEdge.source),
          receiver: String(targetIsEdge.target),
          sender_name: sName,
          receiver_name: tName,
          amount: targetIsEdge.amount,
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
    if (initialEntity) loadGraph(initialEntity);
  }, [initialEntity]);

  // ─── 3D node styling ──────────────────────────────────────────────
  const nodeColor = useCallback((node: any) => {
    if (node.id && entityId && String(node.id).trim().toLowerCase() === String(entityId).trim().toLowerCase()) {
      return '#fbbf24'; // Master Node: Amber/Yellow
    }
    const hasSuspicion = node.suspicion && typeof node.suspicion === 'string' && node.suspicion.trim().length > 3 && node.suspicion.toLowerCase() !== 'none';
    if (hasSuspicion || node.risk > 80) return '#ef4444'; // Anomalous: Red
    if (node.role && node.role.toLowerCase().includes('mule')) return '#ec4899'; // Pink for mules
    return NODE_COLORS[node.kind] || NODE_COLORS.unknown;
  }, [entityId]);

  const nodeVal = useCallback((node: any) => {
    if (node.id && entityId && String(node.id).trim().toLowerCase() === String(entityId).trim().toLowerCase()) {
      return 20; // Root node is static and large
    }
    return 2 + (node.centrality || 0) * 10 + (node.hop_distance === 0 ? 5 : 0);
  }, [entityId]);

  const nodeLabel = useCallback((node: any) => {
    // User requested NO name in the bubble for 3D label, or rely on hover card
    // We will return empty for the default 3D label to avoid congestion, 
    // and rely on the UI overlay for hover.
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
    // Focus camera on clicked node
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

      {/* ── legend with interactive selection checkboxes ───────────────────────── */}
      <div className="absolute top-4 right-4 z-20 rounded-xl border border-slate-700/70 bg-slate-900/90 backdrop-blur-xl p-3 shadow-2xl w-60 text-slate-200 select-none">
        <div className="flex items-center justify-between border-b border-slate-700/60 pb-2 mb-2">
          <p className="text-[10px] font-mono uppercase tracking-widest text-cyan-400 font-semibold">
            Legend & Filter
          </p>
          <button
            onClick={selectAllFilters}
            className="text-[10px] text-cyan-400 hover:text-cyan-200 underline font-mono transition-colors"
          >
            Reset All
          </button>
        </div>

        {/* NODE TYPES CHECKBOXES */}
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-400 mb-1.5 font-medium">
          Node Types
        </p>
        <div className="space-y-1 mb-3">
          {Object.entries(NODE_COLORS).filter(([k]) => k !== 'unknown').map(([k, c]) => {
            const isChecked = selectedNodeKinds.has(k);
            return (
              <label
                key={k}
                className="flex items-center justify-between gap-2 px-1.5 py-0.5 rounded hover:bg-slate-800/60 cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: c }} />
                  <span className={`text-[11px] capitalize ${isChecked ? 'text-slate-200 font-medium' : 'text-slate-500 line-through'}`}>
                    {k}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggleNodeKind(k)}
                  className="rounded border-slate-700 bg-slate-800 text-cyan-500 focus:ring-0 size-3.5 cursor-pointer accent-cyan-500"
                />
              </label>
            );
          })}
        </div>

        {/* FLAGS CHECKBOXES */}
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-400 mb-1.5 font-medium">
          Flags
        </p>
        <div className="space-y-1 mb-3">
          <label className="flex items-center justify-between gap-2 px-1.5 py-0.5 rounded hover:bg-slate-800/60 cursor-pointer transition-colors">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full shadow-[0_0_8px_rgba(251,191,36,0.8)] shrink-0" style={{ background: '#fbbf24' }} />
              <span className={`text-[11px] ${showMasterOnly ? 'text-amber-300 font-semibold' : 'text-amber-400/80'}`}>
                Master Hubs Only
              </span>
            </div>
            <input
              type="checkbox"
              checked={showMasterOnly}
              onChange={(e) => setShowMasterOnly(e.target.checked)}
              className="rounded border-slate-700 bg-slate-800 text-amber-500 focus:ring-0 size-3.5 cursor-pointer accent-amber-500"
            />
          </label>
          <label className="flex items-center justify-between gap-2 px-1.5 py-0.5 rounded hover:bg-slate-800/60 cursor-pointer transition-colors">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full shadow-[0_0_8px_rgba(239,68,68,0.8)] shrink-0" style={{ background: '#ef4444' }} />
              <span className={`text-[11px] ${showOnlyAnomalous ? 'text-rose-300 font-semibold' : 'text-red-400/80'}`}>
                Anomalous Only
              </span>
            </div>
            <input
              type="checkbox"
              checked={showOnlyAnomalous}
              onChange={(e) => setShowOnlyAnomalous(e.target.checked)}
              className="rounded border-slate-700 bg-slate-800 text-rose-500 focus:ring-0 size-3.5 cursor-pointer accent-rose-500"
            />
          </label>
        </div>

        {/* EDGES CHECKBOXES */}
        <p className="text-[10px] font-mono uppercase tracking-widest text-slate-400 mb-1.5 font-medium">
          Edge Connections
        </p>
        <div className="space-y-1">
          {Object.entries(EDGE_COLORS).map(([k, c]) => {
            const isChecked = selectedEdgeKinds.has(k);
            return (
              <label
                key={k}
                className="flex items-center justify-between gap-2 px-1.5 py-0.5 rounded hover:bg-slate-800/60 cursor-pointer transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="w-4 h-[2.5px] rounded shrink-0" style={{ background: c }} />
                  <span className={`text-[11px] ${isChecked ? 'text-slate-200 font-medium' : 'text-slate-500 line-through'}`}>
                    {k.replace(/_/g, ' ')}
                  </span>
                </div>
                <input
                  type="checkbox"
                  checked={isChecked}
                  onChange={() => toggleEdgeKind(k)}
                  className="rounded border-slate-700 bg-slate-800 text-cyan-500 focus:ring-0 size-3.5 cursor-pointer accent-cyan-500"
                />
              </label>
            );
          })}
        </div>

        {graphData.nodes.length > 0 && (
          <div className="mt-3 pt-2 border-t border-slate-700/50 flex items-center justify-between">
            <p className="text-[10px] text-cyan-400 font-mono font-medium">
              {filteredGraphData.nodes.length} nodes · {filteredGraphData.links.length} edges
            </p>
            {filteredGraphData.nodes.length !== graphData.nodes.length && (
              <span className="text-[9px] text-amber-400 font-mono">
                (Filtered)
              </span>
            )}
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

      {/* ── 3D force graph ────────────────────────────────────────────── */}
      {graphData.nodes.length > 0 && (
        <ForceGraph3D
          key={filterKey}
          ref={fgRef}
          graphData={filteredGraphData}
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
          onNodeClick={handleNodeClick}
          onNodeHover={(node) => setHoveredNode(node as GraphNode | null)}
          onNodeRightClick={handleNodeDoubleClick}
          backgroundColor="rgba(0,0,0,0)"
          showNavInfo={false}
          enableNodeDrag={true}
          enableNavigationControls={true}
          warmupTicks={80}
          cooldownTicks={120}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
        />
      )}

      {/* ── hover kpi card ────────────────────────────────────────────── */}
      {hoveredNode && !selectedNode && (
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30 w-[370px] pointer-events-none">
          {(() => {
            const isRoot = hoveredNode.id && entityId && String(hoveredNode.id).trim().toLowerCase() === String(entityId).trim().toLowerCase();
            const isRed = (hoveredNode.risk > 80) || (hoveredNode.suspicion && typeof hoveredNode.suspicion === 'string' && hoveredNode.suspicion.toLowerCase() !== 'none' && hoveredNode.suspicion.trim().length > 3);
            const isBlue = hoveredNode.kind === 'account' && !isRoot;
            const isTxn = hoveredNode.kind === 'txn';
            
            const nColor = nodeColor(hoveredNode);
            const nameToDisplay = hoveredNode.name && hoveredNode.name !== 'Unknown Entity' && hoveredNode.name !== hoveredNode.id 
              ? hoveredNode.name 
              : (hoveredNode.label && hoveredNode.label !== hoveredNode.id ? hoveredNode.label : '');

            return (
              <div className={`bg-slate-900/95 backdrop-blur-md p-4 rounded-xl border shadow-2xl space-y-2.5 ${
                isRed ? 'border-rose-600/70 shadow-rose-950/40' : isBlue ? 'border-blue-600/60' : isTxn || isRoot ? 'border-amber-600/60 shadow-amber-950/30' : 'border-slate-700'
              }`}>
                {/* Header with node indicator color, type & primary title */}
                <div className="flex items-center gap-3">
                  <span className="w-3.5 h-3.5 rounded-full shrink-0 shadow-lg" style={{ background: nColor }}></span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                      {isTxn ? 'Transaction Entity' : isBlue ? 'Bank Account Entity' : isRed ? 'High-Risk / Suspicious Entity' : `${hoveredNode.kind} Entity`}
                    </p>
                    <strong className="text-sm text-slate-100 font-semibold break-all leading-tight block">
                      {nameToDisplay || (isTxn ? `Txn ${hoveredNode.id}` : hoveredNode.id)}
                    </strong>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-slate-800/60 p-2 rounded-lg border border-slate-700/50">
                    <p className="text-[10px] uppercase text-slate-400 font-medium">Kind</p>
                    <p className="text-xs text-slate-200 capitalize font-medium">{hoveredNode.kind}</p>
                  </div>
                  <div className={`p-2 rounded-lg border ${isRed ? 'bg-rose-950/40 border-rose-800/40' : 'bg-slate-800/60 border-slate-700/50'}`}>
                    <p className="text-[10px] uppercase text-slate-400 font-medium">Risk / Suspicion</p>
                    <p className={`text-xs font-semibold capitalize ${isRed ? 'text-rose-400' : 'text-amber-400'}`}>
                      {hoveredNode.suspicion || (hoveredNode.risk > 0 ? `${hoveredNode.risk} Score` : 'None')}
                    </p>
                  </div>
                </div>

                {hoveredNode.role && (
                  <div className="bg-cyan-950/30 p-2 rounded-lg border border-cyan-800/40">
                    <p className="text-[10px] uppercase text-cyan-400 font-medium">Role</p>
                    <p className="text-xs text-cyan-200 font-medium">{hoveredNode.role}</p>
                  </div>
                )}

                {/* 🔴 RED ENTITIES (High-Risk / Anomalous) */}
                {isRed && (
                  <div className="bg-rose-950/40 p-2.5 rounded-lg border border-rose-800/50 space-y-1.5">
                    <p className="text-[10px] uppercase font-bold text-rose-400 tracking-wider">⚠️ High-Risk Entity Details</p>
                    <div>
                      <p className="text-[10px] text-slate-400">Account / Holder Name</p>
                      <p className="text-xs font-semibold text-rose-200 break-all">{nameToDisplay || 'Flagged Entity'}</p>
                    </div>
                    <div className="flex justify-between items-center text-xs text-slate-300 font-mono">
                      <span>ID: {hoveredNode.id}</span>
                      {hoveredNode.phone && <span>Ph: {hoveredNode.phone}</span>}
                    </div>
                  </div>
                )}

                {/* 🔵 BLUE ENTITIES (Bank Accounts) */}
                {isBlue && !isRed && (
                  <div className="bg-blue-950/40 p-2.5 rounded-lg border border-blue-800/40 space-y-1.5">
                    <p className="text-[10px] uppercase font-bold text-cyan-400 tracking-wider">🏦 Bank Account Details</p>
                    <div>
                      <p className="text-[10px] text-slate-400">Account Holder Name</p>
                      <p className="text-xs font-semibold text-cyan-200 break-all">{nameToDisplay || 'Account Holder'}</p>
                    </div>
                    <div className="flex justify-between items-center text-xs text-slate-300 font-mono">
                      <span>Acc No: {hoveredNode.id}</span>
                      {hoveredNode.phone && <span>Ph: {hoveredNode.phone}</span>}
                    </div>
                  </div>
                )}

                {/* 🟡 YELLOW ENTITIES (Transactions / Root Node) */}
                {isTxn && (
                  <div className="bg-amber-950/30 p-2.5 rounded-lg border border-amber-800/40 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <p className="text-[10px] uppercase font-bold text-amber-400 tracking-wider">💸 Transfer Flow & Parties</p>
                      {hoveredNode.amount ? (
                        <span className="text-xs font-bold font-mono text-emerald-400">
                          ₹{Number(hoveredNode.amount).toLocaleString('en-IN')}
                        </span>
                      ) : null}
                    </div>
                    {nameToDisplay && (
                      <div>
                        <p className="text-[10px] text-slate-400">Sender → Receiver Flow</p>
                        <p className="text-xs font-semibold text-amber-200 font-mono break-all">{nameToDisplay}</p>
                      </div>
                    )}
                    <div>
                      <p className="text-[10px] text-slate-400">TXN ID</p>
                      <p className="text-xs text-slate-200 font-mono break-all">{hoveredNode.id}</p>
                    </div>
                  </div>
                )}

                {/* OTHER ENTITIES (Phones / IMEI / IP) */}
                {!isRed && !isBlue && !isTxn && (
                  <div className="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/50 space-y-1">
                    {nameToDisplay && (
                      <div>
                        <p className="text-[10px] uppercase text-slate-400 font-medium">Subscriber / Holder Name</p>
                        <p className="text-xs font-semibold text-emerald-400 break-all">{nameToDisplay}</p>
                      </div>
                    )}
                    <div>
                      <p className="text-[10px] uppercase text-slate-400 font-medium">
                        {hoveredNode.kind === 'phone' ? 'Phone No' : 'Entity ID'}
                      </p>
                      <p className="text-xs text-slate-300 font-mono break-all">{hoveredNode.id}</p>
                    </div>
                  </div>
                )}

                {hoveredNode.centrality > 0.5 && (
                  <p className="text-[10px] text-purple-400 pt-0.5 font-medium flex items-center gap-1">
                    <span>🔗</span> High Centrality Hub
                  </p>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {/* ── selected node detail ──────────────────────────────────────── */}
      {selectedNode && (
        <EntityDetailsOverlay 
          entityId={selectedNode.id} 
          onClose={() => setSelectedNode(null)}
          onInvestigate={(id) => {
            setSelectedNode(null);
            setEntityId(id);
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
