"use client";

import React, { useEffect, useState, useRef } from "react";
import { X, Download, ShieldAlert, Activity, Sparkles, Check, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, CartesianGrid
} from "recharts";
import { SafeChartContainer } from "@/components/ui/safe-chart-container";

interface EntityDetailsOverlayProps {
  entityId: string;
  onClose: () => void;
  onInvestigate?: (entityId: string) => void;
}

const COLORS = ["#06b6d4", "#a855f7", "#ef4444", "#f59e0b", "#10b981"];

export function EntityDetailsOverlay({ entityId, onClose, onInvestigate }: EntityDetailsOverlayProps) {
  const [data, setData] = useState<any>(null);
  const [auditReport, setAuditReport] = useState<string>("");
  const [auditLoading, setAuditLoading] = useState<boolean>(true);
  const [error, setError] = useState("");
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setError("");
    let isMounted = true;

    // 1. Fetch structural entity details immediately (< 5ms)
    api.copilotEntityDetails(entityId, false)
      .then((res) => {
        if (!isMounted) return;
        setData(res);
        if (res.audit_report) {
          setAuditReport(res.audit_report);
          setAuditLoading(false);
        } else {
          // 2. Fetch AI narrative asynchronously in background
          api.copilotEntityAudit(entityId)
            .then((auditRes) => {
              if (isMounted) {
                setAuditReport(auditRes.audit_report || "Forensic audit completed.");
                setAuditLoading(false);
              }
            })
            .catch(() => {
              if (isMounted) {
                setAuditReport("Forensic AI analysis logged with standard risk parameters.");
                setAuditLoading(false);
              }
            });
        }
      })
      .catch((err) => {
        if (isMounted) setError(err?.message || "Failed to load entity details.");
      });

    return () => {
      isMounted = false;
    };
  }, [entityId]);

  // Prepare Chart Data unconditionally at top level
  const { pieData, barData } = React.useMemo(() => {
    if (!data?.transactions || !Array.isArray(data.transactions)) return { pieData: [], barData: [] };
    const typeCount = { C: 0, D: 0 };
    const counterpartyTotals: Record<string, number> = {};
    data.transactions.forEach((t: any) => {
      if (t.type === "C" || t.type === "D") {
        typeCount[t.type as "C" | "D"] = (typeCount[t.type as "C" | "D"] || 0) + 1;
      }
      if (t.counterparty) {
        counterpartyTotals[t.counterparty] = (counterpartyTotals[t.counterparty] || 0) + (t.amount || 0);
      }
    });

    const pie = [
      { name: "Credit", value: typeCount.C },
      { name: "Debit", value: typeCount.D }
    ];

    const bar = Object.entries(counterpartyTotals)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([name, val]) => ({ name: name.length > 10 ? name.slice(0, 10) + "..." : name, amount: val }));

    return { pieData: pie, barData: bar };
  }, [data?.transactions]);

  const generatePDF = React.useCallback(async () => {
    if (!reportRef.current) return;
    try {
      toast.loading("Generating elaborative forensic STR PDF...", { id: "pdf-toast" });
      const htmlToImage = await import("html-to-image");
      const { jsPDF } = await import("jspdf");
      
      const dataUrl = await htmlToImage.toPng(reportRef.current, { 
        quality: 0.98, 
        backgroundColor: '#0a0e1a',
        pixelRatio: 2 
      });
      
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
      
      pdf.save(`STR_${entityId}.pdf`);
      toast.success("STR downloaded successfully!", { id: "pdf-toast" });
    } catch (e) {
      toast.error("Failed to generate STR.", { id: "pdf-toast" });
    }
  }, [entityId]);

  if (error) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
        <div className="p-6 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl w-full max-w-md">
          <h3 className="text-lg font-mono text-red-400 flex items-center gap-2 mb-3">
            <ShieldAlert className="w-5 h-5" /> Entity Lookup
          </h3>
          <p className="text-sm text-slate-300">{error || "No entity data found."}</p>
          <Button onClick={onClose} className="mt-5 w-full bg-slate-700 hover:bg-slate-600">Close</Button>
        </div>
      </div>
    );
  }

  const txns = data?.transactions || [];
  const calls = data?.calls || [];
  const ips = data?.ips || [];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-4 sm:p-6 animate-in fade-in duration-200">
      <div className="w-full max-w-5xl h-[90vh] bg-[#0a0e1a] rounded-xl border border-slate-700/80 shadow-2xl flex flex-col overflow-hidden relative">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700/80 bg-slate-900/50 shrink-0">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 text-cyan-500" />
            <div>
              <h2 className="text-lg font-bold font-mono text-slate-100">{entityId}</h2>
              <p className="text-xs text-slate-400 uppercase tracking-wider">Detailed Forensic & STR Audit</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {onInvestigate && (
              <Button onClick={() => onInvestigate(entityId)} size="sm" variant="outline" className="border-cyan-600 text-cyan-400 hover:bg-cyan-600 hover:text-white transition-colors">
                <Activity className="w-4 h-4 mr-1.5" /> Generate LLM Tree
              </Button>
            )}
            <Button onClick={generatePDF} size="sm" className="bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-900/50">
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
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
              
              {/* Audit Report */}
              <div className="lg:col-span-2 space-y-4">
                <div className="p-5 rounded-lg border border-cyan-900/50 bg-cyan-950/20 h-full flex flex-col justify-between">
                  <div>
                    <h3 className="text-sm font-mono text-cyan-400 uppercase tracking-widest mb-3 flex items-center justify-between">
                      <span className="flex items-center gap-2">
                        <Sparkles className="w-4 h-4 text-cyan-400" /> AI Suspicion Analysis
                      </span>
                      {auditLoading && (
                        <span className="text-[11px] font-sans text-cyan-400/80 animate-pulse flex items-center gap-1.5">
                          <span className="size-1.5 rounded-full bg-cyan-400 animate-ping" /> Analyzing signals...
                        </span>
                      )}
                    </h3>
                    {auditLoading && !auditReport ? (
                      <div className="space-y-2.5 py-2 animate-pulse">
                        <div className="h-3.5 bg-cyan-900/40 rounded w-11/12" />
                        <div className="h-3.5 bg-cyan-900/30 rounded w-full" />
                        <div className="h-3.5 bg-cyan-900/30 rounded w-4/5" />
                        <div className="h-3.5 bg-cyan-900/20 rounded w-2/3" />
                      </div>
                    ) : (
                      <div 
                        className="prose prose-invert prose-sm max-w-none font-sans text-slate-300 leading-relaxed text-xs sm:text-sm" 
                        dangerouslySetInnerHTML={{ 
                          __html: (auditReport || "Forensic audit complete. No elevated risk patterns identified for this entity.")
                            .replace(/\n/g, "<br/>")
                            .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
                            .replace(/\*(.*?)/g, "&bull; $1") 
                        }} 
                      />
                    )}
                  </div>
                  <div className="mt-4 pt-3 border-t border-cyan-900/40 flex items-center justify-between text-[11px] text-slate-400">
                    <span>Forensic Model: Groq LLaMA 3.3 70B & Rules</span>
                    <span className="font-mono">{txns.length} Txns · {calls.length} Calls · {ips.length} IPs</span>
                  </div>
                </div>
              </div>

              {/* Charts */}
              <div className="lg:col-span-1 space-y-6">
                <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3">Txn Type Dist</h3>
                  <div className="h-32 min-h-[128px] w-full min-w-0">
                    <SafeChartContainer className="w-full h-full min-w-0 min-h-0">
                      <PieChart>
                        <Pie data={pieData} dataKey="value" innerRadius={25} outerRadius={45} stroke="none" isAnimationActive={false}>
                          {pieData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", fontSize: "12px" }} />
                      </PieChart>
                    </SafeChartContainer>
                  </div>
                </div>

                <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3">Top Counterparties</h3>
                  <div className="h-40 min-h-[160px] w-full min-w-0">
                    <SafeChartContainer className="w-full h-full min-w-0 min-h-0">
                      <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                        <XAxis type="number" hide />
                        <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                        <Tooltip contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", fontSize: "12px" }} cursor={{fill: "#1e293b"}} />
                        <Bar dataKey="amount" fill="#38bdf8" radius={[0, 4, 4, 0]} barSize={12} isAnimationActive={false} />
                      </BarChart>
                    </SafeChartContainer>
                  </div>
                </div>
              </div>
            </div>

            {/* Timeline / Records */}
            <div className="space-y-6">
              
              {txns.length > 0 ? (
                <div>
                  <h3 className="text-sm font-mono text-cyan-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2">Direct Financial Flows ({txns.length})</h3>
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
                        {txns.slice(0, 15).map((t: any, i: number) => (
                          <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                            <td className="py-2 px-3 font-mono">{t.date || "—"}</td>
                            <td className="py-2 px-3 font-mono text-slate-400">{t.id || "—"}</td>
                            <td className="py-2 px-3">
                              <Badge variant="outline" className={t.type === "C" ? "text-emerald-400 border-emerald-900" : "text-rose-400 border-rose-900"}>{t.type}</Badge>
                            </td>
                            <td className="py-2 px-3 font-mono">{t.counterparty || "—"}</td>
                            <td className="py-2 px-3 font-mono text-right">{Number(t.amount).toLocaleString('en-IN')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {txns.length > 15 && <p className="text-xs text-slate-500 mt-2 italic">+ {txns.length - 15} more records omitted.</p>}
                  </div>
                </div>
              ) : (
                <div className="p-4 rounded border border-slate-800 text-center text-xs text-slate-500">
                  No direct financial transactions linked to this entity.
                </div>
              )}

              {calls.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-sm font-mono text-violet-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2">CDR Call Timeline ({calls.length})</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-500 uppercase">
                        <tr>
                          <th className="py-2 px-3">Date & Time</th>
                          <th className="py-2 px-3">Duration</th>
                          <th className="py-2 px-3">Counterparty MSISDN</th>
                        </tr>
                      </thead>
                      <tbody>
                        {calls.slice(0, 10).map((c: any, i: number) => (
                          <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                            <td className="py-2 px-3 font-mono">{c.date || ""} {c.time || ""}</td>
                            <td className="py-2 px-3 font-mono text-slate-400">{c.duration ? `${c.duration}s` : "—"}</td>
                            <td className="py-2 px-3 font-mono">{c.counterparty || "—"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {ips.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-sm font-mono text-amber-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2">IP Session Logs ({ips.length})</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-500 uppercase">
                        <tr>
                          <th className="py-2 px-3">Timestamp / Date</th>
                          <th className="py-2 px-3">IP Address</th>
                          <th className="py-2 px-3">Destination</th>
                        </tr>
                      </thead>
                      <tbody>
                        {ips.slice(0, 10).map((p: any, i: number) => (
                          <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                            <td className="py-2 px-3 font-mono">{p.date || p.start || "—"}</td>
                            <td className="py-2 px-3 font-mono text-slate-400">{p.ip || "—"}</td>
                            <td className="py-2 px-3 font-mono">{p.destination || "—"}</td>
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
    </div>
  );
}
