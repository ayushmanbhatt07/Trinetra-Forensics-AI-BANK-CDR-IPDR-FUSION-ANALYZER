"use client";

import React, { useEffect, useState, useRef } from "react";
import { X, Download, ShieldAlert, Activity, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid
} from "recharts";

interface EntityDetailsOverlayProps {
  entityId: string;
  onClose: () => void;
  onInvestigate?: (entityId: string) => void;
}

const COLORS = ["#06b6d4", "#a855f7", "#ef4444", "#f59e0b", "#10b981"];

export function EntityDetailsOverlay({ entityId, onClose, onInvestigate }: EntityDetailsOverlayProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    api.copilotEntityDetails(entityId)
      .then(res => {
        setData(res);
      })
      .catch(err => {
        setError(err.message || "Failed to load entity details.");
      })
      .finally(() => setLoading(false));
  }, [entityId]);

  const generatePDF = async () => {
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
  };

  if (loading) {
    return (
      <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
        <div className="flex flex-col items-center p-8 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl">
          <RefreshCw className="w-8 h-8 text-cyan-500 animate-spin mb-4" />
          <h3 className="text-lg font-mono text-slate-200">Loading Intelligence...</h3>
          <p className="text-xs text-slate-400 mt-2">Running forensic LLM audit on {entityId}</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
        <div className="p-8 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl w-[400px]">
          <h3 className="text-lg font-mono text-red-400 flex items-center gap-2 mb-4">
            <ShieldAlert className="w-5 h-5" /> Error
          </h3>
          <p className="text-sm text-slate-300">{error}</p>
          <Button onClick={onClose} className="mt-6 w-full bg-slate-700 hover:bg-slate-600">Close</Button>
        </div>
      </div>
    );
  }

  // Prepare Chart Data
  const typeCount = { C: 0, D: 0 };
  const counterpartyTotals: Record<string, number> = {};
  data.transactions?.forEach((t: any) => {
    typeCount[t.type as "C" | "D"] += 1;
    if (t.counterparty) {
      counterpartyTotals[t.counterparty] = (counterpartyTotals[t.counterparty] || 0) + (t.amount || 0);
    }
  });

  const pieData = [
    { name: "Credit", value: typeCount.C },
    { name: "Debit", value: typeCount.D }
  ];

  const barData = Object.entries(counterpartyTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, val]) => ({ name: name.length > 10 ? name.slice(0, 10) + "..." : name, amount: val }));

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md p-6">
      <div className="w-full max-w-5xl h-[90vh] bg-[#0a0e1a] rounded-xl border border-slate-700/80 shadow-2xl flex flex-col overflow-hidden relative">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700/80 bg-slate-900/50">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 text-cyan-500" />
            <div>
              <h2 className="text-lg font-bold font-mono text-slate-100">{entityId}</h2>
              <p className="text-xs text-slate-400 uppercase tracking-wider">Detailed Forensic & STR Audit</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {onInvestigate && (
              <Button onClick={() => onInvestigate(entityId)} size="sm" variant="outline" className="border-cyan-600 text-cyan-400 hover:bg-cyan-600 hover:text-white transition-colors">
                <Activity className="w-4 h-4 mr-2" /> Generate LLM Tree
              </Button>
            )}
            <Button onClick={generatePDF} size="sm" className="bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-900/50">
              <Download className="w-4 h-4 mr-2" /> Export STR (PDF)
            </Button>
            <button onClick={onClose} className="p-2 text-slate-400 hover:text-white bg-slate-800 rounded-full transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Content (PDF Canvas) */}
        <div className="flex-1 overflow-y-auto p-6" ref={reportRef}>
          {/* Printable wrapper ensures dark mode looks okay on PDF or we can style it via CSS */}
          <div className="bg-[#0a0e1a] text-slate-200 p-2">
            <div className="grid grid-cols-3 gap-6 mb-8">
              
              {/* Audit Report */}
              <div className="col-span-2 space-y-4">
                <div className="p-5 rounded-lg border border-cyan-900/50 bg-cyan-950/20 h-full">
                  <h3 className="text-sm font-mono text-cyan-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                    <Activity className="w-4 h-4" /> AI Suspicion Analysis
                  </h3>
                  <div className="prose prose-invert prose-sm max-w-none font-sans text-slate-300 leading-relaxed" 
                       dangerouslySetInnerHTML={{ __html: data.audit_report.replace(/\n/g, "<br/>").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\*(.*?)/g, "&bull; $1") }} />
                </div>
              </div>

              {/* Charts */}
              <div className="col-span-1 space-y-6">
                <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3">Txn Type Dist</h3>
                  <div className="h-32">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={pieData} dataKey="value" innerRadius={25} outerRadius={45} stroke="none">
                          {pieData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", fontSize: "12px" }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                <div className="p-4 rounded-lg border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3">Top Counterparties</h3>
                  <div className="h-40">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={barData} layout="vertical" margin={{ left: 10, right: 10 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                        <XAxis type="number" hide />
                        <YAxis dataKey="name" type="category" width={80} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                        <Tooltip contentStyle={{ backgroundColor: "#1e293b", borderColor: "#334155", fontSize: "12px" }} cursor={{fill: "#1e293b"}} />
                        <Bar dataKey="amount" fill="#38bdf8" radius={[0, 4, 4, 0]} barSize={12} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            </div>

            {/* Timeline / Records */}
            <div className="space-y-6">
              
              {data.transactions?.length > 0 && (
                <div>
                  <h3 className="text-sm font-mono text-cyan-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2">Direct Financial Flows</h3>
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
                        {data.transactions.slice(0, 15).map((t: any, i: number) => (
                          <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                            <td className="py-2 px-3 font-mono">{t.date}</td>
                            <td className="py-2 px-3 font-mono text-slate-400">{t.id}</td>
                            <td className="py-2 px-3">
                              <Badge variant="outline" className={t.type === "C" ? "text-emerald-400 border-emerald-900" : "text-rose-400 border-rose-900"}>{t.type}</Badge>
                            </td>
                            <td className="py-2 px-3 font-mono">{t.counterparty}</td>
                            <td className="py-2 px-3 font-mono text-right">{Number(t.amount).toLocaleString('en-IN')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {data.transactions.length > 15 && <p className="text-xs text-slate-500 mt-2 italic">+ {data.transactions.length - 15} more records omitted.</p>}
                  </div>
                </div>
              )}

              {data.calls?.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-sm font-mono text-violet-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2">CDR Call Timeline</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-500 uppercase">
                        <tr>
                          <th className="py-2 px-3">Date & Time</th>
                          <th className="py-2 px-3">Duration (s)</th>
                          <th className="py-2 px-3">Counterparty MSISDN</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.calls.slice(0, 10).map((c: any, i: number) => (
                          <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                            <td className="py-2 px-3 font-mono">{c.date} {c.time}</td>
                            <td className="py-2 px-3 font-mono text-slate-400">{c.duration}s</td>
                            <td className="py-2 px-3 font-mono">{c.counterparty}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {data.ips?.length > 0 && (
                <div className="mt-8">
                  <h3 className="text-sm font-mono text-amber-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2">IP Session Logs</h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-500 uppercase">
                        <tr>
                          <th className="py-2 px-3">Timestamp</th>
                          <th className="py-2 px-3">IP Address</th>
                          <th className="py-2 px-3">Duration (s)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.ips.slice(0, 10).map((p: any, i: number) => (
                          <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/20">
                            <td className="py-2 px-3 font-mono">{p.start}</td>
                            <td className="py-2 px-3 font-mono text-slate-400">{p.ip}</td>
                            <td className="py-2 px-3 font-mono">{p.dur}s</td>
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
