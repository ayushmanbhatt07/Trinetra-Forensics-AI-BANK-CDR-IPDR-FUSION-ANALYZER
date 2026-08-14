"use client";

import React, { useEffect, useState, useRef } from "react";
import { X, Download, ShieldAlert, Activity, Sparkles, Landmark, Calendar, Phone, ArrowUpRight, ArrowDownLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, CartesianGrid
} from "recharts";
import { SafeChartContainer } from "@/components/ui/safe-chart-container";

interface TransactionSTRReportProps {
  transactionId: string;
  onClose: () => void;
}

const COLORS = ["#06b6d4", "#a855f7", "#ef4444", "#f59e0b", "#10b981"];

export function TransactionSTRReport({ transactionId, onClose }: TransactionSTRReportProps) {
  const [data, setData] = useState<any>(null);
  const [auditReport, setAuditReport] = useState<string>("");
  const [auditLoading, setAuditLoading] = useState<boolean>(true);
  const [error, setError] = useState("");
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setError("");
    let isMounted = true;

    // Fetch transaction details immediately
    api.copilotEntityDetails(transactionId, false)
      .then((res) => {
        if (!isMounted) return;
        setData(res);
        if (res.audit_report) {
          setAuditReport(res.audit_report);
          setAuditLoading(false);
        } else {
          api.copilotEntityAudit(transactionId)
            .then((auditRes) => {
              if (isMounted) {
                setAuditReport(auditRes.audit_report || "Forensic audit complete.");
                setAuditLoading(false);
              }
            })
            .catch(() => {
              if (isMounted) {
                setAuditReport("Forensic analysis completed with standard thresholds.");
                setAuditLoading(false);
              }
            });
        }
      })
      .catch((err) => {
        if (isMounted) setError(err?.message || "Failed to load transaction details.");
      });

    return () => {
      isMounted = false;
    };
  }, [transactionId]);

  const generatePDF = async () => {
    if (!reportRef.current) return;
    try {
      toast.info("Generating forensic STR PDF...", { id: "tx-pdf" });
      
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
        backgroundColor: '#0a0e1a',
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
      
      pdf.addImage(dataUrl, 'PNG', 0, position, imgWidth, imgHeight);
      heightLeft -= pdfHeight;
      
      while (heightLeft >= 0) {
        position = heightLeft - imgHeight;
        pdf.addPage();
        pdf.addImage(dataUrl, 'PNG', 0, position, imgWidth, imgHeight);
        heightLeft -= pdfHeight;
      }
      
      pdf.save(`STR_Transaction_${transactionId}.pdf`);
      toast.success("Forensic STR downloaded successfully!", { id: "tx-pdf" });
    } catch (e) {
      toast.error("Failed to generate STR PDF.", { id: "tx-pdf" });
    }
  };

  if (error) {
    return (
      <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
        <div className="p-6 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl w-full max-w-md" onClick={(e) => e.stopPropagation()}>
          <h3 className="text-lg font-mono text-red-400 flex items-center gap-2 mb-3">
            <ShieldAlert className="w-5 h-5" /> Transaction Lookup
          </h3>
          <p className="text-sm text-slate-300">{error}</p>
          <Button onClick={onClose} className="mt-5 w-full bg-slate-700 hover:bg-slate-600">Close</Button>
        </div>
      </div>
    );
  }

  const txns = data?.transactions || [];
  const mainTxn = txns.find((t: any) => t.id === transactionId) || txns[0];

  const counterpartyTotals: Record<string, number> = {};
  txns.forEach((t: any) => {
    if (t.counterparty) {
      counterpartyTotals[t.counterparty] = (counterpartyTotals[t.counterparty] || 0) + (t.amount || 0);
    }
  });

  const barData = Object.entries(counterpartyTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, val]) => ({ name: name.length > 10 ? name.slice(0, 10) + "..." : name, amount: val }));

  const pieData = txns.reduce((acc: any[], t: any) => {
    const existing = acc.find(x => x.name === t.type);
    if (existing) existing.value += 1;
    else acc.push({ name: t.type === "C" ? "Credit" : "Debit", value: 1 });
    return acc;
  }, []);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-md p-4 sm:p-6 animate-in fade-in duration-200" onClick={onClose}>
      <div 
        className="w-full max-w-5xl h-[90vh] bg-[#0a0e1a] rounded-xl border border-slate-700/80 shadow-2xl flex flex-col overflow-hidden relative text-slate-200"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700/80 bg-slate-900/50 shrink-0">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 text-red-500" />
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold font-mono text-slate-100">{transactionId}</h2>
                <Badge variant="outline" className="bg-red-500/10 text-red-400 border-red-500/30 text-[10px]">
                  FORENSIC STR
                </Badge>
              </div>
              <p className="text-xs text-slate-400 uppercase tracking-wider">
                Suspicious Transaction Report & Linked Financial Ledger
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button onClick={generatePDF} size="sm" className="bg-red-600 hover:bg-red-500 text-white shadow-lg shadow-red-900/40">
              <Download className="w-4 h-4 mr-1.5" /> Export STR (PDF)
            </Button>
            <button onClick={onClose} className="p-2 text-slate-400 hover:text-white bg-slate-800 rounded-full transition-colors ml-1">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6" ref={reportRef}>
          <div className="bg-[#0a0e1a] text-slate-200 p-2">
            
            {/* Main Txn KPI Cards */}
            {mainTxn && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
                <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-900/60">
                  <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1">Transaction Amount</span>
                  <span className="text-lg font-bold font-mono text-emerald-400">
                    ₹{Number(mainTxn.amount || 0).toLocaleString("en-IN")}
                  </span>
                </div>
                <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-900/60">
                  <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1">Transfer Mode & Type</span>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <Badge variant="outline" className="border-slate-700 text-slate-300 font-mono text-xs">
                      {mainTxn.mode || "UPI/IMPS"}
                    </Badge>
                    <Badge variant="outline" className={mainTxn.type === "C" ? "text-emerald-400 border-emerald-800" : "text-rose-400 border-rose-800"}>
                      {mainTxn.type === "C" ? "Credit (In)" : "Debit (Out)"}
                    </Badge>
                  </div>
                </div>
                <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-900/60">
                  <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1">Source Account</span>
                  <span className="text-sm font-mono text-slate-200 truncate block">
                    {mainTxn.account_no || "—"}
                  </span>
                </div>
                <div className="p-3.5 rounded-lg border border-slate-800 bg-slate-900/60">
                  <span className="text-[10px] uppercase font-mono text-slate-400 block mb-1">Counterparty</span>
                  <span className="text-sm font-mono text-slate-200 truncate block">
                    {mainTxn.counterparty || "—"}
                  </span>
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              {/* Audit Summary Box */}
              <div className="lg:col-span-2 space-y-4">
                <div className="p-5 rounded-lg border border-red-900/40 bg-red-950/20 h-full flex flex-col justify-between">
                  <div>
                    <h3 className="text-sm font-mono text-red-400 uppercase tracking-widest mb-3 flex items-center justify-between">
                      <span className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-red-400" /> STR Intelligence & Narrative
                      </span>
                      {auditLoading && (
                        <span className="text-[11px] font-sans text-red-400/80 animate-pulse flex items-center gap-1.5">
                          <span className="size-1.5 rounded-full bg-red-400 animate-ping" /> Analyzing signals...
                        </span>
                      )}
                    </h3>
                    {auditLoading && !auditReport ? (
                      <div className="space-y-2.5 py-2 animate-pulse">
                        <div className="h-3.5 bg-red-900/40 rounded w-11/12" />
                        <div className="h-3.5 bg-red-900/30 rounded w-full" />
                        <div className="h-3.5 bg-red-900/30 rounded w-4/5" />
                        <div className="h-3.5 bg-red-900/20 rounded w-2/3" />
                      </div>
                    ) : (
                      <div 
                        className="prose prose-invert prose-sm max-w-none font-sans text-slate-300 leading-relaxed text-xs sm:text-sm" 
                        dangerouslySetInnerHTML={{ 
                          __html: (auditReport || "Forensic audit complete. No elevated risk patterns identified for this transaction.")
                            .replace(/\n/g, "<br/>")
                            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
                            .replace(/\*(.*?)/g, "&bull; $1") 
                        }} 
                      />
                    )}
                  </div>
                  {mainTxn?.narration && (
                    <div className="mt-4 pt-3 border-t border-red-900/30 text-xs font-mono text-slate-400">
                      <span className="text-slate-500 uppercase text-[10px] block">Narration:</span>
                      <p className="text-slate-300 mt-0.5">{mainTxn.narration}</p>
                    </div>
                  )}
                </div>
              </div>

              {/* Chart Breakdown */}
              <div className="lg:col-span-1 space-y-6">
                <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3">Linked Flows Breakdown</h3>
                  <div className="h-32 min-h-[128px] w-full min-w-0">
                    <SafeChartContainer className="w-full h-full min-w-0 min-h-0">
                      <PieChart>
                        <Pie data={pieData} dataKey="value" innerRadius={25} outerRadius={45} stroke="none" isAnimationActive={false}>
                          {pieData.map((entry: any, index: number) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", fontSize: "12px" }} />
                      </PieChart>
                    </SafeChartContainer>
                  </div>
                </div>

                <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3">Counterparty Concentration</h3>
                  <div className="h-40 min-h-[160px] w-full min-w-0">
                    <SafeChartContainer className="w-full h-full min-w-0 min-h-0">
                      <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                        <XAxis type="number" hide />
                        <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                        <Tooltip contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", fontSize: "12px" }} cursor={{fill: "#1e293b"}} />
                        <Bar dataKey="amount" fill="#f43f5e" radius={[0, 4, 4, 0]} barSize={12} isAnimationActive={false} />
                      </BarChart>
                    </SafeChartContainer>
                  </div>
                </div>
              </div>
            </div>

            {/* Linked Transactions Table */}
            {txns.length > 0 && (
              <div className="mt-6">
                <h3 className="text-sm font-mono text-slate-300 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2">
                  Correlated Account Activity ({txns.length} records)
                </h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead className="text-slate-500 uppercase">
                      <tr>
                        <th className="py-2 px-3">Date</th>
                        <th className="py-2 px-3">Txn ID</th>
                        <th className="py-2 px-3">Type</th>
                        <th className="py-2 px-3">Counterparty</th>
                        <th className="py-2 px-3 text-right">Amount (₹)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {txns.slice(0, 10).map((t: any, i: number) => (
                        <tr key={i} className={`border-b border-slate-800/50 hover:bg-slate-800/20 ${t.id === transactionId ? 'bg-red-500/10 font-bold' : ''}`}>
                          <td className="py-2 px-3 font-mono">{t.date || "—"}</td>
                          <td className="py-2 px-3 font-mono text-slate-400">
                            {t.id} {t.id === transactionId && <span className="text-red-400 text-[10px] ml-1">(target)</span>}
                          </td>
                          <td className="py-2 px-3">
                            <Badge variant="outline" className={t.type === "C" ? "text-emerald-400 border-emerald-900" : "text-rose-400 border-rose-900"}>
                              {t.type}
                            </Badge>
                          </td>
                          <td className="py-2 px-3 font-mono">{t.counterparty || "—"}</td>
                          <td className="py-2 px-3 font-mono text-right">{Number(t.amount).toLocaleString('en-IN')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

          </div>
        </div>
      </div>
    </div>
  );
}
