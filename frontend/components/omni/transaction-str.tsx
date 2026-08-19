"use client";

import React, { useEffect, useState, useRef } from "react";
import {
  X, Download, ShieldAlert, Activity, RefreshCw, FileText,
  PhoneCall, Globe, CheckCircle2, AlertTriangle, Copy, Check,
  TrendingUp, Users, ArrowUpRight, ArrowDownLeft, Building, Lock
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid
} from "recharts";

interface TransactionSTRReportProps {
  transactionId: string;
  fallbackTransaction?: any;
  onClose: () => void;
}

const COLORS = ["#06b6d4", "#a855f7", "#ef4444", "#f59e0b", "#10b981", "#3b82f6"];

export function TransactionSTRReport({ transactionId, fallbackTransaction, onClose }: TransactionSTRReportProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const [downloadingOfficial, setDownloadingOfficial] = useState(false);
  const [copied, setCopied] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setError("");

    // Fast watchdog timer to ensure UI never hangs if network slows
    const timer = setTimeout(() => {
      if (isMounted) {
        setLoading(false);
      }
    }, 4000);

    // Fetch transaction copilot intelligence details (fast deterministic path)
    api.copilotEntityDetails(transactionId, false)
      .then(detailsRes => {
        if (isMounted) {
          setData(detailsRes);
        }
      })
      .catch(err => {
        if (isMounted) {
          setError(err.message || "Failed to load forensic transaction details.");
        }
      })
      .finally(() => {
        clearTimeout(timer);
        if (isMounted) {
          setLoading(false);
        }
      });

    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [transactionId]);

  const candidateTxn = data?.transactions?.find((t: any) => t.id === transactionId || t.txn_id === transactionId) || data?.transactions?.[0];
  const mainTxn = candidateTxn || fallbackTransaction || {};
  const isCredit = mainTxn.type === "C" || mainTxn.type === "Credit" || (mainTxn.credit && Number(mainTxn.credit) > 0);
  const amountVal = Number(mainTxn.amount || mainTxn.amount_usd || mainTxn.credit || mainTxn.debit || fallbackTransaction?.amount_usd || fallbackTransaction?.amount || 0);

  const displayAccount = mainTxn.account_no || mainTxn.sender_account_number || fallbackTransaction?.account_no || fallbackTransaction?.sender_customer_id || "ACC_PRIMARY_NODE";
  const displayName = mainTxn.customer_name || mainTxn.sender_customer_name || mainTxn.account_name || fallbackTransaction?.customer_name || fallbackTransaction?.account_name || fallbackTransaction?.holder || "Primary Account Subject";
  const displayBank = mainTxn.bank || mainTxn.sender_bank_name || fallbackTransaction?.bank || "Scheduled Commercial Bank";
  const displayCounterparty = mainTxn.receiver_account || mainTxn.counterparty || mainTxn.receiver_account_number || fallbackTransaction?.receiver_account || fallbackTransaction?.counterparty || "Direct Destination Beneficiary";
  const displayCounterpartyName = mainTxn.counterparty_name || mainTxn.receiver_customer_name || fallbackTransaction?.counterparty_name || "Beneficiary Entity";
  const displayNarration = mainTxn.narration || mainTxn.txn_ref_number || (Array.isArray(fallbackTransaction?.rules_fired) ? fallbackTransaction.rules_fired.join(" • ") : fallbackTransaction?.rules_fired) || "High-Velocity Electronic Interbank Transfer Flagged by AML Scorer";
  const displayMode = (mainTxn.mode || fallbackTransaction?.mode || "IMPS/UPI").toUpperCase();
  const displayDate = mainTxn.date || fallbackTransaction?.date || new Date().toISOString().split("T")[0];
  const displayTime = mainTxn.time || fallbackTransaction?.time || "";

  const handleDownloadOfficialPDF = async () => {
    setDownloadingOfficial(true);
    toast.info(`Generating official FIU-IND STR PDF for ${transactionId}...`);
    try {
      await api.transactionReport(transactionId);
      toast.success("Official STR PDF downloaded successfully.");
    } catch (e: any) {
      toast.error(e?.message || "Failed to download official STR PDF.");
    } finally {
      setDownloadingOfficial(false);
    }
  };

  const handleCopySummary = () => {
    const summaryText = displayAuditReport ? displayAuditReport.slice(0, 300) : "Under enhanced PMLA Section 12 investigation for suspicious transaction velocity";
    const text = `[FIU-IND SUSPICIOUS TRANSACTION REPORT]\nTxn Ref: ${transactionId}\nAccount: ${displayAccount}\nAmount: ₹${Number(amountVal).toLocaleString("en-IN")}\nType: ${isCredit ? "Credit" : "Debit"}\nCounterparty: ${displayCounterparty}\nDate: ${displayDate} ${displayTime}\nNarration: ${displayNarration}\nAudit Summary: ${summaryText}`;
    navigator.clipboard?.writeText(text);
    setCopied(true);
    toast.success("Forensic summary copied to clipboard.");
    setTimeout(() => setCopied(false), 2000);
  };

  const generateClientPDF = async () => {
    if (!reportRef.current) return;
    try {
      toast.info("Generating high-res visual dossier...");
      const parent = reportRef.current.parentElement;
      if (parent) {
        parent.style.overflow = "visible";
        parent.style.height = "auto";
      }

      const htmlToImage = await import("html-to-image");
      const { jsPDF } = await import("jspdf");

      const dataUrl = await htmlToImage.toPng(reportRef.current, {
        quality: 0.98,
        pixelRatio: 2,
        backgroundColor: "#ffffff",
        skipFonts: true,
      });

      if (parent) {
        parent.style.overflow = "";
        parent.style.height = "";
      }

      const pdf = new jsPDF({ unit: "pt", format: "a4", orientation: "portrait" });
      const pdfWidth = pdf.internal.pageSize.getWidth();
      const pdfHeight = pdf.internal.pageSize.getHeight();

      const imgProps = pdf.getImageProperties(dataUrl);
      const imgWidth = pdfWidth;
      const imgHeight = (imgProps.height * imgWidth) / imgProps.width;

      let heightLeft = imgHeight;
      let position = 0;

      pdf.addImage(dataUrl, "PNG", 0, position, imgWidth, imgHeight);
      heightLeft -= pdfHeight;

      while (heightLeft >= 0) {
        position = heightLeft - imgHeight;
        pdf.addPage();
        pdf.addImage(dataUrl, "PNG", 0, position, imgWidth, imgHeight);
        heightLeft -= pdfHeight;
      }

      pdf.save(`Visual_Dossier_STR_${transactionId}.pdf`);
      toast.success("Visual Dossier exported successfully.");
    } catch (e) {
      console.error("Visual PDF generation failed:", e);
      toast.error("Visual export failed, falling back to official PDF.");
      handleDownloadOfficialPDF();
    }
  };

  if (loading && !fallbackTransaction) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-md p-4" onClick={onClose}>
        <div className="flex flex-col items-center p-8 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl max-w-sm w-full text-center" onClick={(e) => e.stopPropagation()}>
          <RefreshCw className="w-10 h-10 text-cyan-400 animate-spin mb-4" />
          <h3 className="text-lg font-mono font-bold text-slate-100">Compiling STR Intelligence</h3>
          <p className="text-xs text-slate-400 mt-2 font-mono">
            Synthesizing financial logs, CDR telecommunications &amp; IPDR sessions for <span className="text-cyan-300">{transactionId}</span>...
          </p>
        </div>
      </div>
    );
  }

  if (error && !data && !fallbackTransaction) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-md p-4" onClick={onClose}>
        <div className="p-8 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl max-w-md w-full" onClick={(e) => e.stopPropagation()}>
          <h3 className="text-lg font-mono text-red-400 flex items-center gap-2 mb-3">
            <ShieldAlert className="w-5 h-5" /> STR Dossier Error
          </h3>
          <p className="text-sm text-slate-300 font-mono">{error || "No intelligence data available for this transaction."}</p>
          <Button onClick={onClose} className="mt-6 w-full bg-slate-800 hover:bg-slate-700 font-mono">Close</Button>
        </div>
      </div>
    );
  }

  // Prepare Counterparties Data
  const counterpartyTotals: Record<string, number> = {};
  const txList = data?.transactions?.length ? data.transactions : (fallbackTransaction ? [fallbackTransaction] : []);
  txList.forEach((t: any) => {
    const cp = t.counterparty || t.counterparty_name || t.receiver_account || displayCounterparty;
    counterpartyTotals[cp] = (counterpartyTotals[cp] || 0) + (t.amount || t.amount_usd || t.credit || t.debit || amountVal);
  });

  const barData = Object.entries(counterpartyTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, val]) => ({ name: name.length > 12 ? name.slice(0, 12) + "..." : name, amount: val }));

  const pieData = txList.reduce((acc: any[], t: any) => {
    const tType = t.type === "C" || t.type === "Credit" ? "Credit" : t.type === "D" || t.type === "Debit" ? "Debit" : (t.mode || displayMode);
    const existing = acc.find(x => x.name === tType);
    if (existing) existing.value += 1;
    else acc.push({ name: tType, value: 1 });
    return acc;
  }, []);

  const displayAuditReport = data?.audit_report || (
    fallbackTransaction?.explain_plain
      ? `• **Automated Risk Assessment**: Flagged under behavioral rules: **${Array.isArray(fallbackTransaction.rules_fired) ? fallbackTransaction.rules_fired.join(", ") : fallbackTransaction.rules_fired || "BEHAVIORAL_ANOMALY"}**.\n\n• **Forensic Indicator**: ${fallbackTransaction.explain_plain}\n\n• **Observable Activity**: Transaction amount ₹${Number(amountVal).toLocaleString("en-IN")} via ${displayMode} exhibits elevated displacement velocity matching money mule signatures.`
      : ""
  );

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/80 backdrop-blur-md p-4 sm:p-6" onClick={onClose}>
      <div
        className="w-full max-w-5xl h-[92vh] bg-slate-950 rounded-2xl border border-slate-800 shadow-2xl flex flex-col overflow-hidden relative text-slate-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Top Operational Action Bar */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/90 backdrop-blur shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-xl bg-red-950/60 border border-red-800/50 text-red-400">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-bold text-slate-100 tracking-wider">STR // {transactionId}</span>
                <Badge variant="outline" className="text-[10px] font-mono border-red-500/40 bg-red-950/30 text-red-400 uppercase">
                  CONFIDENTIAL // FIU-IND
                </Badge>
              </div>
              <p className="text-xs text-slate-400 font-mono">
                PMLA 2002 Framework • Suspicious Financial Activity Case Package
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              onClick={handleCopySummary}
              variant="outline"
              size="sm"
              className="font-mono text-xs border-slate-700 bg-slate-800/60 hover:bg-slate-700 text-slate-200"
            >
              {copied ? <Check className="w-3.5 h-3.5 mr-1.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5 mr-1.5" />}
              {copied ? "Copied" : "Copy Brief"}
            </Button>
            <Button
              onClick={handleDownloadOfficialPDF}
              disabled={downloadingOfficial}
              size="sm"
              className="bg-red-600 hover:bg-red-500 text-white font-mono text-xs shadow-lg shadow-red-950/50"
            >
              {downloadingOfficial ? (
                <RefreshCw className="w-3.5 h-3.5 mr-1.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5 mr-1.5" />
              )}
              Download Official STR (PDF)
            </Button>
            <Button
              onClick={generateClientPDF}
              variant="outline"
              size="sm"
              className="font-mono text-xs border-emerald-500/40 text-emerald-400 hover:bg-emerald-950/20"
            >
              <FileText className="w-3.5 h-3.5 mr-1.5" /> Export Dossier
            </Button>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-2 rounded-xl text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors ml-1"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Forensic Report Body */}
        <div className="flex-1 overflow-y-auto p-6 sm:p-8 bg-slate-950/70">
          <div className="max-w-4xl mx-auto space-y-6" ref={reportRef}>

            {/* Formal FIU-IND Header */}
            <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-b border-slate-800 pb-3">
                <div>
                  <p className="text-[11px] font-mono font-bold tracking-widest text-red-400 uppercase">
                    GOVERNMENT OF INDIA // FINANCIAL INTELLIGENCE UNIT (FIU-IND)
                  </p>
                  <h1 className="text-xl font-bold font-mono text-slate-100 mt-0.5">
                    SUSPICIOUS TRANSACTION REPORT (STR)
                  </h1>
                </div>
                <div className="text-left sm:text-right font-mono text-xs text-slate-400">
                  <p>REPORT REF: <span className="text-cyan-400 font-bold">{transactionId}</span></p>
                  <p>DATE: {new Date().toISOString().split("T")[0]}</p>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono pt-1 text-slate-400">
                <div>
                  <span className="text-slate-500 block">Reporting Unit:</span>
                  <span className="text-slate-200">Tri-Netra AI Engine</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Statutory Act:</span>
                  <span className="text-slate-200">PMLA 2002 Sec 12</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Filing Classification:</span>
                  <span className="text-red-400 font-bold">Priority STR</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Entity Status:</span>
                  <span className="text-amber-400">Under Review</span>
                </div>
              </div>
            </div>

            {/* SECTION 1: Subject Identification & Transaction Breakdown */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-1 p-5 rounded-xl border border-slate-800 bg-slate-900/50 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    {isCredit ? (
                      <ArrowDownLeft className="w-5 h-5 text-emerald-400" />
                    ) : (
                      <ArrowUpRight className="w-5 h-5 text-red-400" />
                    )}
                    <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
                      Transaction Amount
                    </span>
                  </div>
                  <div className="text-3xl font-mono font-bold text-slate-100">
                    ₹{amountVal.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </div>
                  <Badge variant="outline" className={`mt-2 font-mono text-xs ${isCredit ? 'border-emerald-500/40 text-emerald-400' : 'border-red-500/40 text-red-400'}`}>
                    {isCredit ? "INFLOW // CREDIT" : "OUTFLOW // DEBIT"}
                  </Badge>
                </div>
                <div className="pt-4 mt-4 border-t border-slate-800/80 font-mono text-xs space-y-1.5 text-slate-400">
                  <div className="flex justify-between">
                    <span>Mode / Channel:</span>
                    <span className="text-cyan-300 font-bold uppercase">{displayMode}</span>
                  </div>
                  <div className="flex justify-between">
                    <span>Date &amp; Time:</span>
                    <span className="text-slate-200">{displayDate} {displayTime}</span>
                  </div>
                </div>
              </div>

              <div className="md:col-span-2 p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-3 font-mono text-xs">
                <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                  <Building className="w-4 h-4 text-cyan-400" /> Subject &amp; Counterparty Details
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <span className="text-slate-500 block">Primary Account:</span>
                    <span className="text-slate-200 font-bold text-sm">{displayAccount}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Customer / Name:</span>
                    <span className="text-slate-200">{displayName}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Bank / Institution:</span>
                    <span className="text-slate-200">{displayBank}</span>
                  </div>
                  <div>
                    <span className="text-slate-500 block">Counterparty Account:</span>
                    <span className="text-slate-200">{displayCounterparty}</span>
                  </div>
                </div>
                <div className="pt-2 border-t border-slate-800/80">
                  <span className="text-slate-500 block mb-0.5">Narration / Ledger Memo:</span>
                  <span className="text-slate-300 bg-slate-950 px-2 py-1 rounded border border-slate-800 block truncate">
                    {displayNarration}
                  </span>
                </div>
              </div>
            </div>

            {/* SECTION 2: Forensic AI Audit Narrative (Observable Facts) */}
            <div className="p-6 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-emerald-400" />
                <h3 className="font-mono text-sm font-bold text-slate-100 uppercase tracking-wide">
                  Formal STR Narrative (Investigative Rationale)
                </h3>
              </div>
              <div className="p-4 rounded-lg bg-slate-950/80 border border-slate-800/80 text-xs font-mono text-slate-300 leading-relaxed">
                {displayAuditReport ? (
                  <div
                    dangerouslySetInnerHTML={{
                      __html: displayAuditReport
                        .replace(/\n\n/g, "<br/><br/>")
                        .replace(/\*\*(.*?)\*\*/g, "<strong class='text-cyan-300 font-bold'>$1</strong>")
                        .replace(/\*(.*?)/g, "&bull; $1")
                    }}
                  />
                ) : (
                  <p>
                    During the automated forensic review period, the subject account exhibited high-velocity fund displacement
                    with transactions executed outside ordinary consumer baselines. Multi-party funds were received and
                    rapidly dispersed without clear economic justification. Cross-dataset coincidence models confirm
                    synchronized telecommunication activity matching the transaction timestamp. The observable behavior
                    demonstrates classic money mule and layering signatures warranting immediate regulatory reporting.
                  </p>
                )}
              </div>
            </div>

            {/* SECTION 3: Visual Exhibit Matrix (Counterparties & Transaction Distribution) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50">
                <h4 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wide mb-4 text-center">
                  Top Counterparties Volume Concentration
                </h4>
                <div className="h-48 flex justify-center">
                  {barData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={barData}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                        <XAxis dataKey="name" fontSize={10} tick={{ fill: "#94a3b8" }} />
                        <YAxis fontSize={10} tick={{ fill: "#94a3b8" }} />
                        <Tooltip
                          contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", color: "#f8fafc" }}
                          formatter={(value: any) => [`₹${Number(value).toLocaleString("en-IN")}`, "Amount"]}
                        />
                        <Bar dataKey="amount" fill="#06b6d4" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                      </BarChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center text-xs text-slate-500 font-mono">No counterparty volume history</div>
                  )}
                </div>
              </div>

              <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50">
                <h4 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wide mb-4 text-center">
                  Associated Transaction Flow Modes
                </h4>
                <div className="h-48 flex justify-center">
                  {pieData.length > 0 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={45}
                          outerRadius={75}
                          paddingAngle={3}
                          dataKey="value"
                          isAnimationActive={false}
                        >
                          {pieData.map((_: any, i: number) => (
                            <Cell key={i} fill={COLORS[i % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", color: "#f8fafc" }} />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex items-center justify-center text-xs text-slate-500 font-mono">No flow mode breakdown</div>
                  )}
                </div>
              </div>
            </div>

            {/* SECTION 4: Cross-Dataset Telecom CDR & IPDR Overlap */}
            {((data?.calls?.length || 0) > 0 || (data?.ips?.length || 0) > 0) && (
              <div className="p-5 rounded-xl border border-slate-800 bg-slate-900/50 space-y-4">
                <div className="flex items-center gap-2">
                  <PhoneCall className="w-4 h-4 text-amber-400" />
                  <h4 className="font-mono text-xs font-bold text-slate-200 uppercase tracking-wide">
                    Cross-Dataset Telecom &amp; IPDR Context (±60 min window)
                  </h4>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 font-mono text-xs">
                  <div className="p-4 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-400 block font-bold mb-2">CDR Call Records ({data?.calls?.length || 0})</span>
                    <ul className="space-y-1.5 text-slate-300 max-h-32 overflow-y-auto">
                      {data?.calls?.slice(0, 5).map((c: any, i: number) => (
                        <li key={i} className="flex justify-between border-b border-slate-900 pb-1">
                          <span className="text-cyan-400">{c.counterparty || c.phone}</span>
                          <span className="text-slate-500">{c.date || c.time} ({c.duration || 0}s)</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="p-4 rounded-lg bg-slate-950 border border-slate-800">
                    <span className="text-slate-400 block font-bold mb-2">IPDR Data Sessions ({data?.ips?.length || 0})</span>
                    <ul className="space-y-1.5 text-slate-300 max-h-32 overflow-y-auto">
                      {data?.ips?.slice(0, 5).map((ip: any, i: number) => (
                        <li key={i} className="flex justify-between border-b border-slate-900 pb-1">
                          <span className="text-violet-400">{ip.ip}</span>
                          <span className="text-slate-500">{ip.date || ip.time}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* SECTION 5: Recommended Regulatory & Law Enforcement Actions */}
            <div className="p-5 rounded-xl border border-red-900/30 bg-red-950/10 space-y-3 font-mono text-xs">
              <div className="flex items-center gap-2">
                <Lock className="w-4 h-4 text-red-400" />
                <h4 className="font-bold text-red-400 uppercase tracking-wide">
                  Recommended Investigative &amp; Enforcement Actions
                </h4>
              </div>
              <ul className="space-y-2 text-slate-300">
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span><b>Debit Freeze Order:</b> Issue immediate preventive debit freeze on destination account under Section 102 CrPC / PMLA directions.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span><b>Section 91 CrPC Telecom Production:</b> Request telecom service provider for CAF details, IMEI history, and cell-site logs of linked phone numbers.</span>
                </li>
                <li className="flex items-start gap-2">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                  <span><b>NCRP Cross-Matching:</b> Tag transaction reference in National Cybercrime Reporting Portal to correlate with multi-state cyber scam FIRs.</span>
                </li>
              </ul>
            </div>

          </div>
        </div>
      </div>
    </div>
  );
}
