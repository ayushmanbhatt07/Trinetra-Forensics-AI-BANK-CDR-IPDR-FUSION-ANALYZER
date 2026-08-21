"use client";

import React, { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { 
  Search, Loader2, Hash, Phone, Landmark, CreditCard, FileWarning, Globe, 
  ArrowLeft, ShieldAlert, Activity, Users, Network, Bot, BrainCircuit, 
  FileText, Zap, PlusCircle, Share2, PhoneCall, Clock, ExternalLink, ChevronRight,
  Smartphone
} from "lucide-react";
import { api, type CopilotQueryResult } from "@/lib/api";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { InvestigationPanel } from "@/components/dashboard/investigation-panel";
import { EventDossierPanel } from "@/components/dashboard/event-dossier";
import { usePipeline } from "@/lib/pipeline-context";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const normalizeMarkdown = (text: any): string => {
  if (!text) return "";
  let s = String(text).replace(/\\n/g, "\n");
  s = s.replace(/\|\s*\|+/g, "|\n|");
  return s.trim();
};

export const SearchSection = React.memo(function SearchSection() {
  const { pipeline } = usePipeline();
  const [query, setQuery] = useState("");
  const [dossier, setDossier] = useState<CopilotQueryResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [suggestions] = useState([
    "Show every transfer within 10 minutes of a call to +91",
    "Show all devices linked to this account",
    "Find every account sharing this UPI",
    "Who communicated before this transaction?",
  ]);

  useEffect(() => {
    setDossier(null);
  }, [pipeline?.dataset_id]);

  const runSearch = async (q: string) => {
    if (!q.trim()) return;
    setQuery(q);
    setBusy(true);
    try {
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
});


function EntityDossier({ data, query, onBack }: { data: CopilotQueryResult; query: string; onBack: () => void }) {
  const hasRecords = Boolean(data.records && data.records.length > 0);
  const isError = !hasRecords && !data.answer && !data.executive_summary && !data.general_answer;
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

  const openEventDossier = async (sourceType: string, eventId: string) => {
    if (!eventId) return;
    setPanelBusy(true);
    try {
      const info = await api.eventDossier(sourceType, eventId);
      setPanelPayload({ type: "event", info });
    } catch (e: any) {
      openDossier("transaction", eventId);
    } finally {
      setPanelBusy(false);
    }
  };

  // Extract Accounts with holder names and bank details
  const discoveredAccounts = Array.from(
    new Map(
      data.records
        ?.map((r: any) => {
          const acc = r.account_no || r.receiver_account || r.sender_account_number || r.receiver_account_number;
          if (!acc) return null;
          const holder = r.account_name || r.customer_name || r.holder || r.sender_customer_name || r.counterparty_name || r.receiver_customer_name || "";
          const bank = r.bank || r.sender_bank_name || r.counterparty_bank || r.receiver_bank_name || "";
          return [String(acc), { acc: String(acc), holder, bank }];
        })
        .filter(Boolean) as [string, { acc: string; holder: string; bank: string }][]
    ).values()
  );

  // Extract Phone Numbers with connected subscriber / role info
  const discoveredPhones = Array.from(
    new Map(
      data.records
        ?.flatMap((r: any) => {
          const list: [string, { phone: string; role: string }][] = [];
          const p1 = r.sender_phone || r.customer_phone || r.sender_phone_number || r.a_party_number || r.phone || r.msisdn;
          if (p1) list.push([String(p1), { phone: String(p1), role: "Sender / Caller" }]);
          const p2 = r.receiver_phone || r.receiver_phone_number || r.b_party_number;
          if (p2) list.push([String(p2), { phone: String(p2), role: "Receiver / Contact" }]);
          return list;
        })
        .filter(Boolean)
    ).values()
  );

  // Extract Entity Names (Holders, Counterparties)
  const discoveredEntities = Array.from(
    new Set(
      data.records
        ?.flatMap((r: any) => [
          r.customer_name,
          r.account_name,
          r.sender_customer_name,
          r.counterparty_name,
          r.receiver_customer_name,
          r.holder,
        ])
        .filter((n): n is string => Boolean(n && typeof n === "string" && n.trim().length > 1))
    )
  );

  // Extract Devices (IMEIs)
  const discoveredDevices = Array.from(
    new Set(
      data.records
        ?.flatMap((r: any) => [r.device_imei, r.imei, r.device_id])
        .filter((d): d is string => Boolean(d && typeof d === "string" && d.trim().length > 3 && d !== "Unknown" && d !== "none"))
    )
  );

  // Extract IPs
  const discoveredIps = Array.from(
    new Set(
      data.records
        ?.flatMap((r: any) => [r.source_ip_address, r.source_ip, r.ip, r.destination_ip_address, r.destination_ip, r.private_ipv4])
        .filter((ip): ip is string => Boolean(ip && typeof ip === "string" && ip.trim().length > 5 && ip !== "Unknown" && ip !== "none"))
    )
  );

  const queryEntityMatch = query.match(/\b(?:TXN|ATM|UPI|IMPS|CDR|IPDR)[A-Z0-9]{4,}\b/i) || query.match(/\b\d{8,18}\b/);
  const primaryTargetId = 
    data.entity_resolution?.entity_id 
    || (queryEntityMatch ? queryEntityMatch[0].toUpperCase() : null)
    || data.investigation_summary?.primary_account 
    || data.investigation_summary?.common_phone 
    || discoveredAccounts[0]?.acc 
    || discoveredPhones[0]?.phone
    || discoveredDevices[0]
    || "Entity Record";

  const primaryHolderName = discoveredAccounts[0]?.holder || discoveredEntities[0] || (discoveredDevices[0] ? `Device ${discoveredDevices[0]}` : "Target Subject");

  const totalVolume = (data.metrics?.total_amount || 0) > 0 
    ? data.metrics?.total_amount 
    : data.records?.reduce((acc: number, r: any) => {
        const val = r.transaction_amount ?? r.amount ?? r.debit ?? r.credit ?? 0;
        return acc + (Number(val) || 0);
      }, 0) || 0;

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
            <Card className="bg-primary/5 border-primary/20 shadow-md overflow-hidden">
              <CardContent className="p-6">
                <div className="flex items-start gap-4">
                  <Bot className="w-6 h-6 text-primary shrink-0 mt-1" />
                  <div className="w-full space-y-2">
                    <h3 className="text-sm font-semibold uppercase tracking-wider text-primary mb-2">AI Copilot Analysis</h3>
                    <div className="text-foreground leading-relaxed text-xs sm:text-sm font-sans space-y-2">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          h1: ({ node, ...props }) => <h1 className="text-base font-bold text-cyan-300 mt-2 mb-1" {...props} />,
                          h2: ({ node, ...props }) => <h2 className="text-sm font-bold text-cyan-300 mt-2 mb-1" {...props} />,
                          h3: ({ node, ...props }) => <h3 className="text-xs font-bold font-mono uppercase tracking-wider text-cyan-400 mt-3 mb-1.5 flex items-center gap-1.5" {...props} />,
                          ul: ({ node, ...props }) => <ul className="list-disc pl-4 space-y-1 my-1 text-xs" {...props} />,
                          ol: ({ node, ...props }) => <ol className="list-decimal pl-4 space-y-1 my-1 text-xs" {...props} />,
                          p: ({ node, ...props }) => <p className="leading-relaxed my-1 text-xs" {...props} />,
                          table: ({ node, ...props }) => (
                            <div className="overflow-x-auto my-2.5 rounded-lg border border-cyan-500/30 bg-slate-950/70 shadow-md">
                              <table className="w-full text-xs text-left border-collapse" {...props} />
                            </div>
                          ),
                          thead: ({ node, ...props }) => <thead className="bg-cyan-950/50 text-cyan-300 font-mono text-[11px] border-b border-cyan-500/30" {...props} />,
                          th: ({ node, ...props }) => <th className="p-2 border-b border-cyan-500/30 font-semibold tracking-wide" {...props} />,
                          td: ({ node, ...props }) => <td className="p-2 border-b border-border/30 font-mono text-[11px] text-foreground/90" {...props} />,
                          tr: ({ node, ...props }) => <tr className="hover:bg-cyan-500/5 transition-colors border-b border-border/20" {...props} />,
                          code: ({ node, ...props }) => <code className="rounded bg-slate-800/90 px-1 py-0.5 font-mono text-[11px] text-cyan-300 border border-slate-700/50" {...props} />,
                          strong: ({ node, ...props }) => <strong className="font-semibold text-slate-100" {...props} />
                        }}
                      >
                        {normalizeMarkdown(llmAnswer)}
                      </ReactMarkdown>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}

          {!hasRecords ? (
            <Card className="bg-card/60 border-border text-center py-12 px-6 shadow-md">
              <ShieldAlert className="w-12 h-12 text-amber-400 mx-auto mb-3 opacity-80" />
              <h3 className="text-lg font-bold text-foreground">Zero Direct Records Found</h3>
              <p className="text-sm text-muted-foreground mt-2 max-w-lg mx-auto">
                No matching financial transactions, CDR tower logs, or IPDR sessions were found for target identifier <strong className="text-slate-200 font-mono">{primaryTargetId}</strong>.
              </p>
              <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
                <button 
                  onClick={onBack}
                  className="px-4 py-2 bg-secondary hover:bg-secondary/80 text-foreground text-xs font-semibold rounded-lg border border-border transition-colors flex items-center gap-2 cursor-pointer"
                >
                  <ArrowLeft className="w-3.5 h-3.5" /> Try Another Query
                </button>
              </div>
            </Card>
          ) : (
            <>
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
                    {primaryTargetId}
                  </h2>
                  <div className="text-sm font-medium text-emerald-400 mt-1 flex items-center gap-2">
                    <Users className="w-4 h-4 text-emerald-400" />
                    <span>Entity Subject: <strong>{primaryHolderName}</strong></span>
                  </div>
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
            <MetricCard title="Total Volume Fused" value={`₹${totalVolume.toLocaleString("en-IN")}`} icon={CreditCard} color="emerald" />
            <MetricCard title="Linked Accounts" value={discoveredAccounts.length || data.metrics?.accounts || 0} icon={Landmark} color="sky" onClick={() => discoveredAccounts[0] && openDossier("account", discoveredAccounts[0].acc)} />
            <MetricCard title="Device Endpoints" value={discoveredDevices.length || discoveredPhones.length || data.metrics?.phones || 0} icon={Smartphone} color="cyan" onClick={() => (discoveredDevices[0] ? openDossier("imei", discoveredDevices[0]) : (discoveredPhones[0] && openDossier("phone", discoveredPhones[0].phone)))} />
            <MetricCard title="Unique Network IPs" value={discoveredIps.length || data.metrics?.ips || 0} icon={Globe} color="purple" onClick={() => discoveredIps[0] && openDossier("ip", discoveredIps[0])} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* LEFT COL: Discovered Identifiers & Timeline */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* DISCOVERED IDENTIFIERS */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between pb-3 border-b border-border/60">
                  <CardTitle className="text-lg flex items-center gap-2 text-cyan-400">
                    <Network className="w-5 h-5 text-cyan-400" /> Discovered Identifiers & Connections
                  </CardTitle>
                  <span className="text-xs text-muted-foreground">Click any card for 360° dossier</span>
                </CardHeader>
                <CardContent className="pt-4 space-y-4">
                  {/* Accounts Grid */}
                  {discoveredAccounts.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Landmark className="w-3.5 h-3.5 text-cyan-400" /> Bank Accounts ({discoveredAccounts.length})
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {discoveredAccounts.map((item, i) => (
                          <div 
                            key={`acc-${i}`}
                            onClick={() => openDossier("account", item.acc)}
                            className="p-3 bg-secondary/40 hover:bg-secondary border border-border/60 hover:border-cyan-500/50 rounded-xl transition-all cursor-pointer group space-y-1 shadow-sm"
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold uppercase text-cyan-400">Bank Account</span>
                              <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-cyan-400 transition-colors" />
                            </div>
                            <p className="font-mono text-sm font-bold text-foreground break-all">{item.acc}</p>
                            {item.holder && <p className="text-xs font-medium text-slate-300 truncate">Holder: {item.holder}</p>}
                            {item.bank && <p className="text-[11px] text-muted-foreground">{item.bank}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Devices Grid */}
                  {discoveredDevices.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Smartphone className="w-3.5 h-3.5 text-cyan-400" /> Linked Device Hardware / IMEIs ({discoveredDevices.length})
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {discoveredDevices.map((imei, i) => (
                          <div 
                            key={`dev-${i}`}
                            onClick={() => openDossier("imei", imei)}
                            className="p-3 bg-secondary/40 hover:bg-secondary border border-border/60 hover:border-cyan-500/50 rounded-xl transition-all cursor-pointer group space-y-1 shadow-sm"
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold uppercase text-cyan-400">Device Hardware IMEI</span>
                              <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-cyan-400 transition-colors" />
                            </div>
                            <p className="font-mono text-sm font-bold text-foreground break-all">{imei}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* IPs Grid */}
                  {discoveredIps.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Globe className="w-3.5 h-3.5 text-purple-400" /> Network IP Addresses ({discoveredIps.length})
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {discoveredIps.map((ip, i) => (
                          <div 
                            key={`ip-${i}`}
                            onClick={() => openDossier("ip", ip)}
                            className="p-3 bg-secondary/40 hover:bg-secondary border border-border/60 hover:border-purple-500/50 rounded-xl transition-all cursor-pointer group space-y-1 shadow-sm"
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold uppercase text-purple-400">Network IP Address</span>
                              <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-purple-400 transition-colors" />
                            </div>
                            <p className="font-mono text-sm font-bold text-foreground break-all">{ip}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Phones Grid */}
                  {discoveredPhones.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Phone className="w-3.5 h-3.5 text-cyan-400" /> Telecom Phone Numbers ({discoveredPhones.length})
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {discoveredPhones.map((item, i) => (
                          <div 
                            key={`ph-${i}`}
                            onClick={() => openDossier("phone", item.phone)}
                            className="p-3 bg-secondary/40 hover:bg-secondary border border-border/60 hover:border-cyan-500/50 rounded-xl transition-all cursor-pointer group space-y-1 shadow-sm"
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold uppercase text-emerald-400">{item.role}</span>
                              <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-emerald-400 transition-colors" />
                            </div>
                            <p className="font-mono text-sm font-bold text-foreground break-all">{item.phone}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Entities Grid */}
                  {discoveredEntities.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                        <Users className="w-3.5 h-3.5 text-cyan-400" /> Entity Names / Parties ({discoveredEntities.length})
                      </p>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {discoveredEntities.map((name, i) => (
                          <div 
                            key={`ent-${i}`}
                            onClick={() => openDossier("name", name)}
                            className="p-3 bg-secondary/40 hover:bg-secondary border border-border/60 hover:border-cyan-500/50 rounded-xl transition-all cursor-pointer group space-y-1 shadow-sm"
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-[10px] font-bold uppercase text-amber-400">Customer Subject</span>
                              <ChevronRight className="w-4 h-4 text-muted-foreground group-hover:text-amber-400 transition-colors" />
                            </div>
                            <p className="text-sm font-bold text-foreground truncate">{name}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>

              {/* TEMPORAL FUSION TIMELINE */}
              <Card className="bg-card border-border">
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-lg flex items-center gap-2 text-amber-400">
                    <Activity className="w-5 h-5 text-amber-400" /> Temporal Fusion Timeline
                  </CardTitle>
                  <span className="text-xs font-mono text-muted-foreground bg-secondary px-2 py-1 rounded">Chronological</span>
                </CardHeader>
                <CardContent>
                  <div className="space-y-4 border-l-2 border-border ml-3 pl-6 relative">
                    {data.records?.slice(0, 15).map((r: any, i: number) => {
                      const isHighValue = (Number(r.amount || r.transaction_amount || r.credit || r.debit || 0)) > 50000;
                      const dateStr = r.date || (r.timestamp ? r.timestamp.split(" ")[0] : "");
                      const timeStr = r.time || (r.timestamp ? r.timestamp.split(" ")[1] : "");
                      const mode = r.mode || r.transaction_mode || r.call_type || (r.amount ? "Transaction" : "Activity");
                      
                      const senderName = r.account_name || r.customer_name || r.sender_customer_name || r.sender_name || "Sender Customer";
                      const senderAccount = r.account_no || r.sender_account_number || r.sender_account || "N/A";
                      const senderPhone = r.sender_phone || r.customer_phone || r.sender_phone_number || r.phone || r.a_party_number || "";
                      const senderBank = r.bank || r.sender_bank_name || "";

                      const receiverName = r.counterparty_name || r.receiver_customer_name || r.receiver_name || "Destination Account";
                      const receiverAccount = r.receiver_account || r.receiver_account_number || r.counterparty_account || "N/A";
                      const receiverPhone = r.receiver_phone || r.receiver_phone_number || r.b_party_number || "";
                      const receiverBank = r.counterparty_bank || r.receiver_bank_name || "";

                      const amountVal = r.amount || r.transaction_amount || r.credit || r.debit;
                      const eventId = r.transaction_id || r.txn_id || r.record_id || r.id || r.reference_no || `EVT_${i}`;
                      const sourceType = (r.mode || r.bank || r.account_no) ? "BANK" : (r.call_type || r.a_party_number) ? "CDR" : "IPDR";

                      return (
                        <div key={i} className="relative group">
                          <div className={`absolute -left-[31px] top-4 w-3.5 h-3.5 rounded-full border-2 border-background shadow-md ${isHighValue ? 'bg-rose-500 ring-4 ring-rose-500/20' : 'bg-cyan-500'}`} />
                          <div 
                            onClick={() => openEventDossier(sourceType, String(eventId))}
                            className="w-full text-left bg-card/60 p-4 rounded-xl border border-border/80 hover:bg-muted/40 hover:border-cyan-500/50 transition-all cursor-pointer shadow-sm space-y-3"
                          >
                            {/* Header row: date/time, ID, badges, amount */}
                            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/40 pb-2">
                              <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
                                <Clock className="w-3.5 h-3.5 text-cyan-400" />
                                <span>{dateStr} {timeStr}</span>
                                <span className="text-slate-600">|</span>
                                <span className="font-semibold text-slate-300">ID: {eventId}</span>
                              </div>
                              <div className="flex items-center gap-2">
                                <Badge variant="outline" className="border-cyan-500/40 bg-cyan-500/10 text-cyan-300 font-mono text-[10px] uppercase">
                                  {mode}
                                </Badge>
                                {amountVal != null && (
                                  <span className={`font-mono text-sm font-bold ${isHighValue ? 'text-rose-400' : 'text-emerald-400'}`}>
                                    ₹{Number(amountVal).toLocaleString("en-IN")}
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Transfer Cycle Flow OR Cyber / Device Session */}
                            {(r.device_imei || r.source_ip_address) && senderAccount === "N/A" && receiverAccount === "N/A" ? (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                                <div className="rounded-lg border border-border/50 bg-secondary/30 p-2.5 space-y-0.5">
                                  <p className="text-[9px] uppercase font-bold text-cyan-400">Device & Subscriber Details</p>
                                  <p className="text-xs font-semibold text-foreground truncate">
                                    IMEI: <span className="font-mono text-cyan-300">{r.device_imei || r.imei || "Hardware Endpoint"}</span>
                                  </p>
                                  <div className="text-[11px] text-muted-foreground font-mono flex flex-wrap gap-x-2">
                                    {(r.subscriber_msisdn || r.phone) && <span>MSISDN: <strong className="text-slate-200">{r.subscriber_msisdn || r.phone}</strong></span>}
                                    {r.subscriber_imsi && <span>IMSI: <strong className="text-slate-200">{r.subscriber_imsi}</strong></span>}
                                  </div>
                                </div>

                                <div className="rounded-lg border border-border/50 bg-secondary/30 p-2.5 space-y-0.5">
                                  <p className="text-[9px] uppercase font-bold text-purple-400">Network Routing Footprint</p>
                                  <p className="text-xs font-semibold text-foreground truncate">
                                    Source IP: <span className="font-mono text-purple-300">{r.source_ip_address || r.source_ip || "N/A"}</span>
                                  </p>
                                  <div className="text-[11px] text-muted-foreground font-mono flex flex-wrap gap-x-2">
                                    {(r.destination_ip_address || r.dest_ip) && <span>Dest IP: <strong className="text-slate-200">{r.destination_ip_address || r.dest_ip}</strong></span>}
                                    {(r.source_port || r.dest_port) && <span>Ports: <strong className="text-slate-200">{r.source_port || "-"}:{r.dest_port || "-"}</strong></span>}
                                  </div>
                                </div>
                              </div>
                            ) : (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                                {/* FROM */}
                                <div className="rounded-lg border border-border/50 bg-secondary/30 p-2.5 space-y-0.5">
                                  <p className="text-[9px] uppercase font-bold text-slate-400">From (Sender Entity)</p>
                                  <p className="text-xs font-semibold text-foreground truncate">{senderName}</p>
                                  <div className="text-[11px] text-muted-foreground font-mono flex flex-wrap gap-x-2">
                                    <span>Acc: <strong className="text-slate-200">{senderAccount}</strong></span>
                                    {senderPhone && <span>Ph: <strong className="text-cyan-300">{senderPhone}</strong></span>}
                                    {senderBank && <span>({senderBank})</span>}
                                  </div>
                                </div>

                                {/* TO */}
                                <div className="rounded-lg border border-border/50 bg-secondary/30 p-2.5 space-y-0.5">
                                  <p className="text-[9px] uppercase font-bold text-amber-400">To (Sent Destination)</p>
                                  <p className="text-xs font-semibold text-foreground truncate">{receiverName}</p>
                                  <div className="text-[11px] text-muted-foreground font-mono flex flex-wrap gap-x-2">
                                    <span>Acc: <strong className="text-slate-200">{receiverAccount}</strong></span>
                                    {receiverPhone && <span>Ph: <strong className="text-cyan-300">{receiverPhone}</strong></span>}
                                    {receiverBank && <span>({receiverBank})</span>}
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Connected Phone Links */}
                            {(senderPhone || receiverPhone) && (
                              <div className="flex items-center gap-2 text-xs text-cyan-300 bg-cyan-950/20 border border-cyan-500/20 px-3 py-1.5 rounded-lg">
                                <PhoneCall className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                                <span>Connected Phones: <strong className="font-mono text-cyan-200">{[senderPhone, receiverPhone].filter(Boolean).join(" ↔ ")}</strong></span>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* RIGHT COL: AI Insights, Action Panel */}
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
                <CardContent className="space-y-3">
                  <button 
                    onClick={() => openDossier("account", primaryTargetId)}
                    className="w-full text-left p-3 bg-secondary hover:bg-secondary/80 rounded-lg border border-border transition-colors group cursor-pointer"
                  >
                    <h4 className="text-sm font-semibold text-cyan-400 group-hover:text-cyan-300 flex items-center justify-between">
                      Investigate Entity Profile
                      <ChevronRight className="w-4 h-4 text-cyan-400" />
                    </h4>
                    <p className="text-xs text-muted-foreground mt-1">Open 360-degree forensic dossier for target {primaryTargetId}.</p>
                  </button>

                  <button 
                    onClick={() => openDossier("account", primaryTargetId)}
                    className="w-full text-left p-3 bg-secondary hover:bg-secondary/80 rounded-lg border border-border transition-colors group cursor-pointer"
                  >
                    <h4 className="text-sm font-semibold text-emerald-400 group-hover:text-emerald-300 flex items-center justify-between">
                      Trace Money Flow
                      <ChevronRight className="w-4 h-4 text-emerald-400" />
                    </h4>
                    <p className="text-xs text-muted-foreground mt-1">Examine inflow and outflow destinations for account {primaryTargetId}.</p>
                  </button>

                  {discoveredPhones[0] && (
                    <button 
                      onClick={() => openDossier("phone", discoveredPhones[0].phone)}
                      className="w-full text-left p-3 bg-secondary hover:bg-secondary/80 rounded-lg border border-border transition-colors group cursor-pointer"
                    >
                      <h4 className="text-sm font-semibold text-sky-400 group-hover:text-sky-300 flex items-center justify-between">
                        Find Linked Calls ({discoveredPhones[0].phone})
                        <ChevronRight className="w-4 h-4 text-sky-400" />
                      </h4>
                      <p className="text-xs text-muted-foreground mt-1">Pull CDR call records & cell tower locations.</p>
                    </button>
                  )}

                  {/* QUICK ACTIONS */}
                  <div className="grid grid-cols-2 gap-3 pt-2">
                    <button 
                      onClick={() => toast.success(`Target ${primaryTargetId} added to active watchlist.`)}
                      className="flex items-center justify-center gap-2 p-3 bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 font-bold text-xs rounded-xl border border-emerald-500/20 transition-colors cursor-pointer"
                    >
                      <PlusCircle className="w-4 h-4" /> Add to Watchlist
                    </button>
                    <button 
                      onClick={() => {
                        navigator.clipboard.writeText(`Investigation Report for ${primaryTargetId}: ${window.location.href}`);
                        toast.success("Intelligence link copied to clipboard!");
                      }}
                      className="flex items-center justify-center gap-2 p-3 bg-sky-500/10 hover:bg-sky-500/20 text-sky-400 font-bold text-xs rounded-xl border border-sky-500/20 transition-colors cursor-pointer"
                    >
                      <Share2 className="w-4 h-4" /> Share Intelligence
                    </button>
                  </div>
                </CardContent>
              </Card>
            </div>

          </div>
            </>
          )}
        </>
      )}

      {/* RENDER THE DOSSIER PANEL WHEN TILES OR TIMELINE ITEMS ARE CLICKED */}
      {panelPayload && panelPayload.type === "entity" && (
        <InvestigationPanel 
          data={panelPayload} 
          onClose={() => setPanelPayload(null)} 
          onEntitySelect={(k, v) => openDossier(k, v)} 
        />
      )}
      {panelPayload && panelPayload.type === "event" && (
        <EventDossierPanel 
          dossier={panelPayload.info} 
          onClose={() => setPanelPayload(null)} 
          onEntitySelect={(k, v) => openDossier(k, v)} 
        />
      )}
    </motion.div>
  );
}


function MetricCard({ title, value, icon: Icon, color, onClick }: { title: string, value: any, icon: any, color: "emerald" | "sky" | "cyan" | "purple", onClick?: () => void }) {
  const colorMap = {
    emerald: "text-emerald-400 bg-emerald-500/10",
    sky: "text-sky-400 bg-sky-500/10",
    cyan: "text-cyan-400 bg-cyan-500/10",
    purple: "text-purple-400 bg-purple-500/10",
  };
  
  return (
    <Card onClick={onClick} className={`bg-card border-border ${onClick ? 'cursor-pointer hover:border-cyan-500/50 transition-colors' : ''}`}>
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
