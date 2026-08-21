
"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Landmark, Phone, Smartphone, Globe, AtSign, User, FileDown, Loader2,
  AlertTriangle, ArrowUpDown, Clock, PhoneCall, Network, ShieldAlert,
  ChevronRight, BrainCircuit, Activity, Link as LinkIcon, Crosshair,
  FileText, Code, Share2, PlusCircle, ExternalLink, ActivitySquare, History, X
} from "lucide-react";
import { api, type DossierIntelligence, type RelationshipIntel } from "@/lib/api";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";

type PanelData =
  | { type: "entity"; info: DossierIntelligence }
  | { type: "relationship"; rel: RelationshipIntel };

const BAND_CLASS: Record<string, string> = {
  CRITICAL: "bg-red-500/15 text-red-400 border-red-500/30",
  HIGH: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  MEDIUM: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  LOW: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
  SAFE: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
};

const KIND_ICON: Record<string, React.ElementType> = {
  account: Landmark,
  phone: Phone,
  device: Smartphone,
  ip: Globe,
  upi: AtSign,
  name: User,
  imei: Smartphone,
  imsi: Smartphone,
  transaction: Activity,
};

const fmtMoney = (n: number | undefined) => n ? "Rs " + Math.round(n).toLocaleString("en-IN") : "—";

function Section({ title, children, icon: Icon }: { title: string; children: React.ReactNode, icon?: React.ElementType }) {
  return (
    <div className="space-y-3">
      <h4 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-2">
        {Icon && <Icon className="w-4 h-4 text-emerald-500" />}
        {title}
      </h4>
      {children}
    </div>
  );
}

function Kpi({ label, value, accent }: { label: string; value: string | number | undefined | boolean; accent?: string }) {
  const displayValue = typeof value === 'boolean' ? (value ? 'Yes' : 'No') : (value ?? "—");
  return (
    <div className="rounded-xl border border-border/60 bg-secondary/30 px-3.5 py-3 min-w-0 shadow-sm">
      <p className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground truncate">{label}</p>
      <p className={`font-mono text-sm font-semibold break-words select-all leading-snug mt-0.5 ${accent ?? "text-foreground"}`} title={String(displayValue)}>{displayValue}</p>
    </div>
  );
}

const markdownComponents = {
  p: ({ children }: any) => <p className="text-sm text-foreground/90 leading-relaxed mb-2.5">{children}</p>,
  ul: ({ children }: any) => <ul className="space-y-2.5 my-3 pl-1">{children}</ul>,
  ol: ({ children }: any) => <ol className="space-y-2.5 my-3 pl-1">{children}</ol>,
  li: ({ children }: any) => (
    <li className="flex items-start gap-3 text-sm text-slate-100 leading-relaxed bg-card/70 p-3.5 rounded-xl border border-border/60 shadow-sm">
      <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shrink-0 mt-1.5 shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
      <span className="flex-1 font-sans">{children}</span>
    </li>
  ),
};

export function InvestigationPanel({
  data,
  onClose,
  onEntitySelect,
}: {
  data: PanelData | null;
  onClose: () => void;
  onEntitySelect: (kind: string, value: string) => void;
}) {
  const [downloading, setDownloading] = useState(false);
  if (!data) return null;

  const download = async () => {
    setDownloading(true);
    setTimeout(() => {
      toast.success("Dossier exported");
      setDownloading(false);
    }, 1500);
  };

  const rel = data.type === "relationship" ? data.rel : null;
  const dossier = data.type === "entity" ? data.info : null;
  const Icon = dossier ? KIND_ICON[dossier.kind || "entity"] ?? Network : ArrowUpDown;
  const title = dossier
    ? `${(dossier.kind || "ENTITY").toUpperCase()} DOSSIER — ${dossier.value}`
    : rel
      ? `RELATIONSHIP — ${rel.a} ↔ ${rel.b}`
      : "";

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent 
        showCloseButton={false}
        onInteractOutside={() => onClose()}
        className="w-[94vw] max-w-[1400px] sm:max-w-[94vw] lg:max-w-[1400px] max-h-[92vh] overflow-hidden flex flex-col p-0 gap-0 bg-background border border-border/60 shadow-2xl"
      >
        
        {/* Header */}
        <div className="flex-none p-6 border-b border-border bg-card/40 flex flex-col gap-4">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="rounded-xl border border-border bg-secondary/60 p-3 shadow-inner">
                <Icon className="h-6 w-6 text-emerald-500" />
              </div>
              <div className="min-w-0">
                <DialogTitle className="font-mono text-xl tracking-tight break-all">{title}</DialogTitle>
                {dossier && (
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <Badge className={`px-3 py-1 uppercase font-bold tracking-widest ${BAND_CLASS[dossier.primary?.risk_band || "SAFE"] ?? BAND_CLASS.LOW}`}>
                      {dossier.primary?.risk_band || "SAFE"} RISK
                    </Badge>
                    <div className="flex items-baseline gap-1 bg-secondary/40 px-3 py-1 rounded-full border border-border">
                      <span className="font-mono text-sm font-bold text-foreground">
                        {dossier.primary?.risk_score || 0}
                      </span>
                      <span className="text-xs text-muted-foreground uppercase tracking-widest">Score</span>
                    </div>
                    {(dossier.primary?.confidence || 0) > 0 && (
                      <div className="flex items-baseline gap-1 bg-secondary/40 px-3 py-1 rounded-full border border-border">
                        <span className="font-mono text-sm font-bold text-foreground">
                          {Math.round(dossier.primary.confidence * 100)}%
                        </span>
                        <span className="text-xs text-muted-foreground uppercase tracking-widest">AI Confidence</span>
                      </div>
                    )}
                    {(dossier.primary?.fraud_probability || 0) > 0 && (
                      <div className="flex items-baseline gap-1 bg-red-500/10 px-3 py-1 rounded-full border border-red-500/20">
                        <span className="font-mono text-sm font-bold text-red-400">
                          {Math.round(dossier.primary.fraud_probability!)}%
                        </span>
                        <span className="text-xs text-red-400/80 uppercase tracking-widest">Fraud Prob</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
            
            {/* Action Buttons & Close */}
            <div className="flex items-center gap-2 flex-wrap">
              <Button onClick={download} variant="outline" size="sm" className="h-8 gap-1.5 bg-secondary/30 text-xs">
                <FileDown className="h-3.5 w-3.5" /> PDF
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1.5 bg-secondary/30 text-xs">
                <ShieldAlert className="h-3.5 w-3.5" /> STR
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1.5 bg-secondary/30 text-xs">
                <Code className="h-3.5 w-3.5" /> JSON
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1.5 bg-secondary/30 text-xs">
                <Share2 className="h-3.5 w-3.5" /> Share
              </Button>
              <Button variant="outline" size="sm" className="h-8 gap-1.5 bg-secondary/30 text-xs">
                <PlusCircle className="h-3.5 w-3.5" /> Add to Case
              </Button>
              <Button variant="default" size="sm" className="h-8 gap-1.5 text-xs bg-emerald-600 hover:bg-emerald-500 text-white">
                <Network className="h-3.5 w-3.5" /> Graph View
              </Button>
              <button
                type="button"
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  onClose();
                }}
                className="h-8 w-8 rounded-lg border border-border/80 bg-secondary/60 hover:bg-rose-500/20 hover:border-rose-500/50 hover:text-rose-400 text-muted-foreground transition-all cursor-pointer flex items-center justify-center ml-1 shadow-sm"
                title="Close"
                aria-label="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto">
          {dossier && (
            <Tabs defaultValue="overview" className="w-full">
              <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b border-border px-6 pt-2">
                <TabsList className="bg-transparent gap-2 sm:gap-6 h-auto py-2 flex-wrap">
                  <TabsTrigger value="overview" className="data-[state=active]:bg-secondary/40 text-muted-foreground border border-transparent data-[state=active]:border-border rounded-lg px-3 font-mono text-xs uppercase tracking-wider">Overview</TabsTrigger>
                  <TabsTrigger value="identities" className="data-[state=active]:bg-secondary/40 text-muted-foreground border border-transparent data-[state=active]:border-border rounded-lg px-3 font-mono text-xs uppercase tracking-wider">Identities</TabsTrigger>
                  <TabsTrigger value="history" className="data-[state=active]:bg-secondary/40 text-muted-foreground border border-transparent data-[state=active]:border-border rounded-lg px-3 font-mono text-xs uppercase tracking-wider">History & Net</TabsTrigger>
                  <TabsTrigger value="journey" className="data-[state=active]:bg-secondary/40 text-muted-foreground border border-transparent data-[state=active]:border-border rounded-lg px-3 font-mono text-xs uppercase tracking-wider">Journey</TabsTrigger>
                  <TabsTrigger value="rules" className="data-[state=active]:bg-secondary/40 text-muted-foreground border border-transparent data-[state=active]:border-border rounded-lg px-3 font-mono text-xs uppercase tracking-wider">Rule Evidence</TabsTrigger>
                  <TabsTrigger value="correlations" className="data-[state=active]:bg-secondary/40 text-muted-foreground border border-transparent data-[state=active]:border-border rounded-lg px-3 font-mono text-xs uppercase tracking-wider">Correlations</TabsTrigger>
                </TabsList>
              </div>

              {/* OVERVIEW TAB */}
              <TabsContent value="overview" className="p-6 space-y-8 mt-0 focus-visible:outline-none">
                
                {/* 1. Primary Transaction Information */}
                {dossier.kind === "transaction" && (
                  <Section title="Primary Transaction Information" icon={ActivitySquare}>
                    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
                      <Kpi label="Transaction ID" value={dossier.value} accent="text-sky-400" />
                      <Kpi label="Timestamp" value={dossier.primary?.timestamp} />
                      <Kpi label="Amount" value={fmtMoney(dossier.primary?.amount)} accent="text-rose-400" />
                      <Kpi label="Type" value={dossier.primary?.type || "Transfer"} />
                      <Kpi label="Channel" value={dossier.primary?.channel || "UPI/IMPS"} />
                      <Kpi label="Bank Name" value={dossier.primary?.bank || "Unknown"} />
                      <Kpi label="Status" value={dossier.primary?.status || "COMPLETED"} accent="text-emerald-400" />
                      <Kpi label="Reference Number" value={dossier.primary?.reference || "N/A"} />
                      <Kpi label="Risk Score" value={dossier.primary?.risk_score} accent="text-amber-400" />
                      <Kpi label="Risk Band" value={dossier.primary?.risk_band} />
                      <Kpi label="Fraud Prob" value={dossier.primary?.fraud_probability ? `${Math.round(dossier.primary.fraud_probability)}%` : "N/A"} />
                      <Kpi label="Model Conf" value={dossier.primary?.confidence ? `${Math.round(dossier.primary.confidence * 100)}%` : "N/A"} />
                    </div>
                  </Section>
                )}

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
                  <div className="space-y-8">
                    {/* 6. AI Investigation Summary */}
                    {dossier.ai?.investigation_summary && dossier.ai.investigation_summary.length > 0 && (
                      <Section title="Point-wise AI Investigation Summary" icon={BrainCircuit}>
                        <div className="bg-emerald-500/5 border border-emerald-500/20 rounded-xl p-4 space-y-3">
                          {dossier.ai.investigation_summary.map((point, i) => {
                            const cleanPoint = point.replace(/^\d+[\.\)]\s*/, '');
                            return (
                              <div key={i} className="flex items-start gap-3.5 bg-card/70 border border-border/70 rounded-xl p-4 shadow-sm hover:border-emerald-500/40 transition-colors">
                                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shrink-0 mt-1.5 shadow-[0_0_8px_rgba(52,211,153,0.6)]" />
                                <p className="text-sm text-slate-100 leading-relaxed flex-1 font-sans">{cleanPoint}</p>
                              </div>
                            );
                          })}
                        </div>
                      </Section>
                    )}

                    {/* 14. Actionable Recommendations */}
                    {dossier.ai?.recommendations && dossier.ai.recommendations.length > 0 && (
                      <Section title="Investigation Recommendations" icon={ShieldAlert}>
                        <div className="space-y-3">
                          {dossier.ai.recommendations.map((rec, i) => {
                            const cleanRec = rec.replace(/^\d+[\.\)]\s*/, '');
                            return (
                              <div key={i} className="flex items-start gap-3.5 bg-card/70 border border-border/70 rounded-xl p-4 shadow-sm hover:border-amber-500/40 transition-colors">
                                <span className="w-2.5 h-2.5 rounded-full bg-amber-400 shrink-0 mt-1.5 shadow-[0_0_8px_rgba(251,191,36,0.6)]" />
                                <p className="text-sm text-slate-100 leading-relaxed flex-1 font-sans">{cleanRec}</p>
                              </div>
                            );
                          })}
                        </div>
                      </Section>
                    )}
                  </div>

                  <div className="space-y-8">
                    {/* 4. Money Flow Summary */}
                    {dossier.ai?.money_flow_summary && (
                      <Section title="Money Flow Summary" icon={Network}>
                        <div className="bg-secondary/20 border border-border rounded-xl p-5 text-sm text-foreground/80 leading-relaxed font-mono">
                          <ReactMarkdown components={markdownComponents}>{dossier.ai.money_flow_summary}</ReactMarkdown>
                        </div>
                        {dossier.ai.flow_stats && (
                          <div className="grid grid-cols-3 gap-2 mt-3">
                            <Kpi label="Total Flow Value" value={fmtMoney(dossier.ai.flow_stats.total_value)} />
                            <Kpi label="Number of Hops" value={dossier.ai.flow_stats.hops} />
                            <Kpi label="Banks Involved" value={dossier.ai.flow_stats.banks} />
                            <Kpi label="Beneficiaries" value={dossier.ai.flow_stats.accounts} />
                            <Kpi label="Circular Txns" value={dossier.ai.flow_stats.circular} />
                            <Kpi label="Layering/Structuring" value={dossier.ai.flow_stats.layering || dossier.ai.flow_stats.structuring} />
                          </div>
                        )}
                      </Section>
                    )}
                  </div>
                </div>
              </TabsContent>

              {/* IDENTITIES TAB */}
              <TabsContent value="identities" className="p-6 space-y-8 mt-0 focus-visible:outline-none">
                
                {/* 2. Complete Sender Profile */}
                {dossier.sender && (
                  <Section title="Complete Sender Profile" icon={User}>
                    <div className="bg-card border border-border rounded-xl p-5 grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-y-4 gap-x-4">
                      <Kpi label="Customer Name" value={dossier.sender.name || "Unknown"} />
                      <Kpi label="Customer ID" value={dossier.sender.customer_id || "N/A"} />
                      <div>
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Account Number</p>
                        <p className="font-mono text-sm font-semibold text-emerald-500 cursor-pointer hover:underline" onClick={() => onEntitySelect("account", dossier.sender.account_no!)}>{dossier.sender.account_no || "—"}</p>
                      </div>
                      <Kpi label="Bank" value={dossier.sender.bank || "N/A"} />
                      <Kpi label="IFSC / Branch" value={dossier.sender.ifsc || "N/A"} />
                      <div>
                        <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Registered Phone</p>
                        <p className="font-mono text-sm font-semibold text-emerald-500 cursor-pointer hover:underline" onClick={() => onEntitySelect("phone", dossier.sender.phone!)}>{dossier.sender.phone || "—"}</p>
                      </div>
                      <Kpi label="Email" value={dossier.sender.email || "N/A"} />
                      <Kpi label="UPI IDs" value={dossier.sender.upi || "N/A"} />
                      <Kpi label="KYC Status" value={dossier.sender.kyc_status || "Unknown"} />
                      <Kpi label="Current Balance" value={fmtMoney(dossier.sender.balance)} />
                      <Kpi label="Customer Risk" value={dossier.sender.risk_category || "Standard"} />
                      <Kpi label="Previous STRs" value={dossier.sender.str_count || 0} />
                      
                      {dossier.sender.linked_devices && dossier.sender.linked_devices.length > 0 && (
                        <div className="col-span-2 md:col-span-3">
                          <p className="text-[10px] uppercase text-muted-foreground mb-1">Linked Devices (IMEI)</p>
                          <div className="flex flex-wrap gap-2">
                            {dossier.sender.linked_devices.map(d => (
                              <Badge key={d} variant="outline" className="font-mono text-xs cursor-pointer hover:border-emerald-500 hover:text-emerald-500" onClick={() => onEntitySelect("device", d)}>{d}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                      {dossier.sender.linked_ips && dossier.sender.linked_ips.length > 0 && (
                        <div className="col-span-2 md:col-span-2">
                          <p className="text-[10px] uppercase text-muted-foreground mb-1">Linked IP Addresses</p>
                          <div className="flex flex-wrap gap-2">
                            {dossier.sender.linked_ips.map(ip => (
                              <Badge key={ip} variant="outline" className="font-mono text-xs cursor-pointer hover:border-emerald-500 hover:text-emerald-500" onClick={() => onEntitySelect("ip", ip)}>{ip}</Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </Section>
                )}

                {/* 3. Complete Receiver Intelligence */}
                {dossier.receivers && dossier.receivers.length > 0 && (
                  <Section title={`Complete Receiver Intelligence (${dossier.receivers.length} Connections)`} icon={LinkIcon}>
                    <div className="space-y-4">
                      {dossier.receivers.map((r, i) => (
                        <div key={i} className="bg-card border border-border rounded-xl p-5">
                          <div className="flex flex-wrap items-center justify-between mb-4 pb-4 border-b border-border/50 gap-4">
                            <h5 className="font-bold text-lg">{r.name || "Unknown Beneficiary"}</h5>
                            <div className="flex items-center gap-3">
                               <span className="text-xs text-muted-foreground font-mono">Total Rcv: <span className="text-emerald-400 font-bold">{fmtMoney(r.total_received)}</span></span>
                               {r.risk_score !== undefined && (
                                 <Badge variant="outline" className="text-xs border-amber-500/30 text-amber-500">Risk: {r.risk_score}</Badge>
                               )}
                            </div>
                          </div>
                          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-4">
                            <div>
                              <p className="text-[10px] uppercase text-muted-foreground">Account</p>
                              <p className="text-sm font-mono text-emerald-500 cursor-pointer hover:underline" onClick={() => onEntitySelect("account", r.account_no!)}>{r.account_no}</p>
                            </div>
                            <div>
                              <p className="text-[10px] uppercase text-muted-foreground">Bank / Branch</p>
                              <p className="text-sm font-mono">{r.bank || "—"}</p>
                            </div>
                            <div>
                              <p className="text-[10px] uppercase text-muted-foreground">Phone</p>
                              <p className="text-sm font-mono text-emerald-500 cursor-pointer hover:underline" onClick={() => onEntitySelect("phone", r.phone!)}>{r.phone || "—"}</p>
                            </div>
                            <div>
                              <p className="text-[10px] uppercase text-muted-foreground">UPI / Email</p>
                              <p className="text-sm font-mono truncate" title={r.upi}>{r.upi || "—"}</p>
                            </div>
                            <div>
                               <p className="text-[10px] uppercase text-muted-foreground">Timeline</p>
                               <p className="text-xs font-mono text-muted-foreground">Seen: {r.first_seen || "N/A"}</p>
                            </div>
                            {/* Shared Flags */}
                            <div>
                               <p className="text-[10px] uppercase text-muted-foreground">Shared Assets</p>
                               <div className="flex flex-wrap gap-1 mt-1">
                                 {r.shared_device && <Badge variant="destructive" className="text-[9px]">DEVICE</Badge>}
                                 {r.shared_ip && <Badge variant="destructive" className="text-[9px]">IP</Badge>}
                                 {r.shared_phone && <Badge variant="destructive" className="text-[9px]">PHONE</Badge>}
                                 {!r.shared_device && !r.shared_ip && !r.shared_phone && <span className="text-xs text-muted-foreground">—</span>}
                               </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </Section>
                )}
              </TabsContent>

              {/* HISTORY & NET TAB */}
              <TabsContent value="history" className="p-6 mt-0 focus-visible:outline-none space-y-8">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* 11. Network Intelligence */}
                  <Section title="Network Intelligence" icon={Network}>
                    <div className="grid grid-cols-2 gap-3">
                      <Kpi label="Node Degree" value={dossier.network?.degree || 0} />
                      <Kpi label="Community ID" value={dossier.network?.community || "Unknown"} />
                      <Kpi label="Centrality Score" value={dossier.network?.centrality?.toFixed(4) || "0.00"} />
                      <Kpi label="Bridge Score" value={dossier.network?.bridge_score?.toFixed(4) || "0.00"} />
                      <Kpi label="Connected Accounts" value={dossier.network?.connected_accounts || 0} />
                      <Kpi label="Neighbour Count" value={dossier.network?.degree || 0} />
                    </div>
                  </Section>

                  {/* 12. Historical Behaviour */}
                  <Section title="Historical Behaviour" icon={History}>
                    <div className="grid grid-cols-2 gap-3">
                      <Kpi label="Avg Daily Txns" value={dossier.history?.avg_daily_txns || 0} />
                      <Kpi label="Avg Amount" value={fmtMoney(dossier.history?.avg_amount)} />
                      <Kpi label="Max Amount" value={fmtMoney(dossier.history?.max_amount)} />
                      <Kpi label="Normal Active Hours" value={dossier.history?.normal_hours || "09:00 - 18:00"} />
                    </div>
                    {dossier.history?.frequent_beneficiaries && dossier.history.frequent_beneficiaries.length > 0 && (
                      <div className="mt-4 p-4 rounded-xl border border-border bg-card">
                        <p className="text-[10px] uppercase text-muted-foreground mb-2">Most Frequent Beneficiaries</p>
                        <div className="flex flex-wrap gap-2">
                          {dossier.history.frequent_beneficiaries.map(fb => (
                             <Badge key={fb} variant="secondary" className="font-mono text-xs cursor-pointer hover:border-emerald-500 hover:text-emerald-500" onClick={() => onEntitySelect("account", fb)}>{fb}</Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </Section>
                </div>

                {/* 9. Relationship Matrix Placeholder */}
                <Section title="Intelligence Relationship Matrix" icon={Network}>
                  <div className="p-8 border border-border bg-secondary/10 rounded-xl text-center">
                    <Network className="w-12 h-12 text-muted-foreground/30 mx-auto mb-3" />
                    <p className="text-muted-foreground text-sm font-mono">
                      Sender → Receiver → Receiver's Devices → Shared Accounts → Known Associates
                    </p>
                    <Button variant="outline" size="sm" className="mt-4 gap-2">
                      <ExternalLink className="w-4 h-4" /> Open Full Network Graph
                    </Button>
                  </div>
                </Section>
              </TabsContent>

              {/* JOURNEY TAB */}
              <TabsContent value="journey" className="p-6 mt-0 focus-visible:outline-none">
                {/* 5. Complete Transaction Journey */}
                <Section title="Complete Chronological Journey" icon={Clock}>
                  {dossier.journey && dossier.journey.length > 0 ? (
                    <div className="relative border-l-2 border-border/50 ml-4 pl-6 space-y-8 py-2">
                      {dossier.journey.map((step, i) => (
                        <div key={i} className="relative">
                          <div className="absolute w-3 h-3 bg-emerald-500/20 border-2 border-emerald-500 rounded-full -left-[1.95rem] top-1.5" />
                          <p className="text-xs font-mono text-muted-foreground mb-1">{step.timestamp}</p>
                          <p className="text-sm">{step.event}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground py-10 text-center">No timeline events found for this entity.</p>
                  )}
                </Section>
              </TabsContent>

              {/* RULES TAB */}
              <TabsContent value="rules" className="p-6 mt-0 focus-visible:outline-none space-y-6">
                
                <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-emerald-500 via-yellow-500 to-red-500"
                    style={{ width: `${dossier.primary?.risk_score || 0}%` }}
                  />
                </div>
                
                {/* 7. Detailed Rule Explanation */}
                <Section title="Detailed Risk Rule Breakdown" icon={AlertTriangle}>
                  {dossier.rules && dossier.rules.length > 0 ? (
                    <div className="space-y-3 grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {dossier.rules.map((rule, i) => (
                        <div key={i} className="bg-card border border-border rounded-xl p-4 flex gap-4 items-start">
                          <div className="mt-0.5 flex-none rounded bg-red-500/15 px-2 py-1 font-mono text-sm font-bold text-red-400">
                            +{rule.points}
                          </div>
                          <div>
                            <h5 className="font-mono text-sm font-bold text-foreground uppercase tracking-wider">{rule.rule}</h5>
                            <p className="text-xs text-muted-foreground mt-1 uppercase">Meaning</p>
                            <p className="text-sm text-foreground mt-0.5">{rule.meaning}</p>
                            {rule.evidence && (
                              <div className="mt-3 bg-secondary/30 border border-border/50 rounded-lg p-3">
                                <p className="text-xs text-muted-foreground uppercase mb-1">Evidence</p>
                                <p className="text-xs font-mono text-foreground/80 break-words">{rule.evidence}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground py-10 text-center">No risk rules fired. Activity appears normal.</p>
                  )}
                </Section>
              </TabsContent>

              {/* CORRELATIONS TAB */}
              <TabsContent value="correlations" className="p-6 mt-0 focus-visible:outline-none space-y-8">
                
                {/* 13. Cross-Dataset Correlation */}
                <Section title="Cross-Dataset Correlation Engine" icon={Crosshair}>
                  {dossier.correlations && dossier.correlations.length > 0 ? (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                      {dossier.correlations.map((corr, i) => (
                        <div key={i} className="bg-secondary/20 border border-border rounded-xl p-4">
                          <Badge variant="outline" className="mb-2 uppercase text-[10px] tracking-widest">{corr.dataset}</Badge>
                          <p className="text-sm font-medium">{corr.evidence}</p>
                          <div className="flex justify-between items-center mt-4 text-xs">
                            <span className="text-emerald-500 font-mono">Conf: {Math.round(corr.confidence * 100)}%</span>
                            <span className="text-rose-400 font-mono">Impact: {corr.impact}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-muted-foreground py-4 text-center">No cross-dataset correlations identified.</p>
                  )}
                </Section>

                {/* 8. Connected Entities */}
                {dossier.connections && Object.keys(dossier.connections).length > 0 && (
                  <Section title="Connected Entities (Direct Links)" icon={Network}>
                    <div className="space-y-4">
                      {Object.entries(dossier.connections).map(([cat, items]) =>
                        items.length > 0 ? (
                          <div key={cat} className="flex flex-wrap items-center gap-2">
                            <span className="w-32 shrink-0 text-xs text-muted-foreground uppercase">{cat}</span>
                            {items.slice(0, 15).map((v) => (
                              <button
                                key={v}
                                onClick={() => {
                                  const kind =
                                    cat === "phones" || cat === "contacts" ? "phone"
                                    : cat === "accounts" || cat === "receiver_accounts" ? "account"
                                    : cat === "imeis" ? "imei"
                                    : cat === "ips" ? "ip"
                                    : cat === "upi_ids" ? "upi" : "name";
                                  onEntitySelect(kind, v);
                                }}
                                className="rounded-md border border-border bg-secondary/40 px-2.5 py-1 font-mono text-[11px] text-foreground transition-colors hover:border-emerald-500/40 hover:text-emerald-500"
                              >
                                {v}
                              </button>
                            ))}
                          </div>
                        ) : null
                      )}
                    </div>
                  </Section>
                )}

              </TabsContent>
            </Tabs>
          )}

          {/* Fallback for Relationship Intelligence */}
          {rel && (
            <div className="p-6 space-y-6">
              {/* Keep the existing rel UI rendering */}
              <Section title="Communication Evidence" icon={PhoneCall}>
                {rel.calls ? (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    <Kpi label="Calls" value={rel.calls.count} />
                    <Kpi label="Total duration" value={`${rel.calls.total_seconds}s`} />
                    <Kpi label="Avg duration" value={`${rel.calls.avg_seconds}s`} />
                    <Kpi label="Longest" value={`${rel.calls.max_seconds}s`} />
                  </div>
                ) : <p className="text-sm text-muted-foreground">No calls found.</p>}
              </Section>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
