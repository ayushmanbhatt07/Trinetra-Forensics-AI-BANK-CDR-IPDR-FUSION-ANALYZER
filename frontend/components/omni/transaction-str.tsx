"use client";

import React, { useEffect, useState, useRef } from "react";
import {
  X,
  Download,
  ShieldAlert,
  Activity,
  RefreshCw,
  FileText,
  AlertTriangle,
  ArrowRight,
  User,
  CreditCard,
  Phone,
  Radio,
  CheckCircle2,
  Copy,
  Check,
  Building,
  TrendingUp,
  ExternalLink,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";

interface TransactionSTRReportProps {
  transactionId: string;
  onClose: () => void;
}

export function TransactionSTRReport({ transactionId, onClose }: TransactionSTRReportProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setLoading(true);
    setError("");

    api
      .transactionEvidence(transactionId)
      .then((res) => {
        setData(res);
      })
      .catch((err) => {
        // Fallback to copilotEntityDetails if evidence endpoint fails
        api
          .copilotEntityDetails(transactionId, true)
          .then((fallbackRes) => {
            setData({ fallback: true, raw: fallbackRes });
          })
          .catch((e) => {
            setError(err?.message || e?.message || "Failed to compile transaction investigation report.");
          });
      })
      .finally(() => setLoading(false));
  }, [transactionId]);

  const handleDownloadPDF = async () => {
    try {
      setDownloading(true);
      toast.info("Compiling high-resolution forensic PDF report...");
      await api.transactionReport(transactionId);
      toast.success("Forensic STR Report PDF downloaded successfully!");
    } catch (e: any) {
      toast.error(e?.message || "Failed to download PDF report.");
    } finally {
      setDownloading(false);
    }
  };

  const handleCopyNarrative = (text: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopied(true);
    toast.success("STR Narrative copied to clipboard!");
    setTimeout(() => setCopied(false), 2500);
  };

  if (loading) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-md" onClick={onClose}>
        <div className="flex flex-col items-center p-8 bg-slate-900 border border-slate-700/80 rounded-2xl shadow-2xl" onClick={(e) => e.stopPropagation()}>
          <RefreshCw className="size-8 text-cyan-400 animate-spin mb-4" />
          <h3 className="text-base font-semibold font-mono text-slate-100">Compiling Forensic STR Dossier...</h3>
          <p className="text-xs text-slate-400 mt-2">Correlating multi-stage risk, funds flow & telecom linkages</p>
          <div className="mt-4 flex items-center gap-2">
            <span className="inline-block size-2 rounded-full bg-cyan-400 animate-pulse" />
            <span className="text-[11px] font-mono text-cyan-300">Transaction ID: {transactionId}</span>
          </div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-md" onClick={onClose}>
        <div className="p-6 bg-slate-900 border border-rose-500/40 rounded-2xl shadow-2xl max-w-md w-full" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-3 text-rose-400 mb-3">
            <ShieldAlert className="size-6 shrink-0" />
            <h3 className="font-semibold text-base">Investigation Report Error</h3>
          </div>
          <p className="text-xs text-slate-300 mb-6">{error || "Could not retrieve transaction forensic evidence."}</p>
          <Button onClick={onClose} className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200">
            Close
          </Button>
        </div>
      </div>
    );
  }

  const ev = data.evidence || {};
  const nar = data.narrative || {};
  const primary = ev.primary_transaction || {};
  const baseline = ev.behavioral_baseline || {};
  const flow = ev.funds_flow || {};
  const counterparties = ev.counterparties || [];
  const cdrIpdr = ev.cdr_ipdr || {};
  const redFlags = ev.red_flags || [];
  const typologies = ev.typologies || [];
  const risk = ev.risk_assessment || {};
  const findings = nar.forensic_findings || [];
  const recs = nar.recommended_actions || {};
  const evidenceLedger = ev.evidence_ledger || [];

  const riskBand = risk.risk_band || "MEDIUM";
  const riskScore = risk.overall_score || 0;

  const getRiskBadgeColor = (band: string) => {
    switch (band) {
      case "CRITICAL":
      case "SEVERE":
        return "bg-rose-500/20 text-rose-400 border-rose-500/40";
      case "HIGH":
        return "bg-amber-500/20 text-amber-400 border-amber-500/40";
      case "MEDIUM":
        return "bg-sky-500/20 text-sky-400 border-sky-500/40";
      default:
        return "bg-emerald-500/20 text-emerald-400 border-emerald-500/40";
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 sm:p-6" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.96 }}
        transition={{ duration: 0.2 }}
        className="w-full max-w-5xl h-[92vh] bg-slate-950 border border-slate-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header Bar */}
        <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90 backdrop-blur-md shrink-0">
          <div className="flex items-center gap-3">
            <div className="size-9 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400">
              <FileText className="size-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold font-mono text-slate-100">STR Investigation Report</h2>
                <Badge variant="outline" className={`font-mono text-[10px] ${getRiskBadgeColor(riskBand)}`}>
                  {riskBand} ({riskScore}/100)
                </Badge>
              </div>
              <p className="text-[11px] font-mono text-slate-400">
                Ref: {transactionId} &nbsp;|&nbsp; Case: {ev.case?.case_id || "CASE-STR"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Button
              onClick={handleDownloadPDF}
              disabled={downloading}
              size="sm"
              className="bg-cyan-600 hover:bg-cyan-500 text-white font-mono text-xs shadow-lg shadow-cyan-900/30 flex items-center gap-1.5"
            >
              {downloading ? <RefreshCw className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
              {downloading ? "Generating PDF..." : "Download Forensic PDF"}
            </Button>
            <button
              onClick={onClose}
              className="size-8 rounded-full bg-slate-800 hover:bg-slate-700 flex items-center justify-center text-slate-400 hover:text-slate-200 transition-colors"
            >
              <X className="size-4" />
            </button>
          </div>
        </header>

        {/* Scrollable Report Body */}
        <div className="flex-1 overflow-y-auto p-6 sm:p-8 space-y-6">
          {/* Classification Banner */}
          <div className="p-2.5 rounded-lg bg-rose-950/30 border border-rose-500/30 text-center">
            <p className="text-[10px] font-mono font-bold tracking-widest text-rose-400 uppercase">
              CONFIDENTIAL // LAW ENFORCEMENT SENSITIVE // SUSPICIOUS TRANSACTION REPORT (STR)
            </p>
          </div>

          {/* 1. Executive Intelligence Summary Callout */}
          <div className="p-5 rounded-xl bg-gradient-to-br from-cyan-950/40 via-slate-900/70 to-slate-900/40 border border-cyan-500/30 shadow-lg">
            <div className="flex items-center gap-2 mb-2">
              <span className="inline-block size-2 rounded-full bg-cyan-400" />
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-cyan-400">
                1. Executive Intelligence Summary
              </h3>
            </div>
            <p className="text-sm leading-relaxed text-slate-200">
              {nar.executive_summary || "Automated multi-stage forensic analysis complete."}
            </p>
          </div>

          {/* 2. Primary Suspicious Transaction Profile */}
          <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
            <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
              <CreditCard className="size-3.5 text-cyan-400" /> 2. Primary Suspicious Transaction Profile
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Transaction ID</span>
                <p className="text-xs font-mono font-bold text-slate-200 mt-0.5 truncate">{primary.transaction_id || transactionId}</p>
              </div>
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Amount</span>
                <p className="text-sm font-mono font-bold text-emerald-400 mt-0.5">
                  ₹ {Number(primary.amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 })}
                </p>
              </div>
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Type / Mode</span>
                <p className="text-xs font-mono font-bold text-slate-200 mt-0.5">
                  {primary.transaction_type || "Debit"} · {primary.mode || "UPI"}
                </p>
              </div>
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Date / Time</span>
                <p className="text-xs font-mono font-bold text-slate-200 mt-0.5">{primary.timestamp || "N/A"}</p>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Sender Account</span>
                <p className="text-xs font-mono font-bold text-slate-200 mt-0.5 truncate">{primary.sender_account || "N/A"}</p>
              </div>
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Receiver Account</span>
                <p className="text-xs font-mono font-bold text-cyan-300 mt-0.5 truncate">{primary.receiver_account || "N/A"}</p>
              </div>
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Counterparty</span>
                <p className="text-xs font-mono font-bold text-slate-200 mt-0.5 truncate">{primary.receiver_customer || "Unknown"}</p>
              </div>
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-500">Reporting Bank</span>
                <p className="text-xs font-mono font-bold text-slate-200 mt-0.5 truncate">{primary.bank || "Bank Ledger"}</p>
              </div>
            </div>

            {primary.narration && (
              <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800">
                <span className="text-[10px] font-mono uppercase text-slate-500">Narration / Remarks</span>
                <p className="text-xs font-mono text-slate-300 mt-0.5">{primary.narration}</p>
              </div>
            )}
          </div>

          {/* 3. Behavioral Baseline & Profile Deviation */}
          {baseline.available && (
            <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <TrendingUp className="size-3.5 text-amber-400" /> 3. Behavioral Baseline & Deviation Metrics
                </h3>
                <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-300 font-mono text-[10px]">
                  {baseline.deviation_ratio}x Median Deviation
                </Badge>
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-500">Historical Avg</span>
                  <p className="text-xs font-mono font-bold text-slate-200 mt-0.5">₹ {baseline.avg_transaction?.toLocaleString()}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-500">Historical Median</span>
                  <p className="text-xs font-mono font-bold text-slate-200 mt-0.5">₹ {baseline.median_transaction?.toLocaleString()}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-500">Historical Max Leg</span>
                  <p className="text-xs font-mono font-bold text-slate-200 mt-0.5">₹ {baseline.max_transaction?.toLocaleString()}</p>
                </div>
                <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80">
                  <span className="text-[10px] font-mono uppercase text-slate-500">Percentile Rank</span>
                  <p className="text-xs font-mono font-bold text-rose-400 mt-0.5">{baseline.percentile}th Percentile</p>
                </div>
              </div>
            </div>
          )}

          {/* 4. Funds Flow Reconstruction */}
          {flow.sequence && flow.sequence.length > 0 && (
            <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                  <Activity className="size-3.5 text-cyan-400" /> 4. Funds Flow Reconstruction & Hop Sequence
                </h3>
                <span className="text-[11px] font-mono text-slate-400">
                  Retention: <strong className="text-cyan-300">{flow.retention_pct}%</strong> · Outflows: ₹ {flow.total_outflow?.toLocaleString()}
                </span>
              </div>
              <div className="space-y-2">
                {flow.sequence.slice(0, 6).map((step: any, idx: number) => (
                  <div
                    key={idx}
                    className={`flex items-center justify-between p-2.5 rounded-lg border text-xs font-mono ${
                      step.direction === "SUSPICIOUS_TRANSACTION"
                        ? "bg-rose-950/40 border-rose-500/40 text-rose-200 font-bold"
                        : "bg-slate-950/40 border-slate-800/80 text-slate-300"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-slate-500 text-[10px]">{step.time}</span>
                      <Badge
                        variant="outline"
                        className={`text-[9px] ${
                          step.direction === "SUSPICIOUS_TRANSACTION"
                            ? "bg-rose-500/20 text-rose-300 border-rose-500/40"
                            : step.direction === "INFLOW"
                            ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                            : "bg-cyan-500/20 text-cyan-300 border-cyan-500/40"
                        }`}
                      >
                        {step.direction}
                      </Badge>
                      <span className="truncate max-w-xs">{step.entity}</span>
                    </div>
                    <span className="font-bold">₹ {Number(step.amount || 0).toLocaleString("en-IN")}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 5. Red Flags & Anomaly Indicators */}
          {redFlags.length > 0 && (
            <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <AlertTriangle className="size-3.5 text-rose-400" /> 5. Detected Forensic Red Flags ({redFlags.length})
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {redFlags.map((rf: any, i: number) => (
                  <div key={i} className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-bold text-slate-200">{rf.indicator}</span>
                      <Badge variant="outline" className={`text-[9px] ${getRiskBadgeColor(rf.severity)}`}>
                        {rf.severity}
                      </Badge>
                    </div>
                    <p className="text-[11px] text-slate-400">{rf.evidence}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 6. AML Crime Typologies */}
          {typologies.length > 0 && (
            <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <ShieldAlert className="size-3.5 text-amber-400" /> 6. AML / Financial Crime Typologies
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {typologies.map((typ: any, i: number) => (
                  <div key={i} className="p-3 rounded-lg bg-slate-950/60 border border-slate-800/80 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-bold text-amber-300">{typ.typology}</span>
                      <Badge variant="outline" className="border-amber-500/40 bg-amber-500/10 text-amber-400 text-[9px]">
                        {typ.confidence} Confidence
                      </Badge>
                    </div>
                    <p className="text-[11px] text-slate-300">{typ.evidence}</p>
                    <p className="text-[10px] text-slate-500 italic">{typ.basis}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 7. Formal STR / SAR Narrative (WHO / WHAT / WHEN / WHERE / WHY / HOW) */}
          <div className="p-5 rounded-xl bg-slate-900/70 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <FileText className="size-3.5 text-cyan-400" /> 7. Formal STR Narrative (FIU-IND Submission Standard)
              </h3>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleCopyNarrative(nar.str_narrative)}
                className="h-7 text-xs font-mono border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center gap-1"
              >
                {copied ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
                {copied ? "Copied" : "Copy Narrative"}
              </Button>
            </div>
            <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 font-mono text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
              {nar.str_narrative || "Narrative compiled."}
            </div>
          </div>

          {/* 8. Recommended Actions */}
          {recs && (
            <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
              <h3 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300 flex items-center gap-2">
                <CheckCircle2 className="size-3.5 text-emerald-400" /> 8. Recommended Law Enforcement Actions
              </h3>
              <div className="space-y-3">
                {recs.immediate && recs.immediate.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[11px] font-mono font-bold text-rose-400 uppercase">Immediate Actions</span>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {recs.immediate.map((r: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-rose-400 shrink-0">•</span> {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {recs.investigative && recs.investigative.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[11px] font-mono font-bold text-amber-400 uppercase">In-Depth Tracing</span>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {recs.investigative.map((r: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-amber-400 shrink-0">•</span> {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                {recs.monitoring && recs.monitoring.length > 0 && (
                  <div className="space-y-1">
                    <span className="text-[11px] font-mono font-bold text-cyan-400 uppercase">Ongoing Monitoring</span>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {recs.monitoring.map((r: string, i: number) => (
                        <li key={i} className="flex items-start gap-2">
                          <span className="text-cyan-400 shrink-0">•</span> {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}
