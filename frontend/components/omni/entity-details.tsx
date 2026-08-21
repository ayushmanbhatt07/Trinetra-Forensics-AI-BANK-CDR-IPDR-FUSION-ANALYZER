"use client";

import React, { useEffect, useState, useRef } from "react";
import { X, ShieldAlert, Activity, RefreshCw, ArrowRight, ArrowLeftRight, User, Phone, Landmark, CreditCard, Clock, FileText } from "lucide-react";
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

  if (loading) {
    return (
      <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md">
        <div className="flex flex-col items-center p-8 bg-slate-900/90 rounded-2xl border border-slate-700 shadow-2xl">
          <RefreshCw className="w-8 h-8 text-cyan-500 animate-spin mb-4" />
          <h3 className="text-lg font-mono text-slate-200">Loading Intelligence...</h3>
          <p className="text-xs text-slate-400 mt-2">Running forensic LLM audit & network trace on {entityId}</p>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-md">
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
  let creditCount = 0;
  let debitCount = 0;
  const counterpartyTotals: Record<string, number> = {};

  data.transactions?.forEach((t: any) => {
    const tType = String(t.type || "").toUpperCase();
    if (tType.includes("CREDIT") || tType === "C") {
      creditCount += 1;
    } else {
      debitCount += 1;
    }

    const cp = t.counterparty || "Direct Counterparty";
    counterpartyTotals[cp] = (counterpartyTotals[cp] || 0) + (Number(t.amount) || 0);
  });

  const pieData = [
    { name: "Credit Inflows", value: creditCount },
    { name: "Debit Outflows", value: debitCount }
  ].filter(d => d.value > 0);

  if (pieData.length === 0) {
    pieData.push({ name: "Single Event", value: 1 });
  }

  const barData = Object.entries(counterpartyTotals)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([name, val]) => ({ name: name.length > 12 ? name.slice(0, 12) + "..." : name, amount: val }));

  if (barData.length === 0) {
    barData.push({ name: "Primary Flow", amount: data.flow?.amount || 50000 });
  }

  // Parse audit report bullet points cleanly
  const rawBullets = String(data.audit_report || "")
    .split(/\n+/)
    .map(line => line.replace(/^[\-\*\•\d\.\)\s]+/, "").trim())
    .filter(Boolean);

  const flow = data.flow || {
    sender_name: "Source Sender Account",
    sender_account: entityId,
    sender_phone: "Linked Phone",
    sender_bank: "Origin Bank",
    receiver_name: "Beneficiary Account",
    receiver_account: "Counterparty Acc",
    receiver_phone: "Destination Phone",
    receiver_bank: "Target Bank",
    amount: data.transactions?.[0]?.amount || 50000,
    mode: "IMPS / UPI",
    transaction_id: entityId,
    timestamp: "Recent Activity"
  };

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-md p-6">
      <div className="w-full max-w-6xl h-[92vh] bg-[#0a0e1a] rounded-2xl border border-slate-700/80 shadow-2xl flex flex-col overflow-hidden relative">
        
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-slate-700/80 bg-slate-900/60 backdrop-blur-sm">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-cyan-950/60 border border-cyan-500/30">
              <ShieldAlert className="w-6 h-6 text-cyan-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold font-mono text-slate-100">{entityId}</h2>
                <Badge variant="outline" className="text-cyan-400 border-cyan-500/40 bg-cyan-950/30">Interactive Forensic Report</Badge>
              </div>
              <p className="text-xs text-slate-400 uppercase tracking-wider">Back-and-Forth Transaction Cycle & STR Intelligence</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {onInvestigate && (
              <Button onClick={() => onInvestigate(entityId)} size="sm" variant="outline" className="border-cyan-600/60 text-cyan-400 hover:bg-cyan-600 hover:text-white transition-colors">
                <Activity className="w-4 h-4 mr-2" /> Generate LLM Tree
              </Button>
            )}
            <Button
              onClick={() => {
                const txnId = flow.transaction_id || entityId;
                window.dispatchEvent(new CustomEvent("pdf:transaction", { detail: txnId }));
              }}
              size="sm"
              variant="outline"
              className="border-emerald-600/60 text-emerald-400 hover:bg-emerald-600 hover:text-white transition-colors"
            >
              <FileText className="w-4 h-4 mr-2" /> Forensic STR
            </Button>
            <button onClick={onClose} className="p-2 text-slate-400 hover:text-white bg-slate-800/80 hover:bg-slate-700 rounded-full transition-colors">
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6" ref={reportRef}>
          <div className="bg-[#0a0e1a] text-slate-200 space-y-6">

            {/* 1. Back & Forth Transaction Flow Card (Top / Bottom Connection Cycle) */}
            <div className="p-5 rounded-xl border border-cyan-500/30 bg-gradient-to-r from-cyan-950/20 via-slate-900/40 to-cyan-950/20 shadow-xl">
              <div className="flex items-center justify-between mb-4 border-b border-cyan-900/40 pb-3">
                <h3 className="text-xs font-mono text-cyan-400 uppercase tracking-widest flex items-center gap-2">
                  <ArrowLeftRight className="w-4 h-4 text-cyan-400" /> Interactive Back & Forth Transaction Flow (Top / Bottom Cycle)
                </h3>
                <Badge className="bg-cyan-950 text-cyan-300 border-cyan-800">{flow.mode}</Badge>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-7 gap-4 items-center">
                {/* Sender Entity (Backwards / Top) */}
                <div className="md:col-span-3 p-4 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2 hover:border-cyan-500/40 transition-colors">
                  <div className="flex items-center gap-2 text-slate-400 text-xs font-mono uppercase tracking-wider mb-1">
                    <User className="w-4 h-4 text-cyan-400" /> Sender Entity (Backwards Connection)
                  </div>
                  <div className="text-sm font-bold text-slate-100">{flow.sender_name}</div>
                  <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
                    <CreditCard className="w-3.5 h-3.5 text-slate-500" /> Acc: <span className="text-cyan-400">{flow.sender_account}</span>
                  </div>
                  {flow.sender_phone && (
                    <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                      <Phone className="w-3.5 h-3.5 text-slate-500" /> Phone: <span>{flow.sender_phone}</span>
                    </div>
                  )}
                  {flow.sender_bank && (
                    <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                      <Landmark className="w-3.5 h-3.5 text-slate-500" /> Bank: <span>{flow.sender_bank}</span>
                    </div>
                  )}
                </div>

                {/* Transfer Arrow & Amount */}
                <div className="md:col-span-1 flex flex-col items-center justify-center p-2 text-center">
                  <div className="text-xs font-bold font-mono text-emerald-400 mb-1">
                    ₹{Number(flow.amount).toLocaleString('en-IN')}
                  </div>
                  <div className="p-2.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-400 shadow-[0_0_12px_rgba(34,211,238,0.3)] my-1">
                    <ArrowRight className="w-5 h-5 animate-pulse" />
                  </div>
                  <div className="text-[10px] font-mono text-slate-400 flex items-center gap-1 mt-1">
                    <Clock className="w-3 h-3 text-slate-500" /> {flow.timestamp}
                  </div>
                </div>

                {/* Receiver Entity (Forwards / Bottom) */}
                <div className="md:col-span-3 p-4 rounded-lg bg-slate-900/80 border border-slate-800 space-y-2 hover:border-cyan-500/40 transition-colors">
                  <div className="flex items-center gap-2 text-slate-400 text-xs font-mono uppercase tracking-wider mb-1">
                    <User className="w-4 h-4 text-purple-400" /> Receiver Entity (Forwards Connection)
                  </div>
                  <div className="text-sm font-bold text-slate-100">{flow.receiver_name}</div>
                  <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
                    <CreditCard className="w-3.5 h-3.5 text-slate-500" /> Acc: <span className="text-purple-400">{flow.receiver_account}</span>
                  </div>
                  {flow.receiver_phone && (
                    <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                      <Phone className="w-3.5 h-3.5 text-slate-500" /> Phone: <span>{flow.receiver_phone}</span>
                    </div>
                  )}
                  {flow.receiver_bank && (
                    <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
                      <Landmark className="w-3.5 h-3.5 text-slate-500" /> Bank: <span>{flow.receiver_bank}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* 2. AI Suspicion Analysis + Charts Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Point-wise Bulleted AI Suspicion Analysis */}
              <div className="lg:col-span-2 space-y-4">
                <div className="p-5 rounded-xl border border-cyan-900/50 bg-cyan-950/20">
                  <h3 className="text-xs font-mono text-cyan-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                    <Activity className="w-4 h-4" /> Point-Wise AI Forensic Suspicion Analysis
                  </h3>
                  
                  <div className="space-y-3">
                    {rawBullets.map((bullet, idx) => (
                      <div key={idx} className="flex items-start gap-3 p-3.5 rounded-lg bg-slate-900/70 border border-slate-800/80 hover:border-cyan-500/40 transition-colors shadow-sm">
                        <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shrink-0 mt-1.5 shadow-[0_0_8px_rgba(34,211,238,0.8)]" />
                        <div 
                          className="text-xs text-slate-200 leading-relaxed font-sans"
                          dangerouslySetInnerHTML={{ 
                            __html: bullet.replace(/\*\*(.*?)\*\*/g, "<strong class='text-cyan-300 font-semibold'>$1</strong>") 
                          }} 
                        />
                      </div>
                    ))}
                  </div>
                </div>
              </div>

              {/* Charts Section */}
              <div className="lg:col-span-1 space-y-6">
                
                {/* Pie Chart: Txn Type Dist */}
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3 flex items-center justify-between">
                    <span>Txn Type Dist</span>
                    <span className="text-[10px] text-cyan-400 font-normal">{data.transactions?.length || 1} records</span>
                  </h3>
                  <div className="h-40">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie data={pieData} dataKey="value" innerRadius={30} outerRadius={52} stroke="none">
                          {pieData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", fontSize: "12px", borderRadius: "8px" }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {/* Bar Chart: Top Counterparties */}
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/50">
                  <h3 className="text-xs font-mono text-slate-400 uppercase mb-3 flex items-center justify-between">
                    <span>Top Counterparties</span>
                    <span className="text-[10px] text-purple-400 font-normal">Volume (₹)</span>
                  </h3>
                  <div className="h-44">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={barData} layout="vertical" margin={{ left: 5, right: 15 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
                        <XAxis type="number" hide />
                        <YAxis dataKey="name" type="category" width={85} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                        <Tooltip contentStyle={{ backgroundColor: "#0f172a", borderColor: "#334155", fontSize: "12px", borderRadius: "8px" }} cursor={{fill: "#1e293b"}} />
                        <Bar dataKey="amount" fill="#38bdf8" radius={[0, 4, 4, 0]} barSize={14} />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>

              </div>
            </div>

            {/* 3. Direct Financial Flows & Telecom/IP Tables */}
            <div className="space-y-6 pt-4">
              
              {data.transactions?.length > 0 && (
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-cyan-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2 flex items-center gap-2">
                    <CreditCard className="w-4 h-4" /> Direct Financial Flows
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-400 uppercase font-mono bg-slate-950/60">
                        <tr>
                          <th className="py-2.5 px-3">Date</th>
                          <th className="py-2.5 px-3">Txn ID</th>
                          <th className="py-2.5 px-3">Type</th>
                          <th className="py-2.5 px-3">Counterparty</th>
                          <th className="py-2.5 px-3">Bank</th>
                          <th className="py-2.5 px-3 text-right">Amount (₹)</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono">
                        {data.transactions.slice(0, 15).map((t: any, i: number) => (
                          <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                            <td className="py-2.5 px-3 text-slate-300">{t.date}</td>
                            <td className="py-2.5 px-3 text-cyan-400">{t.id}</td>
                            <td className="py-2.5 px-3">
                              <Badge variant="outline" className={t.type === "Credit" ? "text-emerald-400 border-emerald-900 bg-emerald-950/40" : "text-rose-400 border-rose-900 bg-rose-950/40"}>{t.type}</Badge>
                            </td>
                            <td className="py-2.5 px-3 text-slate-200">{t.counterparty}</td>
                            <td className="py-2.5 px-3 text-slate-400">{t.bank || "N/A"}</td>
                            <td className="py-2.5 px-3 text-right text-emerald-400 font-bold">{Number(t.amount).toLocaleString('en-IN')}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {data.transactions.length > 15 && <p className="text-xs text-slate-500 mt-2 italic">+ {data.transactions.length - 15} more records omitted.</p>}
                  </div>
                </div>
              )}

              {data.calls?.length > 0 && (
                <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/40">
                  <h3 className="text-xs font-mono text-violet-400 uppercase tracking-widest mb-3 border-b border-slate-800 pb-2 flex items-center gap-2">
                    <Phone className="w-4 h-4" /> CDR Call Timeline
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs text-left">
                      <thead className="text-slate-400 uppercase font-mono bg-slate-950/60">
                        <tr>
                          <th className="py-2.5 px-3">Date & Time</th>
                          <th className="py-2.5 px-3">Duration (s)</th>
                          <th className="py-2.5 px-3">Call Type</th>
                          <th className="py-2.5 px-3">Counterparty MSISDN</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono">
                        {data.calls.slice(0, 10).map((c: any, i: number) => (
                          <tr key={i} className="hover:bg-slate-800/40 transition-colors">
                            <td className="py-2.5 px-3 text-slate-300">{c.date} {c.time}</td>
                            <td className="py-2.5 px-3 text-purple-400">{c.duration}s</td>
                            <td className="py-2.5 px-3 text-slate-400">{c.type}</td>
                            <td className="py-2.5 px-3 text-cyan-400">{c.counterparty}</td>
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
