"use client";

/**
 * Global Tri-Netra Forensics chatbot — anchored bottom-right on EVERY page.
 * Sends queries to the Investigative Co-Pilot API. On search it triggers the
 * full-page globe-to-map transition, then renders the answer with
 * evidence / CoT / graph tabs (all scrollable).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  MessageSquare,
  Send,
  X,
  BrainCircuit,
  Network,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, type CopilotQueryResult } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { OmniEye } from "./omni-eye";
import { EyeSpinner } from "./eye-spinner";
import { InvestigationGraph } from "./investigation-graph";
import { usePathname } from "next/navigation";
import ReactMarkdown from "react-markdown";

interface Msg {
  from: "user" | "omni";
  text: string;
}

const SUGGESTIONS = [
  "Top 5 largest transactions",
  "Accounts with rapid layering",
  "Calls before transactions pattern",
  "Who is the most suspicious entity?",
];

const answerText = (r: CopilotQueryResult) =>
  r.answer ?? r.general_answer ?? r.executive_summary ?? "Query processed.";

const pickEntity = (res: CopilotQueryResult, query: string): string => {
  for (const cand of [
    res.graph_traversal?.root,
    res.graph_traversal?.entity_id,
    res.graph_traversal?.start_node,
    res.linking_tree?.root,
    res.linking_tree?.entity_id,
    res.linking_tree?.start_node,
    res.entity_resolution?.entity_id,
  ]) {
    if (cand && cand !== "none" && cand !== "unknown") return cand;
  }
  const m = query.match(/\bTXN[A-Z0-9]{6,}\b|\b\d{10}\b/i);
  if (m) return m[0];
  const txn = res.records?.[0]?.transaction_id;
  return typeof txn === "string" ? txn : "";
};

export function OmniWidget() {
  const scrollRef = useRef<HTMLDivElement>(null);

  const pathname = usePathname();
  const [isIngested, setIsIngested] = useState(false);
  const { user } = useAuth();

  useEffect(() => {
    let mounted = true;
    let interval: NodeJS.Timeout;
    const checkStatus = () => {
      if (!user) return;
      api.status()
        .then(res => {
          if (mounted) {
            setIsIngested(res.loaded);
            if (res.loaded) {
              import("@/components/dashboard/sections/reports").then(m => m.prefetchReports().catch(()=>{}));
              clearInterval(interval);
            }
          }
        })
        .catch(() => {
          if (mounted) setIsIngested(false);
        });
    };

    checkStatus();
    interval = setInterval(checkStatus, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [user?.username]);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([
    {
      from: "omni",
      text: "Tri-Netra Forensics Co-Pilot online. Ask anything about the loaded bank / CDR / IPDR corpus.",
    },
  ]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [globe, setGlobe] = useState(false);
  const [result, setResult] = useState<CopilotQueryResult | null>(null);
  const [tab, setTab] = useState<"answer" | "evidence" | "cot" | "graph">("answer");
  const [treeOpen, setTreeOpen] = useState(false);
  const [treeEntity, setTreeEntity] = useState("");
  const [treeNonce, setTreeNonce] = useState(0);
  /** Whether a real linking tree exists for the last answer — the LLM-tree
   * option only appears below the answer when this is true. */
  const [treeAvailable, setTreeAvailable] = useState(false);
  const [lastExtractedEntity, setLastExtractedEntity] = useState("");

  const openTree = useCallback((res: CopilotQueryResult, entityOverride?: string) => {
    const entity = entityOverride || lastExtractedEntity || pickEntity(res, "");
    if (!entity) {
      setTreeEntity("");
    } else {
      setTreeEntity(entity);
    }
    setTreeNonce((n) => n + 1);
    setGlobe(true);
  }, [lastExtractedEntity]);



  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, result, tab]);

  const send = useCallback(async (text: string) => {
    const clean = text.trim();
    if (!clean || busy) return;
    setDraft("");
    setBusy(true);
    setResult(null);
    setTreeAvailable(false);
    setTab("answer");
    setMessages((m) => [...m, { from: "user", text: clean }]);
    try {
      const res = await api.copilotQuery(clean);
      setResult(res);
      setMessages((m) => [...m, { from: "omni", text: answerText(res) }]);
      // Verify a linking tree really exists BEFORE offering the LLM-tree option.
      const entity = pickEntity(res, clean);
      setLastExtractedEntity(entity);
      if (entity) {
        try {
          const t = await api.copilotGraphBuild(entity, 3);
          setTreeAvailable(Boolean(t.found && (t.nodes?.length ?? 0) > 0));
        } catch {
          setTreeAvailable(false);
        }
      } else {
        setTreeAvailable(false);
      }
    } catch (e) {
      const msg = (e as { message?: string })?.message ?? "Co-Pilot unavailable — is the backend running?";
      setMessages((m) => [...m, { from: "omni", text: msg }]);
    } finally {
      setBusy(false);
    }
  }, [busy]);

  const records = result?.records ?? [];

  if (pathname === "/" || !user || !isIngested) return null;

  return (
    <>
      {/* 50% backdrop dim + blur while the co-pilot chat is open */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setOpen(false)}
            aria-hidden
            className="fixed inset-0 z-[65] bg-black/50 backdrop-blur-md"
          />
        )}
      </AnimatePresence>

      {/* Chat panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 24, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.97 }}
            transition={{ duration: 0.25 }}
            role="dialog"
            aria-label="Tri-Netra Forensics investigative assistant"
            className="fixed bottom-28 right-5 z-[70] flex h-[calc(100vh-10rem)] w-[calc(100vw-2.5rem)] max-w-lg flex-col overflow-hidden rounded-2xl border border-border/70 bg-card/95 text-card-foreground shadow-2xl shadow-black/50 backdrop-blur-xl sm:right-6"
          >
            {/* header */}
            <header className="flex items-center gap-3 border-b border-border bg-gradient-to-r from-cyan-500/10 via-transparent to-violet-500/10 px-4 py-3">
              <div className="size-11 shrink-0">
                <OmniEye pupil={{ x: 0, y: 0 }} ringPupil={{ x: 0, y: 0 }} className="size-full drop-shadow" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm font-semibold tracking-tight">Tri-Netra Forensics</p>
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="inline-block size-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  investigative co-pilot · online
                </p>
              </div>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close chat"
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <X className="size-4" />
              </button>
            </header>

            {/* messages */}
            <div ref={scrollRef} className="flex-1 space-y-3 overflow-y-auto p-4">
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={cn(
                    "max-w-[88%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                    m.from === "omni"
                      ? "self-start rounded-bl-sm bg-secondary/80 text-secondary-foreground"
                      : "self-end rounded-br-sm bg-primary text-primary-foreground"
                  )}
                >
                  {m.text}
                </div>
              ))}

              {/* result block */}
              {result && (
                <div className="self-start w-full space-y-2">
                  <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                    <BrainCircuit className="size-3.5 text-cyan-500" />
                    {result.mode ?? "sql"} · {result.llm_provider ?? "deterministic"}
                    {result.llm_latency_ms ? ` · ${(result.llm_latency_ms / 1000).toFixed(1)}s` : ""}
                  </div>
                  <div className="flex gap-1">
                    {(["answer", "evidence", "graph"] as const).map((t) => (
                      <button
                        key={t}
                        onClick={() => setTab(t)}
                        className={cn(
                          "rounded-md px-2 py-1 text-[11px] font-mono transition-colors",
                          tab === t
                            ? "bg-cyan-500/15 text-cyan-400"
                            : "text-muted-foreground hover:bg-muted"
                        )}
                      >
                        {t.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  <div className="max-h-96 overflow-auto rounded-xl border border-border/70 bg-background/60 p-4 text-sm leading-relaxed">
                    {tab === "answer" && (
                      <div className="space-y-3 whitespace-pre-wrap text-foreground/90">
                        <div className="space-y-2">
                          <ReactMarkdown
                            components={{
                            ul: ({ node, ...props }) => <ul className="list-disc pl-5 space-y-1" {...props} />,
                            ol: ({ node, ...props }) => <ol className="list-decimal pl-5 space-y-1" {...props} />,
                            p: ({ node, ...props }) => <p className="leading-relaxed" {...props} />
                          }}
                        >
                          {answerText(result)}
                        </ReactMarkdown>
                        </div>
                        {result.intent && (
                          <p className="font-mono text-[11px] text-muted-foreground mt-4">
                            intent: {result.intent}
                          </p>
                        )}
                        {result.explainability && (
                          <div className="mt-2 rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-2.5">
                            <p className="mb-1 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest text-emerald-400">
                              <BrainCircuit className="size-3" />
                              why this is suspicious
                            </p>
                            <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-foreground/85">
                              {result.explainability}
                            </p>
                          </div>
                        )}
                      </div>
                    )}
                    {tab === "evidence" && (
                      <div className="max-h-64 space-y-1 overflow-auto">
                        {records.length === 0 ? (
                          <p className="text-muted-foreground">No evidence records for this query.</p>
                        ) : (
                          records.map((r, i) => (
                            <div key={i} className="rounded bg-muted/40 p-1.5 font-mono text-[10px]">
                              {r.transaction_id ?? r.id} · ₹{Number(r.amount ?? r.transaction_amount ?? 0).toLocaleString("en-IN")} · {r.receiver_account ?? r.receiver ?? ""}
                            </div>
                          ))
                        )}
                      </div>
                    )}
                    {tab === "graph" && (
                      <div className="space-y-4">
                        <p className="text-[11px] leading-relaxed text-muted-foreground">
                          {treeAvailable
                            ? `Forensic linking tree ready. Trace connections from ${pickEntity(result, "")}.`
                            : "Graph traversal unavailable for this query (no clear target entity identified). View the evidence KPIs instead."}
                        </p>
                        <button
                          onClick={() => {
                            if (!treeAvailable) {
                              setTreeEntity("");
                              setTreeNonce((n) => n + 1);
                              setGlobe(true);
                            } else {
                              openTree(result);
                            }
                          }}
                          className="flex w-full items-center justify-center gap-2 rounded-lg bg-cyan-500/10 px-4 py-2.5 text-xs font-semibold text-cyan-400 transition-colors hover:bg-cyan-500/20"
                        >
                          <Network className="size-4" />
                          {treeAvailable ? "Open Visual Graph" : "Open Data View"}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* options below the answer: LLM tree only if it exists */}
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-border/60 bg-background/40 px-2.5 py-1.5 text-[10px]">
                    {treeAvailable && (
                      <button
                        onClick={() => void openTree(result)}
                        className="ml-auto flex items-center gap-1 rounded-md border border-cyan-500/30 px-2 py-1 font-mono text-cyan-400 transition-colors hover:bg-cyan-500/10"
                        title="Open the LLM-annotated forensic linking tree for this answer"
                      >
                        <Network className="size-3" />
                        LLM TREE
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* suggestions */}
            {messages.length <= 1 && !result && (
              <div className="flex flex-wrap gap-1.5 px-4 pb-1">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => void send(s)}
                    className="rounded-full border border-border/70 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-cyan-500/40 hover:text-cyan-400"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {/* input */}
            <div className="flex items-center gap-2 border-t border-border p-3">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    void send(draft);
                  }
                }}
                disabled={busy}
                placeholder="Ask the co-pilot…"
                className="min-w-0 flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring disabled:opacity-60"
              />
              <button
                onClick={() => void send(draft)}
                disabled={busy || !draft.trim()}
                aria-label="Send message"
                className="grid size-9 shrink-0 place-items-center rounded-lg bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {busy ? (
                  <span className="size-4 animate-spin rounded-full border-2 border-primary-foreground/40 border-t-primary-foreground" />
                ) : (
                  <Send className="size-4" />
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* floating button */}
      <div className="fixed bottom-5 right-5 z-[70]">
        {!open && (
          <span className="omni-ping pointer-events-none absolute inset-0 rounded-full border-2 border-cyan-500/50" />
        )}
        <button
          onClick={() => setOpen((v) => !v)}
          aria-label={open ? "Hide co-pilot" : "Open Tri-Netra Forensics co-pilot"}
          aria-expanded={open}
          className="omni-bob group relative grid size-16 place-items-center rounded-full border border-cyan-500/30 bg-card/90 shadow-xl shadow-cyan-950/40 backdrop-blur transition-transform hover:scale-105 active:scale-95"
        >
          <OmniEye pupil={{ x: 0, y: 0 }} ringPupil={{ x: 0, y: 0 }} className="size-12 drop-shadow" />
          <span className="absolute -right-0.5 -top-0.5 grid size-5 place-items-center rounded-full bg-cyan-500 text-background">
            <MessageSquare className="size-3" />
          </span>
        </button>
      </div>

      {/* analysis spinner (replaces the globe-to-map transition) */}
      <AnimatePresence>
        {globe && (
          <EyeSpinner 
            onDone={() => {
              setGlobe(false);
              setTreeOpen(true);
            }} 
          />
        )}
      </AnimatePresence>

      {/* standalone LLM tree overlay — blurred backdrop, nodes / leaves / connectors */}
      <AnimatePresence>
        {treeOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setTreeOpen(false)}
            className="fixed inset-0 z-[80] bg-black/60 backdrop-blur-md"
            role="dialog"
            aria-label="Linking tree visualization"
          >
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={(e) => e.stopPropagation()}
              className="flex h-full w-full flex-col overflow-hidden bg-card/95"
            >
              <header className="flex items-center justify-between gap-3 border-b border-border bg-gradient-to-r from-cyan-500/10 via-transparent to-violet-500/10 px-4 py-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <Network className="size-5 shrink-0 text-cyan-400" />
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm font-semibold tracking-tight">
                      LINKING TREE — LLM ANNOTATED
                    </p>
                    <p className="truncate text-xs text-muted-foreground">
                      root entity: {treeEntity || "auto-detected"}
                    </p>
                  </div>
                </div>
                <button
                  onClick={() => setTreeOpen(false)}
                  aria-label="Close tree"
                  className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              </header>
              <div className="min-h-0 flex-1 bg-background flex items-center justify-center">
                {treeAvailable ? (
                  <InvestigationGraph key={treeNonce} initialEntity={treeEntity} />
                ) : (
                  <div className="flex flex-col gap-6 items-center justify-center h-full max-h-full overflow-y-auto w-full">
                    <div className="text-xl font-semibold mb-2 tracking-[0.2em] text-slate-800/60 uppercase">Forensic Evidence Profile</div>
                    <div className="flex flex-wrap items-center justify-center gap-6 max-w-7xl">
                        {records.length > 0 ? records.slice(0, 5).map((r, i) => (
                            <div key={i} className="flex flex-col p-6 bg-white rounded-2xl shadow-2xl shadow-slate-200/50 border-t-4 border-t-cyan-500 border-x border-b border-slate-200 min-w-[320px] max-w-[360px] transform transition-transform hover:scale-105">
                                <div className="text-[11px] font-bold text-cyan-600 tracking-widest mb-4 uppercase">Profile Card 0{i+1}</div>
                                <div className="text-3xl font-black text-slate-800 tracking-tight mb-2">
                                  {r.transaction_amount ? `₹${Number(r.transaction_amount).toLocaleString()}` : (r.call_duration_seconds ? `${r.call_duration_seconds}s Call` : 'Record')}
                                </div>
                                <div className="space-y-1 mb-6 border-l-2 border-slate-200 pl-3">
                                  <div className="text-sm font-medium text-slate-600 line-clamp-1">{r.sender_account_number ? `Sender: ${r.sender_account_number}` : ''} {r.a_party_number ? `Caller: ${r.a_party_number}` : ''}</div>
                                  <div className="text-sm font-medium text-slate-600 line-clamp-1">{r.receiver_account_number ? `Receiver: ${r.receiver_account_number}` : ''} {r.b_party_number ? `Receiver: ${r.b_party_number}` : ''}</div>
                                  <div className="text-sm font-medium text-slate-600">{r.transaction_mode ? `Mode: ${r.transaction_mode}` : ''}</div>
                                </div>
                                <div className="mt-auto">
                                  <div className="text-[10px] font-mono text-slate-400 bg-slate-50 px-2 py-1.5 rounded-md inline-block">
                                    TS: {r.timestamp || r.call_start_time || r.session_start_time || r.date || 'N/A'}
                                  </div>
                                </div>
                            </div>
                        )) : (
                           <div className="text-slate-500">No records found.</div>
                        )}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
