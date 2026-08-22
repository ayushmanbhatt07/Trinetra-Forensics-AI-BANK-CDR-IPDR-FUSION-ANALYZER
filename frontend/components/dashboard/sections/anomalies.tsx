"use client";

/**
 * Anomaly Detection feed — standalone section (anomalies ONLY).
 * Full-width alert table, row click = blurred background + centralized
 * explainability card with STR generation.
 *
 * SYNCHRONIZATION FIX:
 * Same pattern as fused.tsx — do NOT bail out while pipeline context is loading.
 * Detect isAnomaliesReady false→true transition and auto-refetch.
 * Distinguish loading / processing / empty / no-data states clearly.
 */
import React, { useState, useEffect, useRef } from "react";
import {
  ShieldAlert, FileText, X, Activity, Database,
  Download, AlertTriangle, Check, Copy, PhoneCall, Loader2, Clock, Search, Network
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Checkbox } from "@/components/ui/checkbox";
import { motion, AnimatePresence } from "framer-motion";
import { InvestigationPanel } from "@/components/dashboard/investigation-panel";
import { api, type Alert, isPipelineNotReady } from "@/lib/api";
import { usePipeline } from "@/lib/pipeline-context";

const riskStyle = (score: number) => {
  if (score >= 86) return { color: "#f43f5e", bg: "bg-rose-500/10 border-rose-500/40" };
  if (score >= 71) return { color: "#fb923c", bg: "bg-orange-500/10 border-orange-500/40" };
  if (score >= 51) return { color: "#facc15", bg: "bg-yellow-500/10 border-yellow-500/40" };
  if (score >= 26) return { color: "#38bdf8", bg: "bg-sky-500/10 border-sky-500/40" };
  return { color: "#34d399", bg: "bg-emerald-500/10 border-emerald-500/40" };
};

let globalAlertsCache: { pipelineId: string | null; alerts: Alert[] } | null = null;
let globalAlertsPromise: Promise<Alert[]> | null = null;

export const clearAlertsCache = () => {
  globalAlertsCache = null;
  globalAlertsPromise = null;
};

export const prefetchAlerts = (pipelineId?: string | null, force = false): Promise<Alert[]> => {
  if (!force && globalAlertsCache && globalAlertsCache.pipelineId === (pipelineId || null)) {
    return Promise.resolve(globalAlertsCache.alerts);
  }
  if (!force && globalAlertsPromise) return globalAlertsPromise;

  globalAlertsPromise = api.alerts(50, 200)
    .then((res) => {
      const list = res.results || [];
      globalAlertsCache = { pipelineId: pipelineId || null, alerts: list };
      globalAlertsPromise = null;
      return list;
    })
    .catch((err) => {
      globalAlertsPromise = null;
      throw err;
    });
  return globalAlertsPromise;
};

const getRulesList = (rules: unknown): string[] => {
  if (Array.isArray(rules)) return rules.map(String).filter(Boolean);
  if (typeof rules === "string") {
    return rules.replace(/[\[\]']/g, "").split(",").map((r) => r.trim()).filter(Boolean);
  }
  return [];
};

export const AnomaliesSection = React.memo(function AnomaliesSection() {
  const [alerts, setAlerts] = useState<Alert[]>(() => globalAlertsCache?.alerts || []);
  const [searchQuery, setSearchQuery] = useState("");
  const [alertsLoading, setAlertsLoading] = useState<boolean>(false);
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [selectedRows, setSelectedRows] = useState<Set<string>>(new Set());
  const [copied, setCopied] = useState(false);
  const [panelPayload, setPanelPayload] = useState<any>(null);
  const [panelBusy, setPanelBusy] = useState(false);
  const [fetchKey, setFetchKey] = useState(0);

  const { isAnomaliesReady, loading: pipelineLoading, pipeline } = usePipeline();

  // Calculate multi-selection risk heatmap analytics
  const selectedAlertsList = React.useMemo(() => {
    return alerts.filter(a => selectedRows.has(a.transaction_id));
  }, [alerts, selectedRows]);

  const heatmapData = React.useMemo(() => {
    if (selectedAlertsList.length === 0) return { hourly: [], banks: [], totalVol: 0, maxRisk: 0 };

    const hourBins = Array.from({ length: 24 }, (_, h) => ({ hour: h, count: 0, maxRisk: 0, vol: 0 }));
    const bankSet = new Set<string>();
    let totalVol = 0;
    let maxRisk = 0;

    selectedAlertsList.forEach(a => {
      const amt = Number(a.amount_usd) || 0;
      const risk = Number(a.risk_score) || 0;
      totalVol += amt;
      if (risk > maxRisk) maxRisk = risk;

      if (a.bank) bankSet.add(a.bank);
      if ((a as any).counterparty_bank) bankSet.add((a as any).counterparty_bank);

      let hour = 12;
      if (a.time) {
        const parts = a.time.split(":");
        if (parts.length > 0 && !isNaN(parseInt(parts[0]))) {
          hour = parseInt(parts[0], 10) % 24;
        }
      }
      hourBins[hour].count += 1;
      hourBins[hour].vol += amt;
      if (risk > hourBins[hour].maxRisk) hourBins[hour].maxRisk = risk;
    });

    return {
      hourly: hourBins,
      banks: Array.from(bankSet),
      totalVol,
      maxRisk
    };
  }, [selectedAlertsList]);

  const handleInspectSelectedNetwork = () => {
    const selectedIds = Array.from(selectedRows);
    try {
      sessionStorage.setItem("network_selected_entities", JSON.stringify(selectedIds));
    } catch (e) {}
    window.dispatchEvent(new CustomEvent("nav:network_filter", { detail: { selectedIds } }));
    window.dispatchEvent(new CustomEvent("nav:section", { detail: "network" }));
    toast.success(`Opening cross-bank network graph for ${selectedIds.length} selected transactions.`);
  };

  // Clear cache whenever dataset_id changes
  useEffect(() => {
    clearAlertsCache();
    setFetchKey((k) => k + 1);
  }, [pipeline?.dataset_id]);

  const openDossier = async (kind: string, value: string) => {
    if (!value) return;
    setPanelBusy(true);
    try {
      const info = await api.dossier(kind, value);
      setPanelPayload({ type: "entity", info });
    } catch (e: any) {
      if (e.status !== 409) toast.error(`No dossier found for ${kind} ${value}`);
    } finally {
      setPanelBusy(false);
    }
  };

  // Primary data fetch effect
  useEffect(() => {
    let isMounted = true;

    if (!isAnomaliesReady) {
      setAlertsLoading(false);
      return;
    }

    // Check if cache matches current pipeline job
    if (globalAlertsCache && globalAlertsCache.pipelineId === (pipeline?.job_id || null)) {
      setAlerts(globalAlertsCache.alerts);
      setAlertsLoading(false);
      return;
    }

    setAlertsLoading(true);
    prefetchAlerts(pipeline?.job_id, true)
      .then((list) => {
        if (!isMounted) return;
        setAlerts(list);
      })
      .catch((error) => {
        if (!isMounted) return;
        const err = error as { status?: number };
        if (err.status !== 409 && err.status !== 425 && !isPipelineNotReady(error)) {
          toast.error("Failed to load anomaly alerts.");
        }
        setAlerts([]);
      })
      .finally(() => {
        if (isMounted) setAlertsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isAnomaliesReady, pipeline?.status, pipeline?.job_id, pipeline?.dataset_id, fetchKey]);

  // Listen for pipeline stage transition events
  useEffect(() => {
    const handleReady = () => {
      clearAlertsCache();
      setFetchKey((k) => k + 1);
    };
    window.addEventListener("pipeline:anomalies_ready", handleReady);
    return () => window.removeEventListener("pipeline:anomalies_ready", handleReady);
  }, []);

  const downloadSTR = async () => {
    try {
      await api.downloadReport();
      toast.success("STR PDF generation started.");
    } catch (e) {
      toast.error((e as { message?: string })?.message ?? "Failed to generate STR PDF.");
    }
  };

  const copyAlert = () => {
    if (!selectedAlert) return;
    const scoreVal = (Number(selectedAlert.risk_score) || 0).toFixed(1);
    const rulesStr = getRulesList(selectedAlert.rules_fired || (selectedAlert as any).rules).join(", ");
    navigator.clipboard?.writeText(
      `${selectedAlert.transaction_id}\t${selectedAlert.sender_customer_id}\t₹${Number(selectedAlert.amount_usd) || 0}\trisk ${scoreVal}\n${rulesStr}`
    );
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const [riskFilter, setRiskFilter] = useState<string>("ALL");

  const filteredAlerts = React.useMemo(() => {
    let list = alerts;
    if (riskFilter !== "ALL") {
      if (riskFilter === "CRITICAL") list = list.filter((a) => (Number(a.risk_score) || 0) >= 86);
      else if (riskFilter === "HIGH") list = list.filter((a) => (Number(a.risk_score) || 0) >= 71 && (Number(a.risk_score) || 0) < 86);
      else if (riskFilter === "ELEVATED") list = list.filter((a) => (Number(a.risk_score) || 0) >= 51 && (Number(a.risk_score) || 0) < 71);
      else if (riskFilter === "MEDIUM") list = list.filter((a) => (Number(a.risk_score) || 0) < 51);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter((a) => {
        const nameStr = String(a.customer_name || (a as any).account_name || (a as any).counterparty_name || (a as any).holder || "");
        const phoneStr = String(a.customer_phone || "");
        const bankStr = String(a.bank || (a as any).counterparty_bank || "");
        const modeStr = String(a.mode || "");
        return (
          (a.transaction_id || "").toLowerCase().includes(q) ||
          (a.sender_customer_id || "").toLowerCase().includes(q) ||
          nameStr.toLowerCase().includes(q) ||
          phoneStr.toLowerCase().includes(q) ||
          bankStr.toLowerCase().includes(q) ||
          modeStr.toLowerCase().includes(q)
        );
      });
    }
    return list;
  }, [alerts, riskFilter, searchQuery]);

  const exportAlertsExcel = async () => {
    const t = toast.loading("Preparing Excel Export...");
    try {
      await api.alertsExport(50, 50000);
      toast.success("Excel export downloaded.", { id: t });
    } catch (e) {
      toast.error((e as { message?: string })?.message ?? "Failed to export Excel.", { id: t });
    }
  };

  // Determine what empty-state message to show
  const renderEmptyState = () => {
    if (pipelineLoading || alertsLoading) {
      return (
        <div className="p-8 text-center text-muted-foreground">
          <Loader2 className="mx-auto mb-3 size-7 animate-spin text-red-500" />
          <p className="text-sm animate-pulse">Loading anomaly detection feed...</p>
        </div>
      );
    }
    if (!isAnomaliesReady) {
      const stage = pipeline?.status ?? "IDLE";
      const isProcessing = ["PARSING", "FUSING", "FUSED_READY", "SCORING", "GRAPHS"].includes(stage);
      return (
        <div className="p-8 text-center text-muted-foreground">
          {isProcessing ? (
            <>
              <Clock className="mx-auto mb-3 size-7 text-amber-500 animate-pulse" />
              <p className="text-sm font-semibold text-amber-400">
                Anomaly detection is running — {stage}
              </p>
              <p className="mt-1 text-xs">
                Results will appear automatically when scoring completes.
                {stage === "SCORING" && " This may take a few minutes for large datasets."}
              </p>
            </>
          ) : (
            <>
              <ShieldAlert className="mx-auto mb-3 size-7 opacity-30" />
              <p className="text-sm">No anomalies above risk 50 found. Ingest data first.</p>
            </>
          )}
        </div>
      );
    }

    if (alerts.length > 0 && filteredAlerts.length === 0) {
      return (
        <div className="p-12 text-center text-muted-foreground space-y-3">
          <Search className="mx-auto size-8 opacity-30 text-amber-500" />
          <p className="text-sm font-medium text-foreground">No anomalies match your active filters</p>
          <p className="text-xs text-muted-foreground/80 max-w-sm mx-auto">
            {searchQuery ? `No alerts found containing "${searchQuery}"` : `No alerts found with risk level ${riskFilter}`}
          </p>
          <Button
            variant="outline"
            size="sm"
            onClick={() => { setRiskFilter("ALL"); setSearchQuery(""); }}
            className="text-xs"
          >
            Clear Filters
          </Button>
        </div>
      );
    }

    return (
      <div className="p-8 text-center text-muted-foreground">
        <ShieldAlert className="mx-auto mb-3 size-7 opacity-30" />
        <p className="text-sm">No anomalies above risk 50 found in the current dataset.</p>
        <p className="mt-1 text-xs text-muted-foreground/60">All transactions are within acceptable risk parameters.</p>
      </div>
    );
  };

  return (
    <div className="space-y-6 h-[calc(100vh-12rem)]">
      <div className="flex h-full flex-col rounded-xl border border-border/70 bg-card/60 backdrop-blur">
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
          <ShieldAlert className="size-5 text-red-500" />
          <div className="min-w-[180px] flex-1">
            <p className="text-sm font-semibold text-red-500">Anomaly Detection Feed</p>
            <p className="text-xs text-muted-foreground">
              {filteredAlerts.length} of {alerts.length} high-risk transactions
            </p>
          </div>

          {/* Quick Risk Band Filter Buttons */}
          <div className="flex items-center gap-1.5 bg-secondary/30 p-1 rounded-lg border border-border/40">
            {["ALL", "CRITICAL", "HIGH", "ELEVATED"].map((band) => (
              <button
                key={band}
                onClick={() => setRiskFilter(band)}
                className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                  riskFilter === band
                    ? band === "CRITICAL"
                      ? "bg-rose-500/20 text-rose-400 font-bold border border-rose-500/50"
                      : band === "HIGH"
                      ? "bg-orange-500/20 text-orange-400 font-bold border border-orange-500/50"
                      : band === "ELEVATED"
                      ? "bg-yellow-500/20 text-yellow-400 font-bold border border-yellow-500/50"
                      : "bg-primary/20 text-primary font-bold border border-primary/50"
                    : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {band}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <div className="relative w-64 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="Search Txn ID, Name, Phone..."
                className="pl-9 pr-8 h-9 bg-background/50 text-xs"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              )}
            </div>
            {(riskFilter !== "ALL" || searchQuery) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setRiskFilter("ALL"); setSearchQuery(""); }}
                className="h-9 text-xs text-muted-foreground hover:text-foreground px-2"
              >
                Reset
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={exportAlertsExcel}>
              <Download className="mr-1 size-4" /> Export XLSX
            </Button>
            <Button variant="outline" size="sm" onClick={downloadSTR}>
              <FileText className="mr-1 size-4" /> STR
            </Button>
          </div>
        </div>

        <div className="flex-1 overflow-auto relative">
          {alertsLoading && filteredAlerts.length > 0 && (
            <div className="absolute top-0 left-0 right-0 z-20 h-1 bg-red-500/20 overflow-hidden">
              <div className="h-full bg-red-500 animate-pulse w-full" />
            </div>
          )}
          {alertsLoading && filteredAlerts.length === 0 ? (
            <div className="p-8 text-center text-muted-foreground">
              <Loader2 className="mx-auto mb-3 size-7 animate-spin text-red-500" />
              <p className="text-sm animate-pulse">Loading anomaly detection feed...</p>
            </div>
          ) : filteredAlerts.length === 0 ? (
            renderEmptyState()
          ) : (
            <div className="overflow-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-muted/60 text-muted-foreground z-10">
                  <tr>
                    <th className="p-3 w-10 text-center">
                      <Checkbox
                        checked={filteredAlerts.length > 0 && selectedRows.size === filteredAlerts.length}
                        onCheckedChange={(c) => {
                          if (c) setSelectedRows(new Set(filteredAlerts.map((a) => a.transaction_id)));
                          else setSelectedRows(new Set());
                        }}
                      />
                    </th>
                    <th className="p-3 text-left font-medium min-w-[130px]">Txn ID</th>
                    <th className="p-3 text-left font-medium min-w-[120px]">Cust ID</th>
                    <th className="p-3 text-left font-medium min-w-[140px]">Name</th>
                    <th className="p-3 text-left font-medium min-w-[130px]">Phone No</th>
                    <th className="p-3 text-left font-medium min-w-[110px]">Date/Time</th>
                    <th className="p-3 text-left font-medium min-w-[120px]">Amount</th>
                    <th className="p-3 text-left font-medium min-w-[90px]">Mode</th>
                    <th className="p-3 text-left font-medium min-w-[90px]">Risk</th>
                    <th className="p-3 text-left font-medium min-w-[90px]">Band</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredAlerts.map((alert, idx) => {
                    const score = Number(alert.risk_score) || 0;
                    const rs = riskStyle(score);
                    const amt = Number(alert.amount_usd) || 0;
                    return (
                      <tr
                        key={alert.transaction_id + idx}
                        onClick={() => setSelectedAlert(alert)}
                        className="cursor-pointer border-b border-border/50 transition-colors hover:bg-muted/30 animate-in fade-in duration-200"
                      >
                        <td className="p-3 text-center" onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={selectedRows.has(alert.transaction_id)}
                            onCheckedChange={(c) => {
                              const next = new Set(selectedRows);
                              if (c) next.add(alert.transaction_id);
                              else next.delete(alert.transaction_id);
                              setSelectedRows(next);
                            }}
                          />
                        </td>
                        <td className="p-3 font-mono text-xs">{alert.transaction_id}</td>
                        <td className="p-3 font-mono text-xs">{alert.sender_customer_id}</td>
                        <td className="p-3 text-xs text-muted-foreground">
                          {alert.customer_name || (alert as any).account_name || (alert as any).counterparty_name || (alert as any).holder || "—"}
                        </td>
                        <td className="p-3 font-mono text-xs">{alert.customer_phone || "—"}</td>
                        <td className="p-3 whitespace-nowrap font-mono text-xs">
                          {alert.date ? `${alert.date} ${alert.time ?? ""}` : "—"}
                        </td>
                        <td className="p-3 font-mono">₹{amt.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</td>
                        <td className="p-3"><Badge variant="outline">{alert.mode || "—"}</Badge></td>
                        <td className="p-3">
                          <span className="font-bold" style={{ color: rs.color }}>{score.toFixed(1)}</span>
                        </td>
                        <td className="p-3">
                          <Badge variant="outline" className={rs.bg} style={{ color: rs.color }}>
                            {alert.risk_band || "SAFE"}
                          </Badge>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {selectedRows.size > 0 && (
          <div className="border-t border-border bg-muted/20 p-4 h-64 shrink-0 flex gap-4">
            {/* Multi-Transaction Risk Heatmap */}
            <div className="flex-1 rounded-xl border border-border bg-slate-950/80 p-4 flex flex-col justify-between shadow-xl">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="size-4 text-violet-400" />
                  <h4 className="font-semibold text-xs font-mono text-foreground uppercase tracking-wider">
                    Cross-Bank 24-Hour Risk Density Heatmap
                  </h4>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px] border-violet-500/40 text-violet-300 bg-violet-950/30 font-mono">
                    {selectedRows.size} Selected
                  </Badge>
                  <Badge variant="outline" className="text-[10px] border-rose-500/40 text-rose-400 bg-rose-950/30 font-mono">
                    Peak Risk: {heatmapData.maxRisk.toFixed(1)}
                  </Badge>
                </div>
              </div>

              {/* Hourly Heatmap Grid (24 Hours) */}
              <div className="my-2 space-y-1">
                <div className="grid grid-cols-24 gap-1 h-16 items-end bg-slate-900/80 p-2 rounded-lg border border-slate-800">
                  {heatmapData.hourly.map((bin) => {
                    const heightPct = bin.count > 0 ? Math.max(25, Math.min(100, (bin.count / (selectedRows.size || 1)) * 300)) : 12;
                    const bgClass = bin.maxRisk >= 70 ? "bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)] animate-pulse" 
                      : bin.maxRisk >= 50 ? "bg-amber-400" 
                      : bin.count > 0 ? "bg-cyan-500" 
                      : "bg-slate-800/40";
                    return (
                      <div
                        key={bin.hour}
                        className="group relative flex flex-col justify-end h-full rounded-xs transition-all hover:scale-110 cursor-pointer"
                      >
                        <div
                          className={`w-full rounded-xs transition-all ${bgClass}`}
                          style={{ height: `${heightPct}%` }}
                        />
                        {/* Hover Tooltip */}
                        <div className="absolute bottom-full mb-1 left-1/2 -translate-x-1/2 hidden group-hover:flex flex-col items-center z-30 pointer-events-none">
                          <div className="bg-slate-900 text-slate-100 text-[10px] font-mono px-2.5 py-1.5 rounded-md border border-slate-700 shadow-2xl whitespace-nowrap space-y-0.5">
                            <div className="font-bold text-slate-200">Hour {String(bin.hour).padStart(2, '0')}:00</div>
                            <div className="text-cyan-400">{bin.count} Txns (₹{Math.round(bin.vol).toLocaleString('en-IN')})</div>
                            {bin.maxRisk > 0 && <div className="text-rose-400 font-bold">Max Risk: {bin.maxRisk.toFixed(1)}</div>}
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
                <div className="flex justify-between text-[9px] font-mono text-slate-400 px-1">
                  <span>00:00 (Midnight)</span>
                  <span>06:00</span>
                  <span>12:00 (Noon)</span>
                  <span>18:00</span>
                  <span>23:00</span>
                </div>
              </div>

              <div className="flex items-center justify-between text-[11px] text-muted-foreground font-mono">
                <span>Selected Volume: <strong className="text-emerald-400 font-bold">₹{heatmapData.totalVol.toLocaleString('en-IN')}</strong></span>
                <span>Channels: <strong className="text-cyan-300">{heatmapData.banks.slice(0, 3).join(" ↔ ") || "Multi-Bank"}</strong></span>
              </div>
            </div>

            {/* Relationship Model & Network Inspector */}
            <div className="flex-1 rounded-xl border border-border bg-slate-950/80 p-4 flex flex-col justify-center items-center text-center shadow-xl">
              <Database className="size-7 text-cyan-400 mb-2 opacity-90 animate-pulse" />
              <h4 className="font-semibold text-xs font-mono text-foreground uppercase tracking-wider">Cross-Bank & Operator Sub-Graph</h4>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs font-mono">
                Analyzing common counterparties, shared IP, and telecom intersections across {selectedRows.size} selected anomalies.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-3 border-cyan-500/40 bg-cyan-950/40 text-cyan-300 hover:bg-cyan-600 hover:text-white shadow-lg shadow-cyan-950/50 transition-all font-mono text-xs"
                onClick={handleInspectSelectedNetwork}
              >
                <Network className="mr-1.5 size-3.5" /> Inspect in Network Graph
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* ---------- CENTRALIZED EXPLAINABILITY MODAL ---------- */}
      <AnimatePresence>
        {selectedAlert && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-center justify-center p-4"
          >
            <div className="absolute inset-0 bg-background/70 backdrop-blur-md" onClick={() => setSelectedAlert(null)} />
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
                    <p className="font-mono text-sm font-semibold">{selectedAlert.transaction_id}</p>
                  </div>
                  <p className="mt-1 text-xs font-medium text-emerald-400">
                    {selectedAlert.customer_name || selectedAlert.sender_name ? `${selectedAlert.customer_name || selectedAlert.sender_name} (${selectedAlert.sender_account || selectedAlert.account_no || selectedAlert.sender_customer_id})` : selectedAlert.sender_customer_id} · {selectedAlert.bank || "Bank"}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    onClick={copyAlert}
                    title="Copy alert"
                    className="rounded-lg p-2 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    {copied ? <Check className="size-4 text-emerald-400" /> : <Copy className="size-4" />}
                  </button>
                  <button
                    onClick={() => setSelectedAlert(null)}
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
                  { label: "Risk Score", value: (Number(selectedAlert.risk_score) || 0).toFixed(1), color: riskStyle(Number(selectedAlert.risk_score) || 0).color },
                  { label: "Band", value: selectedAlert.risk_band || "SAFE", color: "#e2e8f0" },
                  { label: "Amount", value: `₹${(Number(selectedAlert.amount_usd) || 0).toLocaleString("en-IN")}`, color: "#e2e8f0" },
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
                  {selectedAlert.mode && (
                    <Badge variant="outline" className="border-cyan-500/40 bg-cyan-500/10 text-cyan-300 font-mono text-[10px]">
                      {selectedAlert.mode}
                    </Badge>
                  )}
                </div>

                <div className="grid grid-cols-2 gap-3">
                  {/* Sender / Source Entity */}
                  <div className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3 space-y-1">
                    <p className="text-[10px] uppercase font-bold text-slate-400">From (Sender Entity)</p>
                    <p className="text-sm font-semibold text-slate-100 break-all">
                      {selectedAlert.customer_name || selectedAlert.sender_name || "Sender Customer"}
                    </p>
                    <div className="text-xs text-slate-400 font-mono space-y-0.5 pt-1">
                      <p>Acc: <span className="text-slate-200">{selectedAlert.account_no || selectedAlert.sender_account || selectedAlert.sender_customer_id || "N/A"}</span></p>
                      <p>Phone: <span className="text-cyan-300">{selectedAlert.customer_phone || selectedAlert.sender_phone || "Not linked"}</span></p>
                      {selectedAlert.bank && <p>Bank: <span className="text-slate-300">{selectedAlert.bank}</span></p>}
                    </div>
                  </div>

                  {/* Receiver / Cycle Destination Entity */}
                  <div className="rounded-lg border border-slate-700/60 bg-slate-900/60 p-3 space-y-1">
                    <p className="text-[10px] uppercase font-bold text-amber-400">To (Sent Cycle Destination)</p>
                    <p className="text-sm font-semibold text-slate-100 break-all">
                      {selectedAlert.receiver_name || selectedAlert.counterparty_name || "Destination Account"}
                    </p>
                    <div className="text-xs text-slate-400 font-mono space-y-0.5 pt-1">
                      <p>Acc: <span className="text-slate-200">{selectedAlert.receiver_account || selectedAlert.counterparty_name || "N/A"}</span></p>
                      <p>Phone: <span className="text-cyan-300">{selectedAlert.receiver_phone || "Not linked"}</span></p>
                      {selectedAlert.counterparty_bank && <p>Bank: <span className="text-slate-300">{selectedAlert.counterparty_bank}</span></p>}
                    </div>
                  </div>
                </div>

                {/* Connected Phone Numbers Banner */}
                {(selectedAlert.customer_phone || selectedAlert.sender_phone || selectedAlert.receiver_phone) && (
                  <div className="flex items-center gap-2 rounded-lg border border-cyan-500/20 bg-cyan-950/20 px-3 py-2 text-xs text-cyan-300">
                    <PhoneCall className="size-3.5 shrink-0 text-cyan-400" />
                    <span>
                      Connected Phone Links:{" "}
                      <strong className="font-mono text-cyan-200">
                        {[selectedAlert.customer_phone || selectedAlert.sender_phone, selectedAlert.receiver_phone].filter(Boolean).join(" ↔ ")}
                      </strong>
                    </span>
                  </div>
                )}
              </div>

              {/* plain-English why */}
              {selectedAlert.explain_plain && (
                <div className="px-5 pb-3">
                  <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-emerald-500">
                    <AlertTriangle className="size-3.5" /> Why this is suspicious — plain English
                  </p>
                  <div className="rounded-xl border border-emerald-500/25 bg-emerald-500/5 p-3 text-sm leading-relaxed text-foreground/90">
                    {selectedAlert.explain_plain}
                  </div>
                </div>
              )}

              {/* rules fired */}
              <div className="px-5 pb-3">
                <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-red-500">
                  <Activity className="size-3.5" /> AI Rationale — Rules Fired
                </p>
                <div className="space-y-2">
                  {getRulesList(selectedAlert.rules_fired || (selectedAlert as any).rules).length === 0 ? (
                    <p className="text-sm text-muted-foreground">No rules fired.</p>
                  ) : (
                    getRulesList(selectedAlert.rules_fired || (selectedAlert as any).rules).map((rule, i) => (
                      <div key={i} className="flex items-start gap-2 rounded-lg border border-red-500/20 bg-red-950/20 p-2.5 text-sm text-red-400">
                        <AlertTriangle className="mt-0.5 size-4 shrink-0" />
                        <span>{rule}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {Array.isArray(selectedAlert.ncrp_states) && selectedAlert.ncrp_states.length > 0 && (
                <div className="px-5 pb-3">
                  <p className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-amber-500">
                    <PhoneCall className="size-3.5" /> NCRP States
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {selectedAlert.ncrp_states.map((s) => (
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
                  <Button onClick={downloadSTR} className="bg-emerald-600 text-white hover:bg-emerald-500">
                    <FileText className="mr-1 size-4" /> Generate STR PDF
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      window.dispatchEvent(new CustomEvent("pdf:transaction", { detail: selectedAlert.transaction_id }));
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
