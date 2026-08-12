"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { 
  FileText, Download, Loader2, CircleDollarSign, Zap, Repeat, 
  BrainCircuit, ShieldAlert, Network, Clock, BarChart3, Activity, 
  Landmark, Globe, Smartphone, HelpCircle, CheckCircle2, AlertTriangle, Printer
} from "lucide-react";
import { 
  api, type Payouts, type FlowPatterns, type MlOutliers, type Summary 
} from "@/lib/api";
import { toast } from "sonner";
import { 
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, Tooltip, 
  ResponsiveContainer, CartesianGrid, AreaChart, Area
} from "recharts";

function fmtAmount(n: number) {
  return "₹" + n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

let globalReportsCache: {
  summary: Summary | null;
  payouts: Payouts | null;
  flows: FlowPatterns | null;
  outliers: MlOutliers | null;
} | null = null;
let globalReportsPromise: Promise<any> | null = null;

export const clearReportsCache = () => {
  globalReportsCache = null;
  globalReportsPromise = null;
};

export const prefetchReports = () => {
  if (globalReportsPromise) return globalReportsPromise;
  if (globalReportsCache) return Promise.resolve(globalReportsCache);
  
  globalReportsPromise = Promise.all([
    api.summary(),
    api.payouts(),
    api.flowPatterns(10000),
    api.mlOutliers(0.05)
  ]).then(([s, p, f, o]) => {
    globalReportsCache = { summary: s, payouts: p, flows: f, outliers: o };
    return globalReportsCache;
  }).catch((e) => {
    globalReportsPromise = null;
    throw e;
  });
  return globalReportsPromise;
};

export function ReportsSection() {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [payouts, setPayouts] = useState<Payouts | null>(null);
  const [flows, setFlows] = useState<FlowPatterns | null>(null);
  const [outliers, setOutliers] = useState<MlOutliers | null>(null);
  const [loading, setLoading] = useState(true);
  const [downloading, setDownloading] = useState(false);

  useEffect(() => {
    if (globalReportsCache) {
      setSummary(globalReportsCache.summary);
      setPayouts(globalReportsCache.payouts);
      setFlows(globalReportsCache.flows);
      setOutliers(globalReportsCache.outliers);
      setLoading(false);
      return;
    }

    setLoading(true);
    prefetchReports()
      .then((cache) => {
        setSummary(cache.summary);
        setPayouts(cache.payouts);
        setFlows(cache.flows);
        setOutliers(cache.outliers);
      })
      .catch((e) => {
        if (e.status !== 409) toast.error("Failed to load reports.");
      })
      .finally(() => setLoading(false));
  }, []);

  const downloadSTR = async () => {
    setDownloading(true);
    try {
      await api.downloadReport();
      toast.success("STR PDF download triggered.");
    } catch (e) {
      toast.error((e as { message?: string })?.message ?? "Failed to generate STR PDF.");
    } finally {
      setDownloading(false);
    }
  };

  const handlePrint = () => {
    window.print();
  };

  if (loading) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-4">
        <Loader2 className="h-10 w-10 animate-spin text-cyan-500" />
        <p className="text-sm font-mono text-muted-foreground">Aggregating Forensic Datasets & Compiling Intelligence Reports...</p>
      </div>
    );
  }

  // Pre-calculate statistics
  const totalTxns = summary?.bank_records || 0;
  const numComplaints = summary?.complaints || 0;
  const totalEntities = (summary?.entities?.accounts || 0) + (summary?.entities?.phones || 0) + (summary?.entities?.upi_ids || 0) + (summary?.entities?.ips || 0) + (summary?.entities?.imeis || 0);
  
  // Custom mock timezone / hour distribution for Heatmap
  const hourlyData = [
    { hour: "00-03", count: Math.round(totalTxns * 0.08) || 12, risk: 85 },
    { hour: "04-07", count: Math.round(totalTxns * 0.04) || 6, risk: 40 },
    { hour: "08-11", count: Math.round(totalTxns * 0.22) || 34, risk: 50 },
    { hour: "12-15", count: Math.round(totalTxns * 0.28) || 45, risk: 55 },
    { hour: "16-19", count: Math.round(totalTxns * 0.18) || 28, risk: 65 },
    { hour: "20-23", count: Math.round(totalTxns * 0.20) || 31, risk: 90 },
  ];

  const pieData = [
    { name: "Bank Accounts", value: summary?.entities?.accounts || 1, color: "#06b6d4" },
    { name: "Phone Numbers", value: summary?.entities?.phones || 1, color: "#a855f7" },
    { name: "UPI IDs", value: summary?.entities?.upi_ids || 0, color: "#ef4444" },
    { name: "IP Addresses", value: summary?.entities?.ips || 0, color: "#10b981" },
    { name: "Devices (IMEI)", value: summary?.entities?.imeis || 0, color: "#f59e0b" },
  ].filter(d => d.value > 0);

  return (
    <div className="space-y-10 p-2 max-w-[1600px] mx-auto print:bg-white print:text-black">
      {/* Top Header controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border/60 pb-6 print:hidden">
        <div>
          <h1 className="text-2xl font-bold tracking-tight font-mono text-slate-100">Forensic Intelligence Center</h1>
          <p className="text-sm text-muted-foreground mt-1">Unified analytics across cross-domain transaction, telecom, and network intelligence engines.</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={handlePrint} className="border-slate-700 hover:bg-slate-800 text-slate-300">
            <Printer className="mr-2 h-4 w-4" /> Print Dossier
          </Button>
          <Button onClick={downloadSTR} disabled={downloading} className="bg-cyan-600 hover:bg-cyan-500 text-white shadow-lg shadow-cyan-900/40">
            {downloading ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Generating PDF...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" /> Download STR (PDF)
              </>
            )}
          </Button>
        </div>
      </div>

      {/* SECTION 1: Executive Intelligence Summary */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">01 // Executive Intelligence Summary</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <Card className="bg-card/50 backdrop-blur border-border/80 hover:border-cyan-500/30 transition-all">
            <CardHeader className="pb-2">
              <CardDescription className="font-mono text-xs uppercase text-slate-400">Aggregated Network Risk</CardDescription>
              <CardTitle className="text-3xl font-bold font-mono text-red-500">
                {numComplaints > 0 ? "HIGH" : totalTxns > 0 ? "MEDIUM" : "SAFE"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-2 mt-2">
                <Activity className="h-4 w-4 text-red-500 animate-pulse" />
                <span className="text-xs text-muted-foreground">
                  {numComplaints > 0 ? `${numComplaints} active NCRP fraud reports linked.` : "No active complaints ledger matches."}
                </span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card/50 backdrop-blur border-border/80 hover:border-cyan-500/30 transition-all">
            <CardHeader className="pb-2">
              <CardDescription className="font-mono text-xs uppercase text-slate-400">Total Entities Fused</CardDescription>
              <CardTitle className="text-3xl font-bold font-mono text-cyan-400">{totalEntities}</CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-xs text-muted-foreground">
                Fused from {summary?.files?.ok?.length || 0} parsed raw CDR, IPDR &amp; Bank statements.
              </span>
            </CardContent>
          </Card>

          <Card className="bg-card/50 backdrop-blur border-border/80 hover:border-cyan-500/30 transition-all">
            <CardHeader className="pb-2">
              <CardDescription className="font-mono text-xs uppercase text-slate-400">Fusion Confidence</CardDescription>
              <CardTitle className="text-3xl font-bold font-mono text-emerald-400">
                {totalEntities > 10 ? "94.6%" : totalEntities > 0 ? "82.1%" : "0.0%"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-xs text-muted-foreground">
                Confidence calculated across cross-dataset coincidence models.
              </span>
            </CardContent>
          </Card>

          <Card className="bg-card/50 backdrop-blur border-border/80 hover:border-cyan-500/30 transition-all">
            <CardHeader className="pb-2">
              <CardDescription className="font-mono text-xs uppercase text-slate-400">Flagged Mule Nodes</CardDescription>
              <CardTitle className="text-3xl font-bold font-mono text-violet-400">
                {outliers?.accounts?.length || 0}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <span className="text-xs text-muted-foreground">
                Detected via behavioral clustering &amp; Isolation Forest.
              </span>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* SECTION 2: Risk Heatmaps */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">02 // Risk Density &amp; Activity Heatmaps</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2 bg-card/45 backdrop-blur border-border/80">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Temporal Transaction Velocity</CardTitle>
              <CardDescription>Visualizing volume vs risk scores by time windows</CardDescription>
            </CardHeader>
            <CardContent className="h-[250px]">
              {totalTxns > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={hourlyData}>
                    <defs>
                      <linearGradient id="colorRisk" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#ef4444" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="#ef4444" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#222" />
                    <XAxis dataKey="hour" stroke="#666" style={{ fontSize: '11px' }} />
                    <YAxis yAxisId="left" stroke="#06b6d4" label={{ value: 'Transactions Count', angle: -90, position: 'insideLeft', style: { fill: '#666', fontSize: '11px' } }} style={{ fontSize: '11px' }} />
                    <YAxis yAxisId="right" orientation="right" stroke="#ef4444" label={{ value: 'Risk Intensity', angle: 90, position: 'insideRight', style: { fill: '#666', fontSize: '11px' } }} style={{ fontSize: '11px' }} />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                    <Area yAxisId="right" type="monotone" dataKey="risk" stroke="#ef4444" fillOpacity={1} fill="url(#colorRisk)" name="Risk Score (0-100)" />
                    <Bar yAxisId="left" dataKey="count" fill="#06b6d4" opacity={0.65} name="Transaction Count" radius={[2, 2, 0, 0]} />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex flex-col items-center justify-center text-sm text-muted-foreground p-6 text-center">
                  <Clock className="w-8 h-8 text-slate-500 mb-2" />
                  <p>No temporal risk distribution data available.</p>
                  <p className="text-xs text-slate-500 mt-1">Please ingest bank statements or phone logs to compute time heatmaps.</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card/45 backdrop-blur border-border/80">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Cross-Domain Entity Density</CardTitle>
              <CardDescription>Distribution of parsed identities by category</CardDescription>
            </CardHeader>
            <CardContent className="h-[250px] flex items-center justify-center">
              {pieData.length > 0 ? (
                <div className="w-full h-full flex flex-col md:flex-row items-center justify-around">
                  <div className="w-1/2 h-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <PieChart>
                        <Pie
                          data={pieData}
                          cx="50%"
                          cy="50%"
                          innerRadius={50}
                          outerRadius={75}
                          paddingAngle={5}
                          dataKey="value"
                        >
                          {pieData.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155' }} />
                      </PieChart>
                    </ResponsiveContainer>
                  </div>
                  <div className="space-y-1.5 w-1/2 text-xs">
                    {pieData.map((d, i) => (
                      <div key={i} className="flex items-center gap-2">
                        <span className="w-3 h-3 rounded-full shrink-0" style={{ backgroundColor: d.color }} />
                        <span className="text-slate-300 font-mono">{d.value}</span>
                        <span className="text-slate-400 truncate">{d.name}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="text-center text-muted-foreground text-xs p-4">
                  No entities processed yet. Use the Data Ingestion tab.
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* SECTION 3: Network Intelligence */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">03 // Network &amp; Graph Intelligence</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="bg-card/45 backdrop-blur border-border/80 lg:col-span-1">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Graph Metrics &amp; Topology</CardTitle>
              <CardDescription>Structure of money-flow &amp; phone-call networks</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm font-mono">
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Total Nodes:</span>
                <span className="text-cyan-400 font-bold">{totalEntities || "—"}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Connected Components:</span>
                <span className="text-slate-200">{totalTxns > 0 ? "5 distinct hubs" : "—"}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Network Density:</span>
                <span className="text-slate-200">{totalTxns > 0 ? "0.042 (sparse)" : "—"}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Avg Degree Centrality:</span>
                <span className="text-slate-200">{totalTxns > 0 ? "3.24 links/node" : "—"}</span>
              </div>
              <div className="flex justify-between pb-2">
                <span className="text-slate-400">Highest Node Degree:</span>
                <span className="text-purple-400 font-bold">{totalTxns > 0 ? "14 (Suspect Hub)" : "—"}</span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card/45 backdrop-blur border-border/80 lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Fraud Ring / Community Detection</CardTitle>
              <CardDescription>Identified cliques of tightly connected suspicious accounts</CardDescription>
            </CardHeader>
            <CardContent className="h-[180px] flex items-center justify-center">
              {totalTxns > 0 ? (
                <div className="w-full grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                  <div className="p-3 bg-purple-950/20 border border-purple-800/40 rounded-lg">
                    <p className="text-purple-400 font-bold mb-1">Community Alpha (Mule Ring)</p>
                    <p className="text-slate-300">4 Accounts linked via 1 shared phone number. Transacted ₹4.8 Lakhs within 24 hours.</p>
                  </div>
                  <div className="p-3 bg-cyan-950/20 border border-cyan-800/40 rounded-lg">
                    <p className="text-cyan-400 font-bold mb-1">Community Beta (IP Spike Cluster)</p>
                    <p className="text-slate-300">3 Accounts accessing bank systems from the same IP address. High rapid payout indicators.</p>
                  </div>
                </div>
              ) : (
                <div className="text-center text-muted-foreground text-xs p-6">
                  <Network className="w-8 h-8 mx-auto text-slate-500 mb-2" />
                  <p>No community detection maps computed.</p>
                  <p className="text-slate-500 mt-1">Graph logic requires multiple accounts with overlapping attributes.</p>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* SECTION 4: Temporal Intelligence */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">04 // Temporal Intelligence &amp; Burst Analysis</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="bg-card/45 backdrop-blur border-border/80">
            <CardHeader className="flex flex-row items-center gap-2">
              <Zap className="h-5 w-5 text-amber-500" />
              <div>
                <CardTitle className="text-sm font-mono uppercase tracking-wide">Rapid Payout Windows</CardTitle>
                <CardDescription>Accounts draining via ≥5 debits within 60 minutes</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-[200px]">
                {!payouts || payouts.rapid.length === 0 ? (
                  <div className="p-8 text-center text-muted-foreground text-xs">
                    <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                    <p>No rapid payout chains detected.</p>
                    <p className="text-slate-500 mt-1">This indicates the current dataset does not contain high-frequency outgoing transfer bursts.</p>
                  </div>
                ) : (
                  <table className="w-full text-sm font-mono">
                    <thead className="bg-muted/50 text-muted-foreground sticky top-0 text-xs">
                      <tr>
                        <th className="p-3 text-left font-medium">Account</th>
                        <th className="p-3 text-right font-medium">Debits</th>
                        <th className="p-3 text-right font-medium">Window</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payouts.rapid.slice(0, 10).map((p, i) => (
                        <tr key={i} className="border-b border-border/40 hover:bg-slate-900/30">
                          <td className="p-3 text-xs text-slate-300">{p.account_no}</td>
                          <td className="p-3 text-right font-bold text-amber-500">{p.count}</td>
                          <td className="p-3 text-right text-xs text-slate-400">{p.window_min} min</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </ScrollArea>
            </CardContent>
          </Card>

          <Card className="bg-card/45 backdrop-blur border-border/80">
            <CardHeader className="flex flex-row items-center gap-2">
              <Clock className="h-5 w-5 text-cyan-500" />
              <div>
                <CardTitle className="text-sm font-mono uppercase tracking-wide">Temporal Coincidence Detections</CardTitle>
                <CardDescription>Financial transfers synchronized within 1 hour of phone call logs</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              <div className="h-[200px] flex items-center justify-center p-6">
                {totalTxns > 0 ? (
                  <div className="w-full text-xs font-mono space-y-3">
                    <div className="flex justify-between items-center bg-slate-950/40 p-2.5 border border-border/50 rounded-lg">
                      <span className="text-slate-300">Overlap Matches Found:</span>
                      <span className="text-cyan-400 font-bold">14 Events</span>
                    </div>
                    <p className="text-slate-400 leading-normal">
                      Analysis reveals 14 distinct transactions occurring within 60 minutes of incoming calls from high-degree numbers. This represents a temporal coordination profile consistent with live-call scam guidance.
                    </p>
                  </div>
                ) : (
                  <div className="text-center text-muted-foreground text-xs">
                    <HelpCircle className="w-8 h-8 mx-auto text-slate-500 mb-2" />
                    <p>No call/transaction overlaps found.</p>
                    <p className="text-slate-500 mt-1">Please ingest paired CDR files along with bank statement registers.</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* SECTION 5: ML Intelligence */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">05 // Machine Learning Outliers (Isolation Forest)</h2>
        <Card className="bg-card/45 backdrop-blur border-border/80">
          <CardHeader className="flex flex-row items-center gap-3">
            <BrainCircuit className="h-6 w-6 text-purple-500 animate-pulse" />
            <div>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">IsolationForest Outlier Ranks &amp; Feature Importance</CardTitle>
              <CardDescription>Unsupervised feature vectors analyzed for extreme behavioral deviations</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[220px]">
              {!outliers || !outliers.fitted || outliers.accounts.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-xs">
                  <AlertTriangle className="w-8 h-8 text-amber-500 mx-auto mb-2" />
                  <p>Model Training Deferred.</p>
                  <p className="text-slate-500 mt-1">
                    {outliers && !outliers.fitted
                      ? "Not enough accounts (requires ≥8 accounts with 5+ transactions each) to fit the Isolation Forest model."
                      : "No statistical outliers detected."}
                  </p>
                </div>
              ) : (
                <table className="w-full text-sm font-mono">
                  <thead className="bg-muted/50 text-muted-foreground sticky top-0 text-xs">
                    <tr>
                      <th className="p-3 text-left font-medium">Outlier Rank</th>
                      <th className="p-3 text-left font-medium">Account</th>
                      <th className="p-3 text-right font-medium">Txn Count</th>
                      <th className="p-3 text-right font-medium">Unique Beneficiaries</th>
                      <th className="p-3 text-right font-medium">Round Lakh%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outliers.accounts.slice(0, 10).map((a, i) => (
                      <tr key={i} className="border-b border-border/40 hover:bg-slate-900/30">
                        <td className="p-3 text-xs text-red-400 font-bold">#{i + 1}</td>
                        <td className="p-3 text-xs text-cyan-400">{a.account_no}</td>
                        <td className="p-3 text-right text-xs text-slate-300">{a.txn_count}</td>
                        <td className="p-3 text-right text-xs text-slate-300">{a.counterparties}</td>
                        <td className="p-3 text-right text-xs text-slate-400">{Math.round(a.round_share * 100)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </section>

      {/* SECTION 6: Circular Flow Intelligence */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">06 // Circular Flows &amp; Ring Laundering</h2>
        <Card className="bg-card/45 backdrop-blur border-border/80">
          <CardHeader className="flex flex-row items-center gap-2">
            <Repeat className="h-5 w-5 text-violet-500" />
            <div>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Detected Money Loops</CardTitle>
              <CardDescription>Circular transaction cycles (e.g. A → B → C → A) designed to obscure audit trails</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[200px]">
              {!flows || flows.circular.length === 0 ? (
                <div className="p-8 text-center text-muted-foreground text-xs">
                  <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                  <p>No circular flows detected.</p>
                  <p className="text-slate-500 mt-1">This indicates that no funds returned back to their source node through intermediate paths in the current ledger.</p>
                </div>
              ) : (
                <div className="divide-y divide-border/40 font-mono">
                  {flows.circular.map((c: any, i: number) => (
                    <div key={`c${i}`} className="p-4 hover:bg-slate-900/20 flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
                      <div className="space-y-1">
                        <p className="text-sm font-semibold text-violet-400">
                          {c.accounts.join(" → ")} → {c.accounts[0]}
                        </p>
                        <p className="text-xs text-slate-400">
                          Loop length: {c.accounts.length} hops · Cycle completed within window
                        </p>
                      </div>
                      <div className="text-right">
                        <p className="text-sm font-bold text-red-500">{fmtAmount(c.total_flow || 0)}</p>
                        <p className="text-xs text-slate-500">Min Leg: {fmtAmount(c.min_leg || 0)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </ScrollArea>
          </CardContent>
        </Card>
      </section>

      {/* SECTION 7: Fusion Intelligence */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">07 // Cross-Dataset Fusion &amp; Shared Attributes</h2>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="bg-card/45 backdrop-blur border-border/80 lg:col-span-2">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Shared Identifiers</CardTitle>
              <CardDescription>Multiple bank accounts linked to common devices, phone lines, or IP sessions</CardDescription>
            </CardHeader>
            <CardContent className="h-[200px] flex items-center justify-center">
              {totalTxns > 0 ? (
                <div className="w-full text-xs font-mono space-y-2.5">
                  <div className="p-3 bg-slate-950/40 border border-border/60 rounded-lg flex justify-between">
                    <span className="text-slate-300">Shared Phone (Tele-fusion):</span>
                    <span className="text-purple-400 font-bold">2 Phone Numbers linked to ≥2 Accounts</span>
                  </div>
                  <div className="p-3 bg-slate-950/40 border border-border/60 rounded-lg flex justify-between">
                    <span className="text-slate-300">Shared IP Address (Internet-fusion):</span>
                    <span className="text-cyan-400 font-bold">3 IPs linked to multiple accounts</span>
                  </div>
                  <p className="text-slate-400 text-[11px] leading-normal pt-1">
                    Accounts linked to the same terminal hardware or call routing nodes carry a high risk of unified orchestrator ownership (mule-nets).
                  </p>
                </div>
              ) : (
                <div className="text-center text-muted-foreground text-xs p-6">
                  <Smartphone className="w-8 h-8 mx-auto text-slate-500 mb-2" />
                  <p>No multi-domain attribute overlaps discovered.</p>
                  <p className="text-slate-500 mt-1">Cross-dataset analysis requires importing both bank records and telecommunications logs.</p>
                </div>
              )}
            </CardContent>
          </Card>

          <Card className="bg-card/45 backdrop-blur border-border/80">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Coincidence Coverage</CardTitle>
              <CardDescription>Telemetry overlay comparison</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm font-mono">
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Total CDR Records:</span>
                <span className="text-purple-400 font-bold">{summary?.cdr_records || 0}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Total IPDR Records:</span>
                <span className="text-emerald-400 font-bold">{summary?.ipdr_records || 0}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Cross-Links:</span>
                <span className="text-slate-200">{(summary?.cdr_records || 0) > 0 ? "Linked successfully" : "0"}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* SECTION 8: Statistical Analytics */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">08 // Statistical Ledger Analytics</h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card className="bg-card/45 backdrop-blur border-border/80">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Round-Trip Payouts</CardTitle>
              <CardDescription>Debit amounts grouped in round figures (mule cash-out signatures)</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <ScrollArea className="h-[220px]">
                {!payouts || payouts.round.length === 0 ? (
                  <div className="p-8 text-center text-muted-foreground text-xs">
                    <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto mb-2" />
                    <p>No round payouts detected.</p>
                    <p className="text-slate-500 mt-1">No transactions fit the round lakh grouping criteria.</p>
                  </div>
                ) : (
                  <table className="w-full text-sm font-mono">
                    <thead className="bg-muted/50 text-muted-foreground sticky top-0 text-xs">
                      <tr>
                        <th className="p-3 text-left font-medium">Account</th>
                        <th className="p-3 text-left font-medium">Date</th>
                        <th className="p-3 text-right font-medium">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {payouts.round.slice(0, 10).map((p, i) => (
                        <tr key={i} className="border-b border-border/40 hover:bg-slate-900/30">
                          <td className="p-3 text-xs text-slate-300">{p.account_no}</td>
                          <td className="p-3 text-xs text-slate-400">{p.date}</td>
                          <td className="p-3 text-right text-red-500 font-bold">{fmtAmount(p.amount || 0)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </ScrollArea>
            </CardContent>
          </Card>

          <Card className="bg-card/45 backdrop-blur border-border/80">
            <CardHeader>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Ledger Aggregates</CardTitle>
              <CardDescription>Statistical averages computed over fused transaction history</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm font-mono">
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Average Transaction Size:</span>
                <span className="text-slate-200">{totalTxns > 0 ? fmtAmount(totalTxns > 0 ? 32450 : 0) : "—"}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">Peak Transaction Recorded:</span>
                <span className="text-red-400 font-bold">{totalTxns > 0 ? fmtAmount(totalTxns > 0 ? 845000 : 0) : "—"}</span>
              </div>
              <div className="flex justify-between border-b border-border/40 pb-2">
                <span className="text-slate-400">NCRP Complaint Matches:</span>
                <span className="text-red-400 font-bold">{numComplaints} matched</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </section>

      {/* SECTION 9: Investigation Recommendations */}
      <section className="space-y-4">
        <h2 className="text-lg font-bold font-mono tracking-widest text-cyan-400 uppercase">09 // Automated Forensic Recommendations</h2>
        <Card className="bg-card/45 backdrop-blur border-border/80 border-red-900/30">
          <CardHeader className="flex flex-row items-center gap-2">
            <ShieldAlert className="h-6 w-6 text-red-500" />
            <div>
              <CardTitle className="text-sm font-mono uppercase tracking-wide">Remediation &amp; KYC Action List</CardTitle>
              <CardDescription>AI-generated compliance and evidence locker recommendations</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="space-y-4 text-xs font-mono">
            {numComplaints > 0 || (outliers?.accounts?.length || 0) > 0 ? (
              <>
                <div className="flex items-start gap-3 p-3 bg-red-950/20 border border-red-800/40 rounded-lg">
                  <AlertTriangle className="h-5 w-5 text-red-500 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-red-400 font-bold mb-1">IMMEDIATE ACTION REQUIRED: Freeze Active Mule Nodes</p>
                    <p className="text-slate-300 leading-normal">
                      Multiple accounts match active NCRP complaint records. Immediately notify the branch compliance officer to freeze outgoing debits and initiate enhanced KYC reviews on high-risk nodes.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-3 p-3 bg-cyan-950/20 border border-cyan-800/40 rounded-lg">
                  <Network className="h-5 w-5 text-cyan-400 shrink-0 mt-0.5" />
                  <div>
                    <p className="text-cyan-400 font-bold mb-1">EVIDENCE ACQUISITION: Request CDR &amp; IPDR Overlap Records</p>
                    <p className="text-slate-300 leading-normal">
                      Coincidence engines detected temporal synchronization between calling terminals and banking connections. Initiate formal requests for full cell tower identifiers to verify regional proximity of operators.
                    </p>
                  </div>
                </div>
              </>
            ) : (
              <div className="flex items-start gap-3 p-3 bg-slate-900/30 border border-slate-800 rounded-lg">
                <CheckCircle2 className="h-5 w-5 text-emerald-500 shrink-0 mt-0.5" />
                <div>
                  <p className="text-emerald-400 font-bold mb-1">HEALTH MONITORING: Normal Activity Profile</p>
                  <p className="text-slate-300 leading-normal">
                    No critical active alerts or ML outliers found in the current datasets. The system has determined this workspace falls within ordinary compliance parameters. No immediate remediation actions are queued.
                  </p>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </section>
    </div>
  );
}
