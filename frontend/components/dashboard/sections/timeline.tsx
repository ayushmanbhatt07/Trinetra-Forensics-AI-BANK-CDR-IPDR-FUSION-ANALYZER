"use client";

import React, { useEffect, useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Clock, Banknote, PhoneCall, Globe, ShieldAlert, type LucideIcon } from "lucide-react";
import { api, type TimelineEvent } from "@/lib/api";
import { toast } from "sonner";

const KIND_STYLE: Record<string, { label: string; cls: string; icon: LucideIcon }> = {
  bank: { label: "BANK", cls: "bg-emerald-500/10 text-emerald-500 border-emerald-500/30", icon: Banknote },
  cdr: { label: "CDR", cls: "bg-blue-500/10 text-blue-500 border-blue-500/30", icon: PhoneCall },
  ipdr: { label: "IPDR", cls: "bg-purple-500/10 text-purple-500 border-purple-500/30", icon: Globe },
  complaint: { label: "NCRP", cls: "bg-red-500/10 text-red-500 border-red-500/30", icon: ShieldAlert },
};

import { HoverCard, HoverCardTrigger, HoverCardContent } from "@/components/ui/hover-card";
import { InvestigationPanel } from "@/components/dashboard/investigation-panel";
import { EventDossierPanel } from "@/components/dashboard/event-dossier";
import { usePipeline } from "@/lib/pipeline-context";

export const TimelineSection = React.memo(function TimelineSection() {
  const { isFusedReady } = usePipeline();
  const [events, setEvents] = useState<TimelineEvent[]>([]);
  const [filter, setFilter] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .timeline(5000)
      .then((res) => setEvents(res.events))
      .catch((e) => {
        if (e.status !== 409) toast.error("Failed to load timeline.");
      })
      .finally(() => setLoading(false));
  }, [isFusedReady]);

  const shown = filter ? events.filter((e) => e.kind === filter) : events;

  const [panelPayload, setPanelPayload] = useState<any>(null);
  const dossierCacheRef = useRef<Map<string, any>>(new Map());

  const handleEventClick = async (e: TimelineEvent) => {
    const key = `${e.kind}:${e.record_id || e.entity}`;
    const cached = dossierCacheRef.current.get(key);
    if (cached) {
      setPanelPayload({ type: "event", info: cached });
      return;
    }

    let toastId: string | number | undefined;
    try {
      toastId = toast.loading(`Analyzing event ${e.record_id || e.entity}...`);
      const info = await api.eventDossier(e.kind, e.record_id || e.entity);
      dossierCacheRef.current.set(key, info);
      toast.dismiss(toastId);
      setPanelPayload({ type: "event", info });
    } catch (err) {
      if (toastId) toast.dismiss(toastId);
      toast.error(`Could not generate dossier for event ${e.record_id || e.entity}`);
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center gap-2 flex-wrap">
          <Clock className="h-5 w-5 text-emerald-500" />
          <CardTitle>Unified Event Timeline</CardTitle>
          <CardDescription>
            {loading ? "…" : `${events.length.toLocaleString()} fused events`}
          </CardDescription>
          <div className="ml-auto flex gap-2">
            {[null, "bank", "cdr", "ipdr", "complaint"].map((k) => (
              <button
                key={k || "all"}
                onClick={() => setFilter(k)}
                className={`px-3 py-1 rounded-full text-xs border transition-colors ${
                  filter === k
                    ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-500"
                    : "border-border text-muted-foreground hover:text-foreground"
                }`}
              >
                {k === null ? "ALL" : k.toUpperCase()}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[calc(100vh-20rem)]">
            {loading ? (
              <div className="p-8 text-center text-muted-foreground animate-pulse">Loading timeline...</div>
            ) : shown.length === 0 ? (
              <div className="p-8 text-center text-muted-foreground">
                No events. Run the ingestion pipeline first.
              </div>
            ) : (
              <div className="relative">
                <div className="absolute left-[19px] top-0 bottom-0 w-px bg-border" />
                {shown.map((e, i) => {
                  const style = KIND_STYLE[e.kind] || KIND_STYLE.bank;
                  const Icon = style.icon;
                  return (
                    <HoverCard key={i}>
                      <HoverCardTrigger asChild>
                        <div 
                           onClick={() => handleEventClick(e)}
                           className="relative flex gap-4 px-5 py-3 cursor-pointer hover:bg-secondary/40 transition-colors"
                        >
                          <div className={`w-10 h-10 rounded-lg border flex items-center justify-center z-10 ${style.cls}`}>
                            <Icon className="w-4 h-4" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-mono text-xs text-foreground">{e.date}</span>
                              <Badge variant="outline" className={style.cls}>
                                {style.label}
                              </Badge>
                              <span className="font-mono text-xs text-muted-foreground">{e.entity}</span>
                            </div>
                            <p className="text-sm text-muted-foreground mt-1 break-words">
                              {e.detail || e.label || "—"}
                            </p>
                            <p className="text-[10px] text-emerald-500/70 mt-1 uppercase font-semibold">Click for in-depth AI research</p>
                          </div>
                        </div>
                      </HoverCardTrigger>
                      <HoverCardContent side="bottom" align="start" className="w-[320px] p-4 bg-slate-900 border-slate-700 shadow-2xl z-[100] rounded-xl">
                        <div className="flex items-center gap-3 mb-3 pb-3 border-b border-slate-700/50">
                          <div className={`w-8 h-8 rounded border flex flex-shrink-0 items-center justify-center ${style.cls}`}>
                            <Icon className="w-4 h-4" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <h4 className="font-bold text-sm text-slate-100 font-mono truncate">{e.entity}</h4>
                            <p className="text-[10px] text-slate-400 uppercase tracking-widest">{style.label} EVENT</p>
                          </div>
                        </div>
                        <div className="space-y-3">
                          {e.date && (
                            <div>
                              <p className="text-[10px] uppercase text-slate-500 mb-0.5">Timestamp</p>
                              <p className="text-xs text-slate-200 font-mono">{e.date}</p>
                            </div>
                          )}
                          {e.label && (
                            <div>
                              <p className="text-[10px] uppercase text-slate-500 mb-0.5">Primary Label</p>
                              <p className="text-xs text-slate-200 font-medium break-words">{e.label}</p>
                            </div>
                          )}
                          {e.detail && (
                            <div className="bg-slate-800/60 p-2 rounded-lg border border-slate-700/50">
                              <p className="text-[10px] uppercase text-slate-500 mb-1">Extended Details</p>
                              <p className="text-xs text-slate-300 break-words leading-relaxed">{e.detail}</p>
                            </div>
                          )}
                        </div>
                      </HoverCardContent>
                    </HoverCard>
                  );
                })}
              </div>
            )}
          </ScrollArea>
        </CardContent>
      </Card>
      {panelPayload && panelPayload.type === "entity" && (
        <InvestigationPanel 
          data={panelPayload} 
          onClose={() => setPanelPayload(null)} 
          onEntitySelect={async (k, v) => {
            try {
              setPanelPayload(null);
              const info = await api.dossier(k, v);
              setPanelPayload({ type: "entity", info });
            } catch (err) {
              toast.error("Could not load entity intelligence for " + v);
            }
          }} 
        />
      )}
      {panelPayload && panelPayload.type === "event" && (
        <EventDossierPanel 
          dossier={panelPayload.info} 
          onClose={() => setPanelPayload(null)} 
          onEntitySelect={async (k, v) => {
            try {
              setPanelPayload(null);
              const info = await api.dossier(k, v);
              setPanelPayload({ type: "entity", info });
            } catch (err) {
              toast.error("Could not load entity intelligence for " + v);
            }
          }} 
        />
      )}
    </div>
  );
});
