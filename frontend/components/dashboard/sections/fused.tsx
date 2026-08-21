"use client";

/**
 * Fused Transactions — standalone section showing the fused bank+CDR+IPDR
 * records table with search, account filter, risk annotation and pagination.
 *
 * SYNCHRONIZATION FIX:
 * The component must NOT bail out ("No fused records") while the pipeline
 * context is still loading its first status response. Doing so causes a
 * permanent empty state that only resolves after a browser refresh.
 *
 * Correct lifecycle:
 *   mount → context loading=true  → show spinner
 *   context loading=false, isFusedReady=false  → show "pipeline running" state
 *   context loading=false, isFusedReady=true   → fetch data
 *   isFusedReady transitions false→true (pipeline completes) → refetch
 */
import React, { useState, useEffect, useCallback, useRef } from "react";
import {
  Database, Search, Download, ShieldAlert,
  FileText, X, Activity, AlertTriangle, Check, Copy, PhoneCall, Loader2, Clock, Network
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import { InvestigationPanel } from "@/components/dashboard/investigation-panel";
import { api, type FusedRow, isPipelineNotReady } from "@/lib/api";
import { usePipeline } from "@/lib/pipeline-context";

const PAGE_SIZE = 50;

const riskStyle = (score: number) => {
  if (score >= 86) return { color: "#f43f5e", bg: "bg-rose-500/10 border-rose-500/40" };
  if (score >= 71) return { color: "#fb923c", bg: "bg-orange-500/10 border-orange-500/40" };
  if (score >= 51) return { color: "#facc15", bg: "bg-yellow-500/10 border-yellow-500/40" };
  if (score >= 26) return { color: "#38bdf8", bg: "bg-sky-500/10 border-sky-500/40" };
  return { color: "#34d399", bg: "bg-emerald-500/10 border-emerald-500/40" };
};

export const FusedSection = React.memo(function FusedSection() {
  const [rows, setRows] = useState<FusedRow[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [q, setQ] = useState("");
  const [dateStart, setDateStart] = useState("");
  const [dateEnd, setDateEnd] = useState("");
  const [minAmount, setMinAmount] = useState<number | "">("");
  const [maxAmount, setMaxAmount] = useState<number | "">("");
  const [riskBand, setRiskBand] = useState("");
  const [riskAnnotate, setRiskAnnotate] = useState(true);
  const [fusedLoading, setFusedLoading] = useState(true);
  const [fusedKey, setFusedKey] = useState(0);

  const [selectedRow, setSelectedRow] = useState<FusedRow | null>(null);
  const [copied, setCopied] = useState(false);
  const [panelPayload, setPanelPayload] = useState<any>(null);
  const [panelBusy, setPanelBusy] = useState(false);

  const { isFusedReady, isAnomaliesReady, loading: pipelineLoading, pipeline } = usePipeline();

  // In-memory client cache to make tab switches and pagination instant (0ms)
  const fusedCacheRef = useRef<Map<string, { rows: FusedRow[]; total: number }>>(new Map());

  // Track previous ready states
  const prevFusedReady = useRef<boolean>(false);
  const prevAnomaliesReady = useRef<boolean>(false);

  // Clear cache on dataset or pipeline status change
  useEffect(() => {
    fusedCacheRef.current.clear();
    setFusedKey((k) => k + 1);
  }, [pipeline?.dataset_id, pipeline?.status, isFusedReady]);

  // Listen for pipeline stage transition events
  useEffect(() => {
    const handleFusedReady = () => {
      fusedCacheRef.current.clear();
      setFusedKey((k) => k + 1);
    };
    window.addEventListener("pipeline:fused_ready", handleFusedReady);
    return () => window.removeEventListener("pipeline:fused_ready", handleFusedReady);
  }, []);

  const loadFused = useCallback(() => {
    if (!isFusedReady && !pipeline?.dataset_id) {
      setFusedLoading(false);
      return;
    }

    const cacheKey = `${pipeline?.dataset_id || "default"}:${offset}:${q}:${riskAnnotate}:${dateStart}:${dateEnd}:${minAmount}:${maxAmount}:${riskBand}:${isAnomaliesReady}`;
    const cached = fusedCacheRef.current.get(cacheKey);
    if (cached) {
      setRows(cached.rows);
      setTotal(cached.total);
      setFusedLoading(false);
      return;
    }

    // Fetch fused records
    setFusedLoading(true);
    api
      .fused(offset, PAGE_SIZE, q, "", "all", riskAnnotate, dateStart, dateEnd, Number(minAmount) || 0, Number(maxAmount) || 0, riskBand)
      .then((res) => {
        const data = { rows: res.rows || [], total: res.total ?? 0 };
        fusedCacheRef.current.set(cacheKey, data);
        setRows(data.rows);
        setTotal(data.total);
      })
      .catch((error) => {
        const err = error as { status?: number };
        if (err.status !== 409 && err.status !== 425 && !isPipelineNotReady(error)) {
          toast.error("Failed to load fused records.");
        }
        setRows([]);
        setTotal(0);
      })
      .finally(() => setFusedLoading(false));
  }, [offset, q, riskAnnotate, isFusedReady, isAnomaliesReady, dateStart, dateEnd, minAmount, maxAmount, riskBand, pipeline?.dataset_id]);

  // Primary effect: re-run loadFused whenever its dependencies change.
  useEffect(() => {
    const t = setTimeout(loadFused, q ? 200 : 0);
    return () => clearTimeout(t);
  }, [loadFused, fusedKey]);

  const downloadFusedCsv = async () => {
    const t = toast.loading("Preparing CSV...");
    try {
      await api.fusedCsv(q, "", "all", dateStart, dateEnd, Number(minAmount) || 0, Number(maxAmount) || 0, riskBand);
      toast.success("CSV export started.", { id: t });
    } catch (e) {
      toast.error((e as { message?: string })?.message ?? "Failed to export CSV.", { id: t });
    }
  };

  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(offset / PAGE_SIZE) + 1;

  const entityDossierCacheRef = useRef<Map<string, any>>(new Map());

  const openDossier = async (kind: string, value: string) => {
    if (!value) return;
    const cacheKey = `${kind}:${value}`;
    const cached = entityDossierCacheRef.current.get(cacheKey);
    if (cached) {
      setPanelPayload({ type: "entity", info: cached });
      return;
    }
    setPanelBusy(true);
    try {
      const info = await api.dossier(kind, value);
      entityDossierCacheRef.current.set(cacheKey, info);
      setPanelPayload({ type: "entity", info });
    } catch (e: any) {
      if (e.status !== 409) toast.error(`No dossier found for ${kind} ${value}`);
    } finally {
      setPanelBusy(false);
    }
  };

  const copyAlert = () => {
    if (!selectedRow) return;
    navigator.clipboard.writeText(JSON.stringify(selectedRow, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Determine what empty-state message to show
  const renderEmptyState = () => {
    if (pipelineLoading || fusedLoading) {
      return (
        <div className="p-8 text-center text-muted-foreground">
          <Loader2 className="mx-auto mb-3 size-7 animate-spin text-cyan-500" />
          <p className="text-sm animate-pulse">Loading fused records...</p>
        </div>
      );
    }
    if (!isFusedReady) {
      const stage = pipeline?.status ?? "IDLE";
      const isProcessing = ["PARSING", "FUSING", "SCORING", "GRAPHS"].includes(stage);
      return (
        <div className="p-8 text-center text-muted-foreground">
          {isProcessing ? (
            <>
              <Clock className="mx-auto mb-3 size-7 text-amber-500 animate-pulse" />
              <p className="text-sm font-semibold text-amber-400">
                Fusion pipeline is running — {stage}
              </p>
              <p className="mt-1 text-xs">
                The fused records will appear automatically when the pipeline is ready.
              </p>
            </>
          ) : (
            <>
              <Database className="mx-auto mb-3 size-7 opacity-30" />
              <p className="text-sm">No fused records. Ingest bank + CDR + IPDR datasets first.</p>
            </>
          )}
        </div>
      );
    }
    return (
      <div className="p-8 text-center text-muted-foreground">
        <Database className="mx-auto mb-3 size-7 opacity-30" />
        <p className="text-sm">No fused records match the current filters.</p>
      </div>
    );
  };

  return (
    <div className="space-y-6 h-[calc(100vh-12rem)]">
      <div className="flex h-full flex-col rounded-xl border border-border/70 bg-card/60 backdrop-blur">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <Database className="size-5 text-cyan-500" />
          <div className="min-w-[220px] flex-1">
            <p className="text-sm font-semibold text-cyan-500">Fused Transactions</p>
            <p className="text-xs text-muted-foreground">
              {total.toLocaleString()} bank transactions fused with CDR calls, IPDR sessions & NCRP complaints
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Switch
                id="risk-annotate"
                checked={riskAnnotate}
                onCheckedChange={(v) => { setRiskAnnotate(v); setOffset(0); }}
              />
              <label htmlFor="risk-annotate">Risk annotation</label>
            </div>
            <Button variant="outline" size="sm" onClick={downloadFusedCsv}>
              <Download className="mr-1 size-4" /> CSV
            </Button>
            <Button
              size="sm"
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={() => window.dispatchEvent(new CustomEvent("nav:section", { detail: "anomalies" }))}
            >
              <ShieldAlert className="mr-1 size-4" /> Show Anomalies
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2 border-b border-border p-3 bg-secondary/10">
          <div className="relative min-w-[220px] flex-1">
            <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input
              type="search"
              name="fused_search_q"
              autoComplete="off"
              autoCorrect="off"
              spellCheck={false}
              className="pl-8 h-9 text-sm"
              placeholder="Search Name, Account, Txn ID, Phone..."
              value={q}
              onChange={(e) => { setQ(e.target.value); setOffset(0); }}
            />
          </div>
          <div className="flex items-center gap-1">
            <Input
              type="date"
              className="w-[130px] h-9 text-sm"
              value={dateStart}
              onChange={(e) => { setDateStart(e.target.value); setOffset(0); }}
              title="Start Date"
            />
            <span className="text-muted-foreground text-xs px-1">to</span>
            <Input
              type="date"
              className="w-[130px] h-9 text-sm"
              value={dateEnd}
              onChange={(e) => { setDateEnd(e.target.value); setOffset(0); }}
              title="End Date"
            />
          </div>
          <div className="flex items-center gap-1">
            <Input
              type="number"
              name="fused_min_amt"
              autoComplete="off"
              className="w-[90px] h-9 text-sm"
              placeholder="Min Amt"
              value={minAmount}
              onChange={(e) => { setMinAmount(e.target.value ? Number(e.target.value) : ""); setOffset(0); }}
            />
            <span className="text-muted-foreground text-xs px-1">-</span>
            <Input
              type="number"
              name="fused_max_amt"
              autoComplete="off"
              className="w-[90px] h-9 text-sm"
              placeholder="Max Amt"
              value={maxAmount}
              onChange={(e) => { setMaxAmount(e.target.value ? Number(e.target.value) : ""); setOffset(0); }}
            />
          </div>
          <select 
            className="h-9 w-[120px] rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            value={riskBand}
            onChange={(e) => { setRiskBand(e.target.value); setOffset(0); }}
          >
            <option value="">All Risks</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="safe">Safe</option>
          </select>
          <Button size="sm" variant="secondary" onClick={() => { setOffset(0); setFusedKey((k) => k + 1); }} className="h-9">
            Apply Filter
          </Button>
        </div>

        <div className="flex-1 overflow-auto relative">
          {fusedLoading && rows.length > 0 && (
            <div className="absolute top-0 left-0 right-0 z-20 h-1 bg-cyan-500/20 overflow-hidden">
              <div className="h-full bg-cyan-500 animate-pulse w-full" />
            </div>
          )}
          {fusedLoading && rows.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <Loader2 className="mx-auto mb-3 size-7 animate-spin text-cyan-500" />
              <p className="text-sm animate-pulse">Loading fused records...</p>
            </div>
          ) : rows.length === 0 ? (
            renderEmptyState()
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-muted/60 text-muted-foreground">
                <tr>
                  <th className="p-3 text-left font-medium">Txn ID</th>
                  <th className="p-3 text-left font-medium">Cust ID</th>
                  <th className="p-3 text-left font-medium">Name</th>
                  <th className="p-3 text-left font-medium">Phone No</th>
                  <th className="p-3 text-left font-medium">Date/Time</th>
                  <th className="p-3 text-left font-medium">Sender</th>
                  <th className="p-3 text-left font-medium">Receiver</th>
                  <th className="p-3 text-left font-medium">Amount</th>
                  <th className="p-3 text-left font-medium">Mode</th>
                  <th className="p-3 text-center font-medium">Calls</th>
                  <th className="p-3 text-center font-medium">IPDR</th>
                  {riskAnnotate && <th className="p-3 text-left font-medium">Risk</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, idx) => (
                  <tr
                    key={row.transaction_id + idx}
                    onClick={() => setSelectedRow(row)}
                    className="cursor-pointer border-b border-border/50 transition-colors hover:bg-muted/30"
                  >
                    <td className="p-3 font-mono text-xs">{row.transaction_id}</td>
                    <td className="p-3 font-mono text-xs">{row.account_no}</td>
                    <td className="p-3 text-xs">{row.account_name ?? row.sender_phone ?? ""}</td>
                    <td className="p-3 font-mono text-xs">{row.sender_phone ?? row.receiver_phone ?? ""}</td>
                    <td className="p-3 whitespace-nowrap font-mono text-xs">{row.date} {row.time}</td>
                    <td className="p-3">
                      <div className="font-mono text-xs">{row.account_no}</div>
                      <div className="text-xs text-muted-foreground">{row.account_name || row.sender_phone}</div>
                    </td>
                    <td className="p-3">
                      <div className="font-mono text-xs">{row.receiver_account}</div>
                      <div className="text-xs text-muted-foreground">{row.counterparty_name || row.receiver_phone}</div>
                    </td>
                    <td className="p-3 font-mono">₹{Number(row.amount || 0).toLocaleString("en-IN", { maximumFractionDigits: 2 })}</td>
                    <td className="p-3"><Badge variant="outline">{row.mode}</Badge></td>
                    <td className="p-3 text-center">
                      {row.call_count ? (
                        <Badge className="border-cyan-500/40 bg-cyan-500/10 text-cyan-400">{row.call_count}</Badge>
                      ) : <span className="text-muted-foreground/40">-</span>}
                    </td>
                    <td className="p-3 text-center">
                      {row.ipdr_count ? (
                        <Badge className="border-violet-500/40 bg-violet-500/10 text-violet-400">{row.ipdr_count}</Badge>
                      ) : <span className="text-muted-foreground/40">-</span>}
                    </td>
                    {riskAnnotate && (
                      <td className="p-3">
                        {typeof row.risk_score === "number" ? (
                          <span className="font-bold" style={{ color: riskStyle(row.risk_score).color }}>
                            {row.risk_score.toFixed(1)}
                          </span>
                        ) : <span className="text-muted-foreground/40">-</span>}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border p-3 text-sm">
          <span className="text-muted-foreground">Page {page} of {pages} · {total.toLocaleString()} records</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}>
              Previous
            </Button>
            <Button variant="outline" size="sm" disabled={offset + PAGE_SIZE >= total} onClick={() => setOffset(offset + PAGE_SIZE)}>
              Next
            </Button>
          </div>
        </div>
      </div>

      {/* ---------- CENTRALIZED EXPLAINABILITY MODAL ---------- */}
      <AnimatePresence>
        {selectedRow && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-center justify-center p-4"
          >
            <div className="absolute inset-0 bg-background/70 backdrop-blur-md" onClick={() => setSelectedRow(null)} />
            <motion.div
              initial={{ scale: 0.92, y: 16 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.94, y: 10 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="relative max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-border/80 bg-card shadow-2xl shadow-black/60"
            >
              {/* header */}
              <div className="flex items-start justify-between gap-3 border-b border-border p-5">
                <div>
                  <div className="flex items-center gap-2">
                    <AlertTriangle className="size-5 text-red-500" />
                    <p className="font-mono text-sm font-semibold">{selectedRow.transaction_id}</p>
                  </div>
                  <p className="mt-1 text-xs font-medium text-emerald-400">
                    {selectedRow.account_name ? `${selectedRow.account_name} (${selectedRow.account_no})` : selectedRow.account_no} · {selectedRow.bank || "Bank"}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={copyAlert}
                    title="Copy details"
                    className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {copied ? <Check className="size-4 text-emerald-400" /> : <Copy className="size-4" />}
                  </button>
                  <button
                    onClick={() => setSelectedRow(null)}
                    aria-label="Close"
                    className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <X className="size-4" />
                  </button>
                </div>
              </div>

              {/* risk summary */}
              <div className="grid grid-cols-3 gap-3 p-5">
                {[
                  { label: "Risk Score", value: selectedRow.risk_score ? selectedRow.risk_score.toFixed(1) : "-", color: selectedRow.risk_score ? riskStyle(selectedRow.risk_score).color : "#e2e8f0" },
                  { label: "Band", value: selectedRow.risk_band || "-", color: "#e2e8f0" },
                  { label: "Amount", value: `₹${Number(selectedRow.amount || 0).toLocaleString("en-IN")}`, color: "#e2e8f0" },
                ].map((s) => (
                  <div key={s.label} className="rounded-xl border border-border/70 bg-muted/30 p-3 text-center">
                    <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{s.label}</p>
                    <p className="mt-1 text-lg font-black" style={{ color: s.color }}>{s.value}</p>
                  </div>
                ))}
              </div>

              {/* ── Entity & Transfer Cycle Details ────────────────────────────────────── */}
              <div className="mx-5 mb-3 rounded-xl border border-border/80 bg-muted/20 p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-border/60 pb-2">
                  <p className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5">
                    <Network className="size-3.5" /> Entity & Transaction Flow Cycle
                  </p>
                  {selectedRow.mode && (
                    <Badge variant="outline" className="border-cyan-500/40 bg-cyan-500/10 text-cyan-300 font-mono text-[10px]">
                      {selectedRow.mode}
                    </Badge>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {/* Sender / Source Entity */}
                  <div className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3 space-y-1">
                    <p className="text-[10px] uppercase font-bold text-slate-400">From (Sender Entity)</p>
                    <p className="text-sm font-semibold text-slate-100 break-all">
                      {selectedRow.account_name || "Sender Customer"}
                    </p>
                    <div className="text-xs text-slate-400 font-mono space-y-0.5 pt-1">
                      <p>Acc: <span className="text-slate-200">{selectedRow.account_no || "N/A"}</span></p>
                      <p>Phone: <span className="text-cyan-300">{selectedRow.sender_phone || "Not linked"}</span></p>
                      {selectedRow.bank && <p>Bank: <span className="text-slate-300">{selectedRow.bank}</span></p>}
                    </div>
                  </div>

                  {/* Receiver / Cycle Destination Entity */}
                  <div className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3 space-y-1">
                    <p className="text-[10px] uppercase font-bold text-amber-400">To (Sent Cycle Destination)</p>
                    <p className="text-sm font-semibold text-slate-100 break-all">
                      {selectedRow.counterparty_name || "Destination Account"}
                    </p>
                    <div className="text-xs text-slate-400 font-mono space-y-0.5 pt-1">
                      <p>Acc: <span className="text-slate-200">{selectedRow.receiver_account || selectedRow.counterparty_name || "N/A"}</span></p>
                      <p>Phone: <span className="text-cyan-300">{selectedRow.receiver_phone || "Not linked"}</span></p>
                      {selectedRow.counterparty_bank && <p>Bank: <span className="text-slate-300">{selectedRow.counterparty_bank}</span></p>}
                    </div>
                  </div>
                </div>

                {/* Connected Phone Numbers Banner */}
                {(selectedRow.sender_phone || selectedRow.receiver_phone || (selectedRow.linked_calls && selectedRow.linked_calls.length > 0)) && (
                  <div className="flex items-center gap-2 rounded-lg border border-cyan-500/20 bg-cyan-950/20 px-3 py-2 text-xs text-cyan-300">
                    <PhoneCall className="size-3.5 shrink-0 text-cyan-400" />
                    <span>
                      Connected Phone Links:{" "}
                      <strong className="font-mono text-cyan-200">
                        {[selectedRow.sender_phone, selectedRow.receiver_phone, ...(selectedRow.linked_calls || []).map((c: any) => c.phone)].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i).join(" ↔ ")}
                      </strong>
                    </span>
                  </div>
                )}
              </div>

              {/* plain-English why */}
              {selectedRow.explain_plain && (
                <div className="px-5 pb-3">
                  <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-emerald-500">
                    <AlertTriangle className="size-3.5" /> Why this is suspicious — plain English
                  </p>
                  <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3 text-sm leading-relaxed text-foreground/90">
                    {selectedRow.explain_plain}
                  </div>
                </div>
              )}

              {/* rules fired */}
              {selectedRow.rules_fired && (
                <div className="px-5 pb-3">
                  <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-red-500">
                    <Activity className="size-3.5" /> AI Rationale — Rules Fired
                  </p>
                  <div className="space-y-2">
                    {(selectedRow.rules_fired.replace(/[\[\]']/g, "").split(",").map((r) => r.trim()).filter(Boolean)).length === 0 ? (
                      <p className="text-sm text-muted-foreground">No rules fired.</p>
                    ) : (
                      selectedRow.rules_fired.replace(/[\[\]']/g, "").split(",").map((r) => r.trim()).filter(Boolean).map((rule, i) => (
                        <div key={i} className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-950/20 p-2.5 text-sm text-red-400">
                          <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                          <span>{rule}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              )}

              {selectedRow.ncrp_states && selectedRow.ncrp_states.length > 0 && (
                <div className="px-5 pb-3">
                  <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-amber-500">
                    <PhoneCall className="size-3.5" /> NCRP States
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedRow.ncrp_states.map((s) => (
                      <Badge key={s} variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-400">{s}</Badge>
                    ))}
                  </div>
                </div>
              )}

              {/* STR */}
              <div className="border-t border-border p-5">
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-emerald-500">
                  Suspicious Transaction Report
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent("pdf:transaction", { detail: selectedRow.transaction_id }));
                      toast.success("Transaction STR visual generation started.");
                    }}
                  >
                    <FileText className="mr-1 size-4" /> Transaction STR
                  </Button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {panelPayload && (
        <InvestigationPanel
          data={panelPayload}
          onClose={() => setPanelPayload(null)}
          onEntitySelect={openDossier}
        />
      )}
      {panelBusy && (
        <p className="fixed bottom-4 left-1/2 -translate-x-1/2 rounded-full border border-border bg-background px-4 py-2 text-xs text-muted-foreground animate-pulse z-50">
          Loading intelligence dossier...
        </p>
      )}
    </div>
  );
});
