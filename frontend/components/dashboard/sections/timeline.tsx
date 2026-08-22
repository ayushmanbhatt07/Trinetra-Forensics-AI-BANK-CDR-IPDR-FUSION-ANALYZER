"use client";

import React, { useEffect, useState, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { Clock, Banknote, PhoneCall, Globe, ShieldAlert, Search, X, Loader2, type LucideIcon } from "lucide-react";
import { api, type TimelineEvent } from "@/lib/api";
import { toast } from "sonner";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

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
  const [searchQuery, setSearchQuery] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .timeline(5000)
      .then((res) => setEvents(res?.events || []))
      .catch((e) => {
        if (e?.status !== 409) toast.error("Failed to load timeline.");
        setEvents([]);
      })
      .finally(() => setLoading(false));
  }, [isFusedReady]);

  const shown = React.useMemo(() => {
    let list = events;
    if (filter) {
      list = list.filter((e) => e.kind === filter);
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter((e) => 
        (e.entity || "").toLowerCase().includes(q) ||
        (e.detail || "").toLowerCase().includes(q) ||
        (e.label || "").toLowerCase().includes(q) ||
        (e.date || "").toLowerCase().includes(q)
      );
    }
    return list;
  }, [events, filter, searchQuery]);

  const countsByKind = React.useMemo(() => {
    const counts: Record<string, number> = { bank: 0, cdr: 0, ipdr: 0, complaint: 0 };
    events.forEach((e) => {
      if (counts[e.kind] !== undefined) counts[e.kind]++;
    });
    return counts;
  }, [events]);

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
      <Card className="border-border/70 bg-card/60 backdrop-blur shadow-xl">
        <CardHeader className="flex flex-col gap-4 border-b border-border/60 pb-4">
          <div className="flex flex-row items-center gap-2 flex-wrap justify-between">
            <div className="flex items-center gap-2">
              <Clock className="h-5 w-5 text-emerald-500" />
              <div>
                <CardTitle className="text-lg font-bold">Unified Event Timeline</CardTitle>
                <CardDescription className="text-xs">
                  {loading ? "Loading events..." : `${shown.length.toLocaleString()} of ${events.length.toLocaleString()} fused temporal events`}
                </CardDescription>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {[null, "bank", "cdr", "ipdr", "complaint"].map((k) => {
                const count = k === null ? events.length : countsByKind[k] || 0;
                return (
                  <button
                    key={k || "all"}
                    onClick={() => setFilter(k)}
                    className={`px-3 py-1 rounded-full text-xs border font-mono transition-colors flex items-center gap-1.5 ${
                      filter === k
                        ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-400 font-semibold"
                        : "border-border text-muted-foreground hover:text-foreground hover:bg-secondary/40"
                    }`}
                  >
                    <span>{k === null ? "ALL" : k.toUpperCase()}</span>
                    <span className="text-[10px] opacity-70">({count})</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Fast in-memory search bar */}
          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Filter timeline by Entity ID, Account, Phone, Details, Timestamp..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-8 h-9 text-xs bg-background/80 border-border/80"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery("")}
                  className="absolute right-2.5 top-2.5 text-muted-foreground hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              )}
            </div>
            {(filter !== null || searchQuery) && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => { setFilter(null); setSearchQuery(""); }}
                className="h-9 text-xs text-muted-foreground hover:text-foreground"
              >
                Reset
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <ScrollArea className="h-[calc(100vh-20rem)]">
            {loading ? (
              <div className="p-12 text-center text-muted-foreground">
                <Loader2 className="mx-auto mb-3 size-7 animate-spin text-emerald-500" />
                <p className="text-sm animate-pulse font-mono">Synchronizing unified forensic timeline...</p>
              </div>
            ) : events.length === 0 ? (
              <div className="p-12 text-center text-muted-foreground space-y-2">
                <Clock className="mx-auto size-8 opacity-30 text-emerald-500" />
                <p className="text-sm font-medium">No events found in dataset.</p>
                <p className="text-xs text-muted-foreground/60">Upload and fuse bank, CDR, or IPDR files to view unified chronological events.</p>
              </div>
            ) : shown.length === 0 ? (
              <div className="p-12 text-center text-muted-foreground space-y-3">
                <Search className="mx-auto size-8 opacity-30 text-amber-500" />
                <p className="text-sm font-medium text-foreground">No events match your active filters</p>
                <p className="text-xs text-muted-foreground/80 max-w-sm mx-auto">
                  {searchQuery ? `No records found containing "${searchQuery}"` : `No records found in category ${filter?.toUpperCase()}`}
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => { setFilter(null); setSearchQuery(""); }}
                  className="text-xs"
                >
                  Clear All Filters
                </Button>
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
