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
  Plus,
  Sparkles,
  RotateCcw,
  Zap,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { api, type CopilotQueryResult, type CopilotTokenStats } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { OmniEye } from "./omni-eye";
import { EyeSpinner } from "./eye-spinner";
import { InvestigationGraph } from "./investigation-graph";
import { usePathname } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Msg {
  from: "user" | "omni";
  text: string;
  result?: CopilotQueryResult;
}

const SUGGESTIONS = [
  "Top 5 largest transactions",
  "Accounts with rapid layering",
  "Calls before transactions pattern",
  "Who is the most suspicious entity?",
  "Transfers within 10 mins of calls",
  "Find shared IP & IMEI devices",
  "Identify mule account clusters",
  "High-risk transfers above ₹50,000",
];

const normalizeMarkdown = (text: any): string => {
  if (!text) return "";
  let s = String(text).replace(/\\n/g, "\n");
  // Fix double pipes in table rows: "||" -> "|\n|"
  s = s.replace(/\|\s*\|+/g, "|\n|");
  return s.trim();
};

const answerText = (r: CopilotQueryResult) => {
  const raw = r.answer ?? r.general_answer ?? r.executive_summary ?? "Query processed.";
  return normalizeMarkdown(raw);
};

const pickEntity = (res: CopilotQueryResult, query: string): string => {
  if (query) {
    const txnMatch = query.match(/\bTXN[A-Z0-9]{4,}\b/i);
    if (txnMatch) return txnMatch[0].toUpperCase();
    
    const phoneMatch = query.match(/\b(?:91)?[6-9]\d{9}\b/);
    if (phoneMatch) return phoneMatch[0];
    
    const accMatch = query.match(/\b\d{8,18}\b/);
    if (accMatch) return accMatch[0];
  }

  for (const cand of [
    res.entity_resolution?.entity_id,
    res.graph_traversal?.root,
    res.graph_traversal?.entity_id,
    res.graph_traversal?.start_node,
    res.linking_tree?.root,
    res.linking_tree?.entity_id,
    res.linking_tree?.start_node,
  ]) {
    if (cand && cand !== "none" && cand !== "unknown") return String(cand);
  }

  if (res.records && res.records.length > 0) {
    for (const r of res.records) {
      const cand = r.transaction_id || r.sender_account_number || r.receiver_account_number || r.a_party_number || r.b_party_number || (r as any).account_no || (r as any).phone;
      if (cand && String(cand) !== "unknown" && String(cand) !== "none") {
        return String(cand);
      }
    }
  }

  return "";
};

export function OmniWidget() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastUserQueryRef = useRef<string>("");

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
  const [treeAvailable, setTreeAvailable] = useState(false);
  const [lastExtractedEntity, setLastExtractedEntity] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [tokenStats, setTokenStats] = useState<CopilotTokenStats | null>(null);
  const [showTokenDetails, setShowTokenDetails] = useState(false);

  const fetchTokenStats = useCallback(() => {
    api.copilotTokenStats()
      .then((st) => setTokenStats(st))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (open) {
      fetchTokenStats();
      const interval = setInterval(fetchTokenStats, 6000);
      return () => clearInterval(interval);
    }
  }, [open, fetchTokenStats]);

  const handleNewChat = useCallback(() => {
    setMessages([
      {
        from: "omni",
        text: "New investigative chat started. Ask anything about the loaded bank / CDR / IPDR corpus.",
      },
    ]);
    setResult(null);
    setDraft("");
    setTreeAvailable(false);
    setTab("answer");
    setLastExtractedEntity("");
    setShowSuggestions(true);
    fetchTokenStats();
  }, [fetchTokenStats]);

  const openTree = useCallback((res: CopilotQueryResult, entityOverride?: string) => {
    const entity = entityOverride || pickEntity(res, lastUserQueryRef.current) || lastExtractedEntity;
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
    lastUserQueryRef.current = clean;
    setDraft("");
    setBusy(true);
    setResult(null);
    setTreeAvailable(false);
    setTab("answer");
    setMessages((m) => [...m, { from: "user", text: clean }]);
    try {
      const res = await api.copilotQuery(clean);
      setResult(res);
      setMessages((m) => [...m, { from: "omni", text: answerText(res), result: res }]);
      fetchTokenStats();
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
      setShowSuggestions(true); // Keep prompt templates visible for continuous investigative prompts
      fetchTokenStats();
    }
  }, [busy, fetchTokenStats]);

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
              <div className="size-10 shrink-0">
                <OmniEye pupil={{ x: 0, y: 0 }} ringPupil={{ x: 0, y: 0 }} className="size-full drop-shadow" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-mono text-sm font-semibold tracking-tight">Tri-Netra Forensics</p>
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <span className="inline-block size-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  investigative co-pilot · online
                </p>
              </div>
              <div className="flex items-center gap-2">
                {/* Mathematical Token Usage Indicator */}
                {tokenStats && (
                  <div className="relative">
                    <button
                      onClick={() => setShowTokenDetails((v) => !v)}
                      title="Click to view live LLM Token & Capacity Analytics"
                      className={cn(
                        "flex items-center gap-1.5 rounded-lg border px-2 py-1 font-mono text-[11px] transition-colors shadow-sm",
                        tokenStats.pct_remaining > 50
                          ? "border-emerald-500/40 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-500/20"
                          : tokenStats.pct_remaining > 20
                          ? "border-amber-500/40 bg-amber-950/40 text-amber-300 hover:bg-amber-500/20"
                          : "border-rose-500/40 bg-rose-950/40 text-rose-300 hover:bg-rose-500/20"
                      )}
                    >
                      <Zap className="size-3 text-cyan-400 animate-pulse" />
                      <span>{tokenStats.pct_remaining}% TPM</span>
                    </button>

                    {/* Popover Analytics Card */}
                    {showTokenDetails && (
                      <div className="absolute right-0 top-9 z-[80] w-64 rounded-xl border border-slate-700/80 bg-slate-900/95 p-3 font-mono text-xs shadow-2xl backdrop-blur-xl text-slate-200 space-y-2 select-none">
                        <div className="flex items-center justify-between border-b border-slate-700/60 pb-1.5">
                          <span className="text-[10px] font-bold uppercase text-cyan-400 tracking-wider">LLM Quota Analytics</span>
                          <span className="text-[9px] text-slate-400">{tokenStats.active_keys_count} Groq Keys</span>
                        </div>
                        <div className="space-y-1 text-[11px]">
                          <div className="flex justify-between">
                            <span className="text-slate-400">Active Model:</span>
                            <span className="font-semibold text-cyan-300">{tokenStats.active_model.split('/').pop()}</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-400">Total Capacity:</span>
                            <span>{(tokenStats.total_tpm_capacity / 1000).toFixed(0)}k TPM</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-400">1-Min Usage:</span>
                            <span>{tokenStats.used_last_minute.toLocaleString()} tokens</span>
                          </div>
                          <div className="flex justify-between">
                            <span className="text-slate-400">Remaining Quota:</span>
                            <span className="text-emerald-400 font-bold">{tokenStats.pct_remaining}%</span>
                          </div>
                          {tokenStats.last_query?.total_tokens > 0 && (
                            <div className="mt-1.5 pt-1.5 border-t border-slate-800 text-[10px] text-slate-400">
                              Last Query: {tokenStats.last_query.prompt_tokens} prompt + {tokenStats.last_query.completion_tokens} answer = <strong className="text-slate-200">{tokenStats.last_query.total_tokens} tokens</strong>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}

                <button
                  onClick={handleNewChat}
                  title="Start a new chat session"
                  className="flex items-center gap-1 rounded-lg border border-cyan-500/40 bg-cyan-950/40 px-2.5 py-1 font-mono text-xs text-cyan-300 hover:bg-cyan-500/20 hover:text-white transition-colors"
                >
                  <Plus className="size-3.5" />
                  <span>New Chat</span>
                </button>
                <button
                  onClick={() => setOpen(false)}
                  aria-label="Close chat"
                  className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              </div>
            </header>

            {/* messages */}
            <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto p-4 custom-scrollbar">
              {messages.map((m, i) => {
                if (m.from === "user") {
                  return (
                    <div
                      key={i}
                      className="self-end max-w-[88%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground leading-relaxed shadow-sm"
                    >
                      {m.text}
                    </div>
                  );
                }

                // Omni Assistant message card
                const res = m.result;
                if (!res) {
                  return (
                    <div
                      key={i}
                      className="self-start max-w-[88%] rounded-2xl rounded-bl-sm bg-secondary/80 px-4 py-2.5 text-sm text-secondary-foreground leading-relaxed whitespace-pre-wrap"
                    >
                      {m.text}
                    </div>
                  );
                }

                return (
                  <div key={i} className="self-start w-full space-y-2">
                    <div className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
                      <BrainCircuit className="size-3.5 text-cyan-500" />
                      {res.mode === "deterministic_fallback" ? (
                        <span className="text-amber-400 font-bold">⚠️ DEGRADED MODE (DETERMINISTIC FALLBACK)</span>
                      ) : (
                        <span>
                          {res.mode ?? "sql"} · {res.llm_provider || "groq"}
                          {res.llm_model ? ` (${res.llm_model.split("/").pop()})` : ""}
                        </span>
                      )}
                      {res.llm_latency_ms ? ` · ${(res.llm_latency_ms / 1000).toFixed(1)}s` : ""}
                    </div>
                    {res.mode === "deterministic_fallback" && (
                      <div className="rounded-lg border border-amber-500/40 bg-amber-950/30 p-2.5 text-xs text-amber-300 font-mono flex items-center gap-2 shadow-sm">
                        <span>⚠️ AI Co-Pilot operating in deterministic fallback mode. All configured LLM providers/models are currently unavailable.</span>
                      </div>
                    )}
                    <div className="w-full rounded-xl border border-border/70 bg-background/60 p-4 text-sm leading-relaxed space-y-3 shadow-inner">
                      <div className="space-y-2 text-foreground/90 font-sans">
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
                              <div className="overflow-x-auto my-3 rounded-lg border border-cyan-500/30 bg-slate-950/70 shadow-md">
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
                          {answerText(res)}
                        </ReactMarkdown>
                      </div>
                      {res.explainability && (
                        <div className="mt-2 rounded-lg border border-emerald-500/25 bg-emerald-500/5 p-2.5">
                          <p className="mb-1 flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-widest text-emerald-400">
                            <BrainCircuit className="size-3" />
                            why this is suspicious
                          </p>
                          <div className="text-[11px] leading-relaxed text-foreground/85 space-y-1">
                            <ReactMarkdown
                              components={{
                                ul: ({ node, ...props }) => <ul className="list-disc pl-4 space-y-1 my-1" {...props} />,
                                p: ({ node, ...props }) => <p className="my-1" {...props} />,
                                strong: ({ node, ...props }) => <strong className="font-semibold text-slate-100" {...props} />
                              }}
                            >
                              {String(res.explainability).replace(/\\n/g, "\n")}
                            </ReactMarkdown>
                          </div>
                        </div>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-lg border border-border/60 bg-background/40 px-2.5 py-1.5 text-[10px]">
                      <button
                        onClick={() => void openTree(res)}
                        className="ml-auto flex items-center gap-1 rounded-md border border-cyan-500/30 px-2.5 py-1 font-mono text-cyan-400 transition-colors hover:bg-cyan-500/10 hover:border-cyan-400 active:scale-95"
                        title="Open the LLM-annotated forensic linking tree for this answer"
                      >
                        <Network className="size-3" />
                        LLM TREE
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* suggestions - sleek horizontal pill carousel without vertical scrollbar */}
            {showSuggestions && (
              <div className="border-t border-border/50 bg-slate-950/80 backdrop-blur-md px-3 py-2">
                <div className="mb-1.5 flex items-center justify-between text-[10px] font-mono text-cyan-400">
                  <span className="flex items-center gap-1"><Sparkles className="size-3 text-cyan-400" /> Quick Query Templates</span>
                  <button onClick={() => setShowSuggestions(false)} className="text-slate-500 hover:text-slate-300 text-[10px]">hide</button>
                </div>
                <div className="flex gap-1.5 overflow-x-auto no-scrollbar py-0.5 scroll-smooth">
                  {SUGGESTIONS.map((s) => (
                    <button
                      key={s}
                      onClick={() => void send(s)}
                      className="shrink-0 rounded-full border border-cyan-500/20 bg-slate-900/90 px-3 py-1 text-[11px] font-sans text-slate-300 transition-all hover:border-cyan-500/60 hover:bg-cyan-950/40 hover:text-cyan-300 active:scale-95 shadow-sm"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* input */}
            <div className="flex items-center gap-2 border-t border-border p-3">
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onFocus={() => setShowSuggestions(true)}
                onClick={() => setShowSuggestions(true)}
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
