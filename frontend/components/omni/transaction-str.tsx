"use client";

import React, { useEffect, useState, useRef } from "react";
import { X, Download, ShieldAlert, Activity, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, CartesianGrid
} from "recharts";

interface TransactionSTRReportProps {
  transactionId: string;
  onClose: () => void;
}

const COLORS = ["#06b6d4", "#a855f7", "#ef4444", "#f59e0b", "#10b981"];

export function TransactionSTRReport({ transactionId, onClose }: TransactionSTRReportProps) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState("");
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setLoading(true);
    
    // Fetch transaction details
    api.copilotEntityDetails(transactionId).then(detailsRes => {
      setData(detailsRes);
    }).catch(err => {
      setError(err.message || "Failed to load transaction details.");
    }).finally(() => setLoading(false));
  }, [transactionId]);

  const generatePDF = async () => {
    if (!reportRef.current) return;
    try {
      toast.info("Generating PDF, please wait...");
      
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
        backgroundColor: '#ffffff',
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
      
      pdf.save(`Transaction_STR_${transactionId}.pdf`);
    } catch (e) {
      console.error("PDF generation failed:", e);
    }
  };

  if (loading) {
    return (
      <div className="absolute inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
        <div className="flex flex-col items-center p-8 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl" onClick={(e) => e.stopPropagation()}>
          <RefreshCw className="w-8 h-8 text-cyan-500 animate-spin mb-4" />
          <h3 className="text-lg font-mono text-slate-200">Generating STR...</h3>
          <p className="text-xs text-slate-400 mt-2">Compiling forensic details for {transactionId}</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="absolute inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
        <div className="p-8 bg-slate-900 rounded-2xl border border-slate-700 shadow-2xl w-[400px]" onClick={(e) => e.stopPropagation()}>
          <h3 className="text-lg font-mono text-red-400 flex items-center gap-2 mb-4">
            <ShieldAlert className="w-5 h-5" /> Error
          </h3>
          <p className="text-sm text-slate-300">{error}</p>
          <Button onClick={onClose} className="mt-6 w-full bg-slate-700 hover:bg-slate-600">Close</Button>
        </div>
      </div>
    );
  }

  // Transaction specific target txn
  const mainTxn = data.transactions?.find((t: any) => t.id === transactionId) || data.transactions?.[0];

  // Prepare Chart Data
  const counterpartyTotals: Record<string, number> = {};
  data.transactions?.forEach((t: any) => {
    if (t.counterparty) {
      counterpartyTotals[t.counterparty] = (counterpartyTotals[t.counterparty] || 0) + (t.amount || 0);
    }
  });

  const barData = Object.entries(counterpartyTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, val]) => ({ name: name.length > 10 ? name.slice(0, 10) + "..." : name, amount: val }));

  const pieData = data.transactions?.reduce((acc: any[], t: any) => {
    const existing = acc.find(x => x.name === t.type);
    if (existing) existing.value += 1;
    else acc.push({ name: t.type, value: 1 });
    return acc;
  }, []);

  return (
    <div className="absolute inset-0 z-[100] flex items-center justify-center bg-black/70 backdrop-blur-md p-6" onClick={onClose}>
      <div 
        className="w-full max-w-5xl h-[90vh] bg-slate-50 rounded-xl shadow-2xl flex flex-col overflow-hidden relative text-slate-900"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-white">
          <div className="flex items-center gap-3">
            <ShieldAlert className="w-6 h-6 text-red-600" />
            <div>
              <h2 className="text-lg font-bold font-mono text-slate-800">STR: {transactionId}</h2>
              <p className="text-xs text-slate-500 uppercase tracking-wider">Transaction Suspicious Activity Report</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Button onClick={generatePDF} size="sm" className="bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg shadow-emerald-900/50">
              <Download className="w-4 h-4 mr-2" /> Download PDF
            </Button>
            <button onClick={onClose} className="p-2 text-slate-400 hover:text-slate-800 bg-slate-100 rounded-full transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto bg-slate-50 p-8">
          <div className="max-w-4xl mx-auto bg-white p-8 rounded-lg shadow-sm border border-slate-200" ref={reportRef}>
            
            {/* Report Header for PDF */}
            <div className="border-b-2 border-slate-800 pb-4 mb-6">
              <h1 className="text-2xl font-serif font-bold text-slate-900">Suspicious Transaction Report (STR)</h1>
              <div className="flex justify-between mt-2 text-sm text-slate-600">
                <span>Transaction Ref: {transactionId}</span>
                <span>Date: {new Date().toLocaleDateString()}</span>
              </div>
            </div>

            {/* Transaction Details */}
            {mainTxn && (
              <div className="grid grid-cols-2 gap-4 mb-8">
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-1">Amount</h3>
                  <p className="text-xl font-mono text-slate-900 font-bold">₹{mainTxn.amount.toLocaleString()}</p>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-1">Date</h3>
                  <p className="text-lg font-mono text-slate-800">{mainTxn.date}</p>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-1">Type</h3>
                  <p className="text-lg font-mono text-slate-800">{mainTxn.type === "C" ? "Credit" : "Debit"}</p>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-1">Counterparty</h3>
                  <p className="text-lg font-mono text-slate-800">{mainTxn.counterparty || "Unknown"}</p>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg col-span-2">
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-1">Narration</h3>
                  <p className="text-sm font-mono text-slate-800 truncate">{mainTxn.narration || "N/A"}</p>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-1">Bank / Account</h3>
                  <p className="text-sm font-mono text-slate-800">{mainTxn.bank || "N/A"} / {mainTxn.account_no || "N/A"}</p>
                </div>
                <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                  <h3 className="text-xs font-bold text-slate-500 uppercase mb-1">Mode</h3>
                  <p className="text-lg font-mono text-slate-800">{mainTxn.mode || "N/A"}</p>
                </div>
              </div>
            )}

            {/* AI Audit Report */}
            {data.audit_report && (
              <div className="mb-8">
                <h2 className="text-lg font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">Investigative Audit</h2>
                <div className="prose prose-sm max-w-none text-slate-700" 
                     dangerouslySetInnerHTML={{ __html: data.audit_report.replace(/\n/g, "<br/>").replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>").replace(/\*(.*?)/g, "&bull; $1") }} />
              </div>
            )}

            {/* Charts Section */}
            <div className="grid grid-cols-2 gap-8 mb-8" style={{ pageBreakInside: "avoid" }}>
              <div>
                <h3 className="text-sm font-bold text-slate-800 mb-4 text-center">Top Counterparties Volume</h3>
                <div className="h-48 flex justify-center">
                  <BarChart data={barData} width={320} height={192}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                    <XAxis dataKey="name" fontSize={10} tick={{fill: '#64748b'}} />
                    <YAxis fontSize={10} tick={{fill: '#64748b'}} />
                    <Tooltip contentStyle={{ backgroundColor: '#fff', borderColor: '#e2e8f0' }} />
                    <Bar dataKey="amount" fill="#3b82f6" radius={[4, 4, 0, 0]} isAnimationActive={false} />
                  </BarChart>
                </div>
              </div>
              
              <div>
                <h3 className="text-sm font-bold text-slate-800 mb-4 text-center">Related Txn Types</h3>
                <div className="h-48 flex justify-center">
                  <PieChart width={200} height={200}>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={40} outerRadius={80} paddingAngle={2} dataKey="value" isAnimationActive={false}>
                      {pieData.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                    </Pie>
                    <Tooltip contentStyle={{ backgroundColor: '#fff', borderColor: '#e2e8f0' }} />
                  </PieChart>
                </div>
              </div>
            </div>

            {/* Telecom / IPDR Context */}
            {(data.calls?.length > 0 || data.ips?.length > 0) && (
              <div className="mb-8" style={{ pageBreakInside: "avoid" }}>
                <h2 className="text-lg font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">Telephonic & IP Context</h2>
                <div className="grid grid-cols-2 gap-4">
                  <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                    <h3 className="text-sm font-bold text-slate-700 mb-2">Calls ({data.calls.length})</h3>
                    <ul className="text-xs text-slate-600 space-y-1 max-h-32 overflow-y-auto">
                      {data.calls.slice(0, 5).map((c: any, i: number) => (
                        <li key={i}>{c.date} - {c.counterparty} ({c.duration}s)</li>
                      ))}
                      {data.calls.length > 5 && <li>...and {data.calls.length - 5} more</li>}
                    </ul>
                  </div>
                  <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg">
                    <h3 className="text-sm font-bold text-slate-700 mb-2">IP Sessions ({data.ips.length})</h3>
                    <ul className="text-xs text-slate-600 space-y-1 max-h-32 overflow-y-auto">
                      {data.ips.slice(0, 5).map((ip: any, i: number) => (
                        <li key={i}>{ip.date} - {ip.ip}</li>
                      ))}
                      {data.ips.length > 5 && <li>...and {data.ips.length - 5} more</li>}
                    </ul>
                  </div>
                </div>
              </div>
            )}

            {/* Removed Anomalous Flow Network */}

          </div>
        </div>
      </div>
    </div>
  );
}
