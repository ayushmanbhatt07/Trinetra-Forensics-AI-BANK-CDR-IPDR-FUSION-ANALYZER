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
  Download, AlertTriangle, Check, Copy, PhoneCall, Loader2, Clock, Search
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

  const filteredAlerts = alerts.filter((a) => {
    if (!searchQuery) return true;
    const q = searchQuery.toLowerCase();
    const nameStr = String(a.customer_name || (a as any).account_name || (a as any).counterparty_name || (a as any).holder || "");
    const phoneStr = String(a.customer_phone || "");
    return (
      (a.transaction_id || "").toLowerCase().includes(q) ||
      (a.sender_customer_id || "").toLowerCase().includes(q) ||
      nameStr.toLowerCase().includes(q) ||
      phoneStr.toLowerCase().includes(q)
    );
  });

  const exportCSV = () => {
    if (filteredAlerts.length === 0) {
      toast.error("No anomalies to export.");
      return;
    }
    const headers = ["Txn ID", "Cust ID", "Name", "Phone No", "Date/Time", "Amount", "Mode", "Risk", "Band"];
    const rows = filteredAlerts.map((a) => {
      const nameStr = String(a.customer_name || (a as any).account_name || (a as any).counterparty_name || (a as any).holder || "");
      const phoneStr = String(a.customer_phone || "");
      const dateTimeStr = a.date ? `${a.date} ${a.time ?? ""}`.trim() : "";
      return [
        a.transaction_id || "",
        a.sender_customer_id || "",
        nameStr,
        phoneStr,
        dateTimeStr,
        a.amount_usd || "",
        a.mode || "",
        a.risk_score || "",
        a.risk_band || ""
      ];
    });
    const csvContent = [
      headers.join(","),
      ...rows.map(r => r.map(c => `"${String(c).replace(/"/g, '""')}"`).join(","))
    ].join("\n");
    
    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `anomalies_export_${new Date().getTime()}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toast.success("Anomalies exported successfully.");
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
          <div className="min-w-[200px] flex-1">
            <p className="text-sm font-semibold text-red-500">Anomaly Detection Feed</p>
            <p className="text-xs text-muted-foreground">
              {filteredAlerts.length} highest-risk transactions · click a row for full explainability + STR
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative w-64 max-w-sm">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input
                placeholder="Search Txn ID, Name, Phone..."
                className="pl-9 h-9 bg-background/50 text-xs"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>
            <Button variant="outline" size="sm" onClick={exportCSV}>
              <Download className="mr-1 size-4" /> Export CSV
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
            <div className="flex-1 rounded-xl border border-border bg-card/60 p-4 flex flex-col justify-center items-center text-center">
              <Activity className="size-8 text-violet-400 mb-2 opacity-80" />
              <h4 className="font-semibold text-sm text-foreground/90">Multi-Transaction Heatmap</h4>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                {selectedRows.size} transactions selected. The density heatmap visualizes chronological concentration and frequency outliers.
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-1">
                {Array.from({ length: 28 }).map((_, i) => (
                  <div key={i} className="size-3 rounded-sm bg-violet-500/20" style={{ opacity: 0.3 + (i % 5) * 0.15 }} />
                ))}
              </div>
            </div>
            <div className="flex-1 rounded-xl border border-border bg-card/60 p-4 flex flex-col justify-center items-center text-center">
              <Database className="size-8 text-cyan-400 mb-2 opacity-80" />
              <h4 className="font-semibold text-sm text-foreground/90">Relationship Model</h4>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                Analyzing common counter-parties and shared IP/IMEI intersections across {selectedRows.size} selections.
              </p>
              <Button
                variant="outline"
                size="sm"
                className="mt-4 border-cyan-500/30 text-cyan-400 hover:bg-cyan-950/20"
                onClick={() => {
                  window.dispatchEvent(new CustomEvent("nav:section", { detail: "network" }));
                }}
              >
                Inspect in Network Graph
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
                  <p className="mt-1 text-xs text-muted-foreground">
                    {selectedAlert.sender_customer_id} · {selectedAlert.bank}
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
