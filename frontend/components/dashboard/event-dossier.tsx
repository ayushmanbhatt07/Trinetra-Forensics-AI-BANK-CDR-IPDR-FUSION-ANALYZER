"use client";

import React, { useState, useRef } from "react";
import {
  Dialog,
  DialogContent,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Activity, Landmark, Phone, Globe, ShieldAlert,
  FileDown, Code, ArrowUpDown, Clock, Network, AlertTriangle, FileText, X
} from "lucide-react";
import { type EventDossier } from "@/lib/api";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";

const BAND_CLASS: Record<string, string> = {
  CRITICAL: "bg-red-500/15 text-red-400 border-red-500/30",
  HIGH: "bg-orange-500/15 text-orange-400 border-orange-500/30",
  MEDIUM: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  LOW: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
  SAFE: "bg-emerald-500/15 text-emerald-500 border-emerald-500/30",
};

const SOURCE_ICON: Record<string, React.ElementType> = {
  BANK: Landmark,
  CDR: Phone,
  IPDR: Globe,
  COMPLAINT: FileText,
};

function Kpi({ label, value, accent = "text-foreground" }: { label: string; value: React.ReactNode; accent?: string }) {
  if (value === undefined || value === null || value === "" || value === "NaN") return null;
  return (
    <div className="flex flex-col gap-1 p-3 bg-secondary/20 rounded-lg border border-border/50 min-w-0">
      <span className="text-[10px] uppercase font-semibold text-muted-foreground tracking-widest truncate">{label}</span>
      <span className={`font-mono font-medium break-all ${accent}`}>{value}</span>
    </div>
  );
}

function Section({ title, children, icon: Icon }: { title: string; children: React.ReactNode; icon?: React.ElementType }) {
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

export function EventDossierPanel({
  dossier,
  onClose,
  onEntitySelect,
}: {
  dossier: EventDossier;
  onClose: () => void;
  onEntitySelect: (kind: string, value: string) => void;
}) {
  const [downloading, setDownloading] = useState(false);

  const reportRef = useRef<HTMLDivElement>(null);

  const download = async () => {
    if (!reportRef.current) return;
    setDownloading(true);
    try {
      toast.info("Generating PDF, please wait...");
      const htmlToImage = await import("html-to-image");
      const { jsPDF } = await import("jspdf");
      
      const dataUrl = await htmlToImage.toPng(reportRef.current, { 
        quality: 0.98,
        pixelRatio: 2,
        backgroundColor: '#ffffff',
        skipFonts: true,
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
      
      pdf.save(`Event_Dossier_${dossier.event_id}.pdf`);
      toast.success("PDF generated successfully");
    } catch (e) {
      console.error("PDF generation failed:", e);
      toast.error("Failed to generate PDF");
    } finally {
      setDownloading(false);
    }
  };

  const downloadJson = () => {
    const dataStr = JSON.stringify(dossier, null, 2);
    const blob = new Blob([dataStr], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `EventDossier_${dossier.event_id}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast.success("JSON downloaded");
  };

  const Icon = SOURCE_ICON[dossier.source_type] || Activity;
  const title = `${dossier.source_type} EVENT — ${dossier.event_id}`;
  const isPending = !dossier.risk?.score && dossier.risk?.score !== 0;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent 
        showCloseButton={false}
        onInteractOutside={() => onClose()}
        className="max-w-[95vw] w-[1200px] max-h-[95vh] overflow-hidden flex flex-col p-0 gap-0 bg-background border border-border/60 shadow-2xl"
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
                <div className="mt-2 flex flex-wrap items-center gap-3">
                  {isPending ? (
                     <Badge className="px-3 py-1 uppercase font-bold tracking-widest bg-slate-500/15 text-slate-400 border-slate-500/30">
                       ANALYSIS PENDING
                     </Badge>
                  ) : (
                    <>
                      <Badge className={`px-3 py-1 uppercase font-bold tracking-widest ${BAND_CLASS[dossier.risk?.band || "SAFE"] ?? BAND_CLASS.LOW}`}>
                        {dossier.risk?.band || "SAFE"} RISK
                      </Badge>
                      <div className="flex items-baseline gap-1 bg-secondary/40 px-3 py-1 rounded-full border border-border">
                        <span className="font-mono text-sm font-bold text-foreground">
                          {dossier.risk?.score}
                        </span>
                        <span className="text-xs text-muted-foreground uppercase tracking-widest">Score</span>
                      </div>
                    </>
                  )}
                  {dossier.timestamp && (
                    <div className="flex items-center gap-1.5 text-xs font-mono text-muted-foreground">
                      <Clock className="w-3.5 h-3.5" />
                      {new Date(dossier.timestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            {/* Action Buttons & Close */}
            <div className="flex items-center gap-2">
              <Button onClick={download} variant="outline" size="sm" className="h-8 gap-1.5 bg-secondary/30 text-xs">
                <FileDown className="h-3.5 w-3.5" /> PDF
              </Button>
              <Button onClick={downloadJson} variant="outline" size="sm" className="h-8 gap-1.5 bg-secondary/30 text-xs">
                <Code className="h-3.5 w-3.5" /> JSON
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

        {/* Content */}
        <div className="flex-1 overflow-hidden">
          <Tabs defaultValue="overview" className="w-full h-full flex flex-col">
            <div className="px-6 border-b border-border bg-muted/10">
              <TabsList className="h-12 bg-transparent gap-6 p-0">
                <TabsTrigger value="overview" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-emerald-500 rounded-none px-0 h-12 uppercase tracking-wider text-xs font-semibold">Overview</TabsTrigger>
                <TabsTrigger value="raw" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-emerald-500 rounded-none px-0 h-12 uppercase tracking-wider text-xs font-semibold">Source Data</TabsTrigger>
                <TabsTrigger value="identities" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-emerald-500 rounded-none px-0 h-12 uppercase tracking-wider text-xs font-semibold">Identities</TabsTrigger>
                <TabsTrigger value="correlations" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-emerald-500 rounded-none px-0 h-12 uppercase tracking-wider text-xs font-semibold">Correlations</TabsTrigger>
                <TabsTrigger value="risk" className="data-[state=active]:bg-transparent data-[state=active]:shadow-none data-[state=active]:border-b-2 data-[state=active]:border-emerald-500 rounded-none px-0 h-12 uppercase tracking-wider text-xs font-semibold">Rule Evidence</TabsTrigger>
              </TabsList>
            </div>
            
            <ScrollArea className="flex-1 p-6">
              <TabsContent value="overview" className="m-0 space-y-8">
                <Section title="Event Facts">
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                     {dossier.source_type === "BANK" && (
                       <>
                         <Kpi label="Account" value={dossier.source_record.account_no} accent="text-cyan-400" />
                         <Kpi label="Amount" value={dossier.source_record.amount} accent="text-rose-400" />
                         <Kpi label="Type" value={dossier.source_record.txn_type === "C" ? "CREDIT" : "DEBIT"} />
                         <Kpi label="Balance" value={dossier.source_record.balance} />
                         <Kpi label="Counterparty A/C" value={dossier.source_record.receiver_account} />
                         <Kpi label="Counterparty Name" value={dossier.source_record.receiver_name} />
                         <Kpi label="Mode" value={dossier.source_record.mode} />
                         <Kpi label="Bank" value={dossier.source_record.bank} />
                       </>
                     )}
                     {dossier.source_type === "CDR" && (
                       <>
                         <Kpi label="Caller (A)" value={dossier.source_record.a_number} accent="text-cyan-400" />
                         <Kpi label="Receiver (B)" value={dossier.source_record.b_number} accent="text-rose-400" />
                         <Kpi label="Duration" value={`${dossier.source_record.duration} sec`} />
                         <Kpi label="Type" value={dossier.source_record.call_type} />
                         <Kpi label="Cell Tower" value={dossier.source_record.cell_id} />
                         <Kpi label="IMSI" value={dossier.source_record.imsi} />
                         <Kpi label="IMEI" value={dossier.source_record.imei} />
                       </>
                     )}
                     {dossier.source_type === "IPDR" && (
                       <>
                         <Kpi label="Source IP" value={dossier.source_record.source_ip} accent="text-cyan-400" />
                         <Kpi label="Dest IP" value={dossier.source_record.dest_ip} accent="text-rose-400" />
                         <Kpi label="Source Port" value={dossier.source_record.source_port} />
                         <Kpi label="Dest Port" value={dossier.source_record.dest_port} />
                         <Kpi label="Bytes Up" value={dossier.source_record.upload_bytes} />
                         <Kpi label="Bytes Down" value={dossier.source_record.download_bytes} />
                         <Kpi label="Protocol" value={dossier.source_record.protocol} />
                         <Kpi label="Subscriber" value={dossier.source_record.subscriber_id} />
                       </>
                     )}
                     {dossier.source_type === "COMPLAINT" && (
                       <>
                         <Kpi label="Complainant" value={dossier.source_record.complainant} />
                         <Kpi label="Account" value={dossier.source_record.account_no} accent="text-cyan-400" />
                         <Kpi label="Phone" value={dossier.source_record.phone} accent="text-cyan-400" />
                         <Kpi label="Category" value={dossier.source_record.category} />
                       </>
                     )}
                  </div>
                </Section>
                {dossier.source_type === "BANK" && dossier.source_record.narration && (
                  <Section title="Narration / Context">
                    <div className="bg-secondary/20 p-4 rounded-lg font-mono text-sm border border-border/50">
                      {dossier.source_record.narration}
                    </div>
                  </Section>
                )}
                {dossier.source_type === "COMPLAINT" && dossier.source_record.description && (
                  <Section title="Complaint Description">
                    <div className="bg-secondary/20 p-4 rounded-lg text-sm border border-border/50">
                      {dossier.source_record.description}
                    </div>
                  </Section>
                )}
              </TabsContent>

              <TabsContent value="raw" className="m-0 space-y-4">
                 <div className="grid grid-cols-1 md:grid-cols-2 gap-x-12 gap-y-2 font-mono text-sm bg-secondary/10 p-6 rounded-lg border border-border/50">
                   {Object.entries(dossier.source_record).map(([k, v]) => {
                     if (v === null || v === undefined || v === "") return null;
                     return (
                       <div key={k} className="flex justify-between py-1 border-b border-border/30 last:border-0">
                         <span className="text-muted-foreground">{k}</span>
                         <span className="text-foreground text-right break-all ml-4">{String(v)}</span>
                       </div>
                     )
                   })}
                 </div>
              </TabsContent>

              <TabsContent value="identities" className="m-0 space-y-4">
                 <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                   {dossier.identities.length === 0 && (
                     <div className="text-muted-foreground italic text-sm p-4">No identities linked.</div>
                   )}
                   {dossier.identities.map((id, i) => (
                     <div key={i} className="flex items-center gap-3 p-4 bg-secondary/20 border border-border/50 rounded-lg hover:bg-secondary/40 transition-colors cursor-pointer"
                       onClick={() => {
                         // Default mapping for graph navigation
                         let apiKind = "entity";
                         if (id.type.includes("ACCOUNT")) apiKind = "account";
                         else if (id.type.includes("PHONE")) apiKind = "phone";
                         else if (id.type.includes("IP")) apiKind = "ip";
                         else if (id.type.includes("IMSI") || id.type.includes("IMEI")) apiKind = "device";
                         onEntitySelect(apiKind, id.value);
                       }}
                     >
                        <div className="p-2 bg-emerald-500/10 rounded-md">
                          <Network className="w-4 h-4 text-emerald-500" />
                        </div>
                        <div>
                          <div className="text-[10px] text-muted-foreground font-semibold tracking-wider">{id.type}</div>
                          <div className="font-mono text-sm">{id.value}</div>
                        </div>
                     </div>
                   ))}
                 </div>
              </TabsContent>

              <TabsContent value="correlations" className="m-0 space-y-4">
                 {dossier.correlations.length === 0 ? (
                   <div className="text-muted-foreground italic text-sm p-4">No temporal correlations found within the standard window.</div>
                 ) : (
                   <div className="relative border-l-2 border-border ml-4 space-y-6 pb-4">
                     {dossier.correlations.map((c, i) => (
                       <div key={i} className="relative pl-6">
                          <div className="absolute w-3 h-3 bg-emerald-500 rounded-full -left-[7.5px] top-1.5 shadow-[0_0_10px_rgba(16,185,129,0.5)]" />
                          <div className="bg-secondary/20 border border-border/50 p-4 rounded-lg inline-block min-w-[300px]">
                            <div className="flex justify-between items-center mb-2">
                              <Badge variant="outline" className="text-xs uppercase">{c.type}</Badge>
                              <span className="text-xs text-muted-foreground font-mono">{c.time_diff_sec}s apart</span>
                            </div>
                            <div className="text-sm">{c.description}</div>
                            <div className="text-[10px] text-muted-foreground mt-2 font-mono">ID: {c.id}</div>
                          </div>
                       </div>
                     ))}
                   </div>
                 )}
              </TabsContent>

              <TabsContent value="risk" className="m-0 space-y-4">
                 {isPending ? (
                   <div className="text-muted-foreground italic text-sm p-4">Risk analysis is pending or not applicable.</div>
                 ) : dossier.evidence.length === 0 ? (
                   <div className="text-muted-foreground italic text-sm p-4">No specific risk rules triggered.</div>
                 ) : (
                   <div className="space-y-3">
                     {dossier.evidence.map((ev, i) => (
                       <div key={i} className="flex gap-4 items-start bg-secondary/20 border border-border/50 p-4 rounded-lg">
                          <div className="bg-red-500/20 text-red-400 font-mono font-bold px-3 py-1.5 rounded-md min-w-[60px] text-center border border-red-500/30">
                            +{ev.points}
                          </div>
                          <div>
                            <div className="font-semibold text-sm mb-1">{ev.rule}</div>
                            <div className="text-sm text-muted-foreground leading-relaxed">{ev.reason}</div>
                          </div>
                       </div>
                     ))}
                   </div>
                 )}
              </TabsContent>

            </ScrollArea>
          </Tabs>
        </div>
        
        {/* Hidden Printable Report */}
        <div className="absolute top-0 left-0 w-[800px] opacity-0 pointer-events-none -z-50" ref={reportRef}>
          <div className="border-b-2 border-slate-800 pb-4 mb-6">
            <h1 className="text-2xl font-serif font-bold text-slate-900">Forensic Event Dossier</h1>
            <div className="flex justify-between mt-2 text-sm text-slate-600">
              <span>Event ID: {dossier.event_id}</span>
              <span>Source: {dossier.source_type}</span>
            </div>
            {dossier.timestamp && (
              <div className="text-sm text-slate-600 mt-1">
                Timestamp: {new Date(dossier.timestamp).toLocaleString("en-IN", { timeZone: "Asia/Kolkata" })} IST
              </div>
            )}
            <div className="text-sm text-slate-600 mt-1 font-bold">
               Risk Score: {dossier.risk?.score ?? "N/A"} ({dossier.risk?.band || "SAFE"})
            </div>
          </div>

          {/* Context / Narration */}
          {(dossier.source_record.narration || dossier.source_record.description) && (
            <div className="mb-6">
              <h2 className="text-lg font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">Context / Description</h2>
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-800 font-mono break-words">
                {dossier.source_record.narration || dossier.source_record.description}
              </div>
            </div>
          )}

          {/* Raw Facts */}
          <div className="mb-6">
            <h2 className="text-lg font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">Event Facts</h2>
            <div className="grid grid-cols-2 gap-4">
              {Object.entries(dossier.source_record).map(([k, v]) => {
                if (v === null || v === undefined || v === "") return null;
                return (
                  <div key={k} className="p-3 bg-slate-50 border border-slate-200 rounded-lg break-inside-avoid">
                    <h3 className="text-[10px] font-bold text-slate-500 uppercase mb-1">{k}</h3>
                    <p className="text-sm font-mono text-slate-900 break-all">{String(v)}</p>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Identities */}
          <div className="mb-6">
            <h2 className="text-lg font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">Extracted Identities</h2>
            {dossier.identities.length === 0 ? (
               <p className="text-sm text-slate-500 italic">No identities linked.</p>
            ) : (
               <div className="grid grid-cols-2 gap-4">
                 {dossier.identities.map((id, i) => (
                   <div key={i} className="flex flex-col p-3 bg-slate-50 border border-slate-200 rounded-lg break-inside-avoid">
                     <span className="text-[10px] font-bold text-slate-500 uppercase mb-1">{id.type}</span>
                     <span className="text-sm font-mono text-slate-900">{id.value}</span>
                   </div>
                 ))}
               </div>
            )}
          </div>

          {/* Correlations */}
          <div className="mb-6">
            <h2 className="text-lg font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">Correlations</h2>
            {dossier.correlations.length === 0 ? (
               <p className="text-sm text-slate-500 italic">No correlations found.</p>
            ) : (
               <div className="space-y-4">
                 {dossier.correlations.map((c, i) => (
                   <div key={i} className="p-4 bg-slate-50 border border-slate-200 rounded-lg break-inside-avoid">
                     <div className="flex justify-between items-center mb-2">
                       <span className="text-xs font-bold bg-slate-200 px-2 py-1 rounded uppercase">{c.type}</span>
                       <span className="text-xs text-slate-500 font-mono">{c.time_diff_sec}s apart</span>
                     </div>
                     <p className="text-sm text-slate-800 mb-2">{c.description}</p>
                     <p className="text-[10px] text-slate-500 font-mono">ID: {c.id}</p>
                   </div>
                 ))}
               </div>
            )}
          </div>

          {/* Evidence */}
          <div className="mb-6">
            <h2 className="text-lg font-bold text-slate-800 border-b border-slate-200 pb-2 mb-4">Risk Evidence</h2>
            {dossier.evidence.length === 0 ? (
               <p className="text-sm text-slate-500 italic">No specific risk rules triggered.</p>
            ) : (
               <div className="space-y-3">
                 {dossier.evidence.map((ev, i) => (
                   <div key={i} className="flex gap-4 items-start bg-slate-50 border border-slate-200 p-4 rounded-lg break-inside-avoid">
                     <div className="text-red-600 font-mono font-bold px-3 py-1 bg-red-50 rounded-md border border-red-200 min-w-[60px] text-center">
                       +{ev.points}
                     </div>
                     <div>
                       <h3 className="font-semibold text-sm text-slate-900 mb-1">{ev.rule}</h3>
                       <p className="text-sm text-slate-600 leading-relaxed">{ev.reason}</p>
                     </div>
                   </div>
                 ))}
               </div>
            )}
          </div>
        </div>

      </DialogContent>
    </Dialog>
  );
}
