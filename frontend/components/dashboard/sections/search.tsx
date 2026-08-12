"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Search, Loader2, Hash, Phone, Landmark, CreditCard, FileWarning, Globe, ArrowLeft, ShieldAlert, Activity, Users, Network, Bot, BrainCircuit, FileText, Zap, PlusCircle, Share2 } from "lucide-react";
import { api, type CopilotQueryResult } from "@/lib/api";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { InvestigationPanel } from "@/components/dashboard/investigation-panel";

export function SearchSection() {
  const [query, setQuery] = useState("");
  const [dossier, setDossier] = useState<CopilotQueryResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [suggestions] = useState([
    "Show every transfer within 10 minutes of a call to +91",
    "Show all devices linked to this account",
    "Find every account sharing this UPI",
    "Who communicated before this transaction?",
  ]);

  const runSearch = async (q: string) => {
    if (!q.trim()) return;
    setQuery(q);
    setBusy(true);
    try {
      // Natural language queries or exact entity identifiers go through copilot query
      const result = await api.copilotQuery(q.trim());
      setDossier(result);
    } catch (e) {
      toast.error("Failed to construct Entity Intelligence Profile.");
    } finally {
      setBusy(false);
    }
  };

  if (dossier) {
    return <EntityDossier data={dossier} query={query} onBack={() => setDossier(null)} />;
  }

  return (
    <div className="min-h-[80vh] flex flex-col items-center justify-center p-4">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-4xl space-y-8"
      >
        <div className="text-center space-y-4">
          <div className="inline-flex items-center justify-center p-4 bg-emerald-500/10 rounded-full mb-2 border border-emerald-500/20">
            <BrainCircuit className="w-12 h-12 text-emerald-400" />
          </div>
          <h1 className="text-4xl md:text-5xl font-black text-slate-100 tracking-tight">
            Unified Intelligence Search
          </h1>
          <p className="text-slate-400 text-lg max-w-2xl mx-auto">
            Search across transactions, telecom metadata, IP intelligence, device fingerprints, complaints, banking relationships and temporal events.
          </p>
        </div>

        <Card className="bg-card/50 border-border shadow-2xl backdrop-blur-sm overflow-hidden">
          <div className="p-2 bg-gradient-to-r from-primary/20 via-accent/20 to-primary/20 border-b border-border" />
          <CardContent className="p-6 md:p-8">
            <form onSubmit={(e) => { e.preventDefault(); runSearch(query); }} className="relative flex items-center">
              <Search className="absolute left-4 w-6 h-6 text-primary" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search by Account, Phone, UPI, IMEI, IP, Complaint ID..."
                className="w-full h-16 pl-14 pr-32 rounded-xl bg-background border border-input text-lg text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary/50 shadow-inner transition-all"
              />
              <button
                type="submit"
                disabled={busy || !query.trim()}
                className="absolute right-2 h-12 px-6 rounded-lg bg-primary hover:bg-primary/90 text-primary-foreground font-semibold flex items-center gap-2 transition-all disabled:opacity-50"
              >
                {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : "Analyze"}
              </button>
            </form>

            <div className="mt-8">
              <h3 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground mb-4 flex items-center gap-2">
                <Zap className="w-4 h-4 text-warning" /> Natural Language Capabilities
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {suggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => setQuery(s)}
                    className="text-left px-4 py-3 rounded-lg bg-secondary/50 border border-border hover:bg-secondary hover:border-primary/50 transition-colors text-sm text-foreground flex items-center gap-3 group"
                  >
                    <Search className="w-4 h-4 text-muted-foreground group-hover:text-primary shrink-0" />
                    <span className="truncate">{s}</span>
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </motion.div>
    </div>
  );
}


function EntityDossier({ data, query, onBack }: { data: CopilotQueryResult; query: string; onBack: () => void }) {
  const isError = (!data.records || data.records.length === 0) && !data.answer && !data.executive_summary && !data.general_answer;
  const llmAnswer = data.answer || data.executive_summary || data.general_answer;

  const [panelPayload, setPanelPayload] = useState<any>(null);
  const [panelBusy, setPanelBusy] = useState(false);

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


  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="space-y-6 pb-20"
    >
      {/* Top Nav */}
      <div className="flex items-center justify-between">
        <button onClick={onBack} className="flex items-center gap-2 text-slate-400 hover:text-white transition-colors px-3 py-2 rounded-lg hover:bg-slate-800">
          <ArrowLeft className="w-4 h-4" /> Back to Search
        </button>
        <div className="flex items-center gap-3">
          <button 
            onClick={() => {
              toast.promise(api.downloadEntityReport("search", query), {
                loading: "Generating PDF Report...",
                success: "Report downloaded successfully!",
                error: "Failed to generate report."
              });
            }}
            className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 text-sm font-semibold rounded-lg border border-slate-700 transition-colors"
          >
            <FileText className="w-4 h-4 text-sky-400" /> Export PDF
          </button>
          <button 
            onClick={() => {
              toast.promise(api.downloadReport(), {
                loading: "Compiling STR...",
                success: "Suspicious Transaction Report generated!",
                error: "Failed to generate STR."
              });
            }}
            className="flex items-center gap-2 px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold rounded-lg transition-colors shadow-[0_0_15px_rgba(16,185,129,0.3)]"
          >
            <ShieldAlert className="w-4 h-4" /> Generate STR
          </button>
        </div>
      </div>

      {isError ? (
        <Card className="bg-card border-border text-center py-20">
          <ShieldAlert className="w-16 h-16 text-muted-foreground mx-auto mb-4" />
          <h2 className="text-xl font-bold text-foreground">No Intelligence Found</h2>
          <p className="text-muted-foreground mt-2">No entities or temporal correlations matched your query: "{query}"</p>
        </Card>
      ) : (
        <>
          {llmAnswer && (
            <Card className="bg-primary/5 border-primary/20 shadow-md">
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <Bot className="w-6 h-6 text-primary shrink-0 mt-1" />
                  <div>
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-primary mb-2">AI Copilot Analysis</h3>
                    <p className="text-foreground leading-relaxed whitespace-pre-wrap">{llmAnswer}</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {/* ENTITY PROFILE HEADER */}
          <Card className="bg-card/80 border-border shadow-xl overflow-hidden relative">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary via-accent to-secondary" />
            <CardContent className="p-8">
              <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                  <div className="flex items-center gap-3 mb-2">
                    <span className="px-2.5 py-1 text-[10px] uppercase tracking-widest font-bold bg-primary/20 text-primary border border-primary/30 rounded">
                      Target Identified
                    </span>
                    <span className="text-sm font-mono text-muted-foreground">
                      Query: {query}
                    </span>
                  </div>
                  <h2 className="text-3xl md:text-4xl font-black text-foreground tracking-tight flex items-center gap-3">
                    {data.investigation_summary?.primary_account || data.investigation_summary?.common_phone || "Complex Relationship Cluster"}
                  </h2>
                  <p className="text-muted-foreground mt-2 flex items-center gap-4 text-sm">
                    <span className="flex items-center gap-1.5"><Activity className="w-4 h-4" /> Active Investigation</span>
                    <span className="flex items-center gap-1.5"><Network className="w-4 h-4" /> {data.metrics?.records || data.records?.length || 0} linked records</span>
                  </p>
                </div>
                
                {/* Threat Badge */}
                <div className="flex flex-col items-end">
                  <div className={`text-4xl font-black ${(data.metrics?.highest_risk || 0) > 80 ? 'text-red-500' : 'text-amber-500'}`}>
                    {data.metrics?.highest_risk || 0}
                    <span className="text-lg text-slate-500">/100</span>
                  </div>
                  <div className="text-sm uppercase tracking-wider font-bold text-slate-400">Peak Threat Level</div>
                </div>
              </div>

              {/* Quick Badges */}
              <div className="flex flex-wrap gap-2 mt-6">
                {(data.metrics?.highest_risk || 0) > 80 && (
                  <span className="px-3 py-1.5 bg-red-500/10 border border-red-500/20 text-red-400 text-xs font-semibold rounded-md flex items-center gap-1.5">
                    <FileWarning className="w-3.5 h-3.5" /> High Risk Exposure
                  </span>
                )}
                {(data.metrics?.beneficiaries || 0) > 2 && (
                  <span className="px-3 py-1.5 bg-amber-500/10 border border-amber-500/20 text-amber-400 text-xs font-semibold rounded-md flex items-center gap-1.5">
                    <Users className="w-3.5 h-3.5" /> Multiple Beneficiaries
                  </span>
                )}
                {(data.metrics?.ips || 0) > 1 && (
                  <span className="px-3 py-1.5 bg-purple-500/10 border border-purple-500/20 text-purple-400 text-xs font-semibold rounded-md flex items-center gap-1.5">
                    <Globe className="w-3.5 h-3.5" /> Distributed IPs
                  </span>
                )}
                {(data.metrics?.phones || 0) > 1 && (
                  <span className="px-3 py-1.5 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 text-xs font-semibold rounded-md flex items-center gap-1.5">
                    <Phone className="w-3.5 h-3.5" /> Device Rotation
                  </span>
                )}
              </div>
            </CardContent>
          </Card>

          {/* RISK SUMMARY PANEL */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard title="Total Volume Fused" value={`₹${(data.metrics?.total_amount || 0).toLocaleString()}`} icon={CreditCard} color="emerald" />
            <MetricCard title="Linked Accounts" value={data.metrics?.accounts} icon={Landmark} color="sky" />
            <MetricCard title="Device Endpoints" value={data.metrics?.phones} icon={Phone} color="cyan" />
            <MetricCard title="Unique Network IPs" value={data.metrics?.ips} icon={Globe} color="purple" />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* LEFT COL: Timeline & Connected Identifiers */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* CONNECTED IDENTIFIERS */}
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Network className="w-5 h-5 text-sky-400" /> Discovered Identifiers
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {Array.from(new Set(data.records?.map(r => (r.sender_phone || r.receiver_phone || (r as any).a_party_number || (r as any).b_party_number) as string).filter(Boolean))).slice(0, 5).map((p, i) => (
                      <IdentifierBadge key={`ph-${i}`} icon={Phone} label="Phone" value={p} onClick={() => openDossier("phone", p)} />
                    ))}
                    {Array.from(new Set(data.records?.map(r => (r.account_no || r.receiver_account || r.sender_account_number || r.receiver_account_number) as string).filter(Boolean))).slice(0, 5).map((a, i) => (
                      <IdentifierBadge key={`ac-${i}`} icon={Landmark} label="Account" value={a} onClick={() => openDossier("account", a)} />
                    ))}
                    {Array.from(new Set(data.records?.map(r => (r.counterparty_name || r.receiver_customer_name) as string).filter(Boolean))).slice(0, 5).map((n, i) => (
                      <IdentifierBadge key={`na-${i}`} icon={Users} label="Entity" value={n} onClick={() => openDossier("name", n)} />
                    ))}
                  </div>
                </CardContent>
              </Card>

              {/* TEMPORAL FUSION TIMELINE */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Activity className="w-5 h-5 text-amber-400" /> Temporal Fusion Timeline
                  </CardTitle>
                  <span className="text-xs font-mono text-muted-foreground bg-secondary px-2 py-1 rounded">Chronological</span>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 border-l-2 border-border ml-3 pl-6 relative">
                    {data.records?.slice(0, 15).map((r, i) => {
                      const isHighValue = ((r.amount as number) || (r as any).transaction_amount || 0) > 100000;
                      const displayDate = r.date || (r as any).timestamp?.split(' ')[0] || (r as any).call_start_time?.split(' ')[0] || "Unknown Date";
                      const displayTime = r.time || (r as any).timestamp?.split(' ')[1] || (r as any).call_start_time?.split(' ')[1] || "";
                      const displayMode = r.mode || (r as any).transaction_type || (r as any).call_type || (r as any).type || (r.amount || (r as any).transaction_amount ? "Transaction" : "Activity");
                      let description = r.narration || r.explain_plain;
                      if (!description) {
                        const target = r.counterparty_name || r.receiver_account || (r as any).receiver_customer_name || (r as any).receiver_account_number;
                        if (target) {
                           description = `Transfer to ${target}`;
                        } else if ((r as any).a_party_number && (r as any).b_party_number) {
                           description = `Call to ${(r as any).b_party_number}`;
                        } else {
                           description = "Activity logged";
                        }
                      }
                      const amount = r.amount || (r as any).transaction_amount;

                      return (
                        <div key={i} className="relative">
                          <div className={`absolute -left-[31px] top-1 w-3 h-3 rounded-full border-2 border-background ${isHighValue ? 'bg-red-500' : 'bg-primary'}`} />
                          <button 
                            onClick={() => openDossier("transaction", String(r.transaction_id || (r as any).id || (r as any).reference_no))}
                            className="w-full text-left bg-secondary/50 p-4 rounded-xl border border-border/50 hover:bg-secondary hover:border-primary/40 transition-all group cursor-pointer"
                          >
                            <div className="flex justify-between items-start">
                              <div className="min-w-0 pr-4">
                                <div className="text-[10px] font-mono text-muted-foreground mb-1.5 flex flex-wrap items-center gap-2">
                                  <span>{displayDate} {displayTime}</span>
                                  {(r as any).bank && (
                                    <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300">{ (r as any).bank }</span>
                                  )}
                                  {(r as any).channel && (
                                    <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300">{ (r as any).channel }</span>
                                  )}
                                </div>
                                <h4 className="text-sm font-semibold text-foreground">
                                  {displayMode}
                                </h4>
                                <p className="text-xs text-muted-foreground mt-1 truncate">
                                  {description}
                                </p>
                              </div>
                              {amount != null && (
                                <div className={`font-mono text-sm font-bold shrink-0 ${isHighValue ? 'text-red-400' : 'text-emerald-400'}`}>
                                  ₹{Number(amount).toLocaleString()}
                                </div>
                              )}
                            </div>
                          </button>
                        </div>
                      )
                    })}
                  </div>
                  {(data.records?.length || 0) > 15 && (
                    <button className="w-full mt-4 py-3 text-sm text-slate-400 hover:text-emerald-400 bg-slate-800/30 rounded-lg border border-dashed border-slate-700 transition-colors">
                      View full timeline ({data.records!.length} events)
                    </button>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* RIGHT COL: AI Insights, Action Panel, Network */}
            <div className="space-y-6">
              
              {/* AI INSIGHTS */}
              <Card className="bg-card border-border border-t-4 border-t-primary">
                <CardHeader>
                  <CardTitle className="text-lg flex items-center gap-2">
                    <Bot className="w-5 h-5 text-primary" /> AI Insights
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {data.insights?.map((insight, i) => (
                    <div key={i} className="bg-secondary/50 p-3 rounded-lg border border-border/50">
                      <div className="flex items-center gap-2 mb-1">
                        <div className={`w-2 h-2 rounded-full ${insight.severity === 'high' ? 'bg-red-500' : insight.severity === 'medium' ? 'bg-amber-500' : 'bg-sky-500'}`} />
                        <span className="text-xs font-bold text-foreground uppercase tracking-wider">{insight.title}</span>
                      </div>
                      <p className="text-sm text-muted-foreground leading-relaxed">{insight.detail}</p>
                    </div>
                  ))}
                  {(!data.insights || data.insights.length === 0) && (
                    <p className="text-sm text-muted-foreground italic">No specific AI insights flagged for this cluster.</p>
                  )}
                </CardContent>
              </Card>

              {/* ACTION PANEL */}
              <Card className="bg-card border-border">
                <CardHeader>
                  <CardTitle className="text-lg">Investigation Actions</CardTitle>
                </CardHeader>
                <CardContent className="space-y-2">
                  {data.suggestions?.map((sugg, i) => (
                    <button key={i} onClick={() => alert(`Simulating action: ${sugg.action} on ${sugg.target}`)} className="w-full text-left p-3 bg-secondary hover:bg-secondary/80 rounded-lg border border-border transition-colors group">
                      <h4 className="text-sm font-semibold text-primary group-hover:text-primary/80 flex items-center justify-between">
                        {sugg.action}
                        <ArrowLeft className="w-4 h-4 rotate-135 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </h4>
                      <p className="text-xs text-muted-foreground mt-1">{sugg.why}</p>
                    </button>
                  ))}
                  {/* QUICK ACTIONS */}
                  <div className="grid grid-cols-2 gap-4">
                    <button className="flex items-center justify-center gap-2 p-4 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 font-bold rounded-xl border border-emerald-500/20 transition-colors">
                      <PlusCircle className="w-5 h-5" /> Add to Watchlist
                    </button>
                    <button className="flex items-center justify-center gap-2 p-4 bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 font-bold rounded-xl border border-sky-500/20 transition-colors">
                      <Share2 className="w-5 h-5" /> Share Intelligence
                    </button>
                  </div>
                </CardContent>
              </Card>
            </div>

          </div>
        </>
      )}

      {/* RENDER THE DOSSIER PANEL WHEN TILES OR TIMELINE ITEMS ARE CLICKED */}
      <InvestigationPanel 
        data={panelPayload} 
        onClose={() => setPanelPayload(null)} 
        onEntitySelect={openDossier} 
      />
    </motion.div>
  );
}


function MetricCard({ title, value, icon: Icon, color }: { title: string, value: any, icon: any, color: "emerald" | "sky" | "cyan" | "purple" }) {
  const colorMap = {
    emerald: "text-emerald-400 bg-emerald-500/10",
    sky: "text-sky-400 bg-sky-500/10",
    cyan: "text-cyan-400 bg-cyan-500/10",
    purple: "text-purple-400 bg-purple-500/10",
  };
  
  return (
    <Card className="bg-card border-border">
      <CardContent className="p-4 flex items-center gap-4">
        <div className={`p-3 rounded-xl ${colorMap[color]}`}>
          <Icon className="w-6 h-6" />
        </div>
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</p>
          <p className="text-2xl font-black text-foreground mt-0.5">{value || 0}</p>
        </div>
      </CardContent>
    </Card>
  );
}


function IdentifierBadge({ icon: Icon, label, value, onClick }: { icon: any, label: string, value: string, onClick?: () => void }) {
  return (
    <div onClick={onClick} className="flex flex-col items-center justify-center p-3 bg-secondary/50 rounded-lg border border-border/50 hover:bg-secondary hover:border-primary/50 transition-colors cursor-pointer group">
      <Icon className="w-5 h-5 text-muted-foreground group-hover:text-primary mb-2 transition-colors" />
      <span className="text-[10px] uppercase tracking-widest text-muted-foreground mb-1">{label}</span>
      <span className="text-sm font-mono text-foreground font-semibold max-w-[120px] truncate" title={value}>{value}</span>
    </div>
  );
}

