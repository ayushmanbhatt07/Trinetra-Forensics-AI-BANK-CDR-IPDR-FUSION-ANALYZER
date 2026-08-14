"use client";

/**
 * Global Tri-Netra Forensics chatbot — anchored bottom-right on EVERY page.
 * Sends queries to the Investigative Co-Pilot API. On search it triggers the
 * full-page globe-to-map transition, then renders the answer with
 * evidence / CoT / graph tabs (all scrollable).
 *
 * PHASE 4 OPTIMIZATION:
 * Decouples `draft` input state into `ChatInputForm` so keystrokes ONLY re-render
 * the input box itself, eliminating re-render cascades across `OmniWidget`,
 * `CopilotMessageList`, `ReactMarkdown`, `CopilotSuggestions`, and `InvestigationGraph`.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { usePipeline } from "@/lib/pipeline-context";

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

const pickEntity = (res?: CopilotQueryResult | null, query?: string): string => {
  if (!res && !query) return "";
  if (res) {
    for (const cand of [
      res.graph_traversal?.root,
      res.graph_traversal?.entity_id,
      res.graph_traversal?.start_node,
      res.linking_tree?.root,
      res.linking_tree?.entity_id,
      res.linking_tree?.start_node,
      res.entity_resolution?.entity_id,
    ]) {
      if (cand && cand !== "none" && cand !== "unknown") return String(cand);
    }
    const r0 = res.records?.[0];
    if (r0) {
      const extracted =
        r0.account_no ||
        r0.transaction_id ||
        r0.sender_account_number ||
        r0.receiver_account_number ||
        r0.sender_account ||
        r0.receiver_account ||
        r0.sender_phone ||
        r0.receiver_phone ||
        r0.a_party_number ||
        r0.b_party_number ||
        r0.phone ||
        r0.id;
      if (extracted) return String(extracted);
    }
  }
  if (query) {
    const m = query.match(/\b(TXN[A-Z0-9_-]{3,}|ACC[A-Z0-9_-]{3,}|CDR[A-Z0-9_-]{3,}|\d{10})\b/i);
    if (m) return m[0];
  }
  return "";
};

// ─── isolated memoized chat input form ──────────────────────────────────
interface ChatInputFormProps {
  busy: boolean;
  onSend: (text: string) => void;
}

const ChatInputForm = React.memo(function ChatInputForm({
  busy,
  onSend,
}: ChatInputFormProps) {
  const [draft, setDraft] = useState("");

  const handleSubmit = useCallback((e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const clean = draft.trim();
    if (!clean || busy) return;
    onSend(clean);
    setDraft("");
  }, [draft, busy, onSend]);

  return (
    <div className="flex items-center gap-2 border-t border-border p-3">
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            handleSubmit();
          }
        }}
        disabled={busy}
        placeholder="Ask the co-pilot…"
        className="min-w-0 flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus:ring-2 focus:ring-ring disabled:opacity-60"
      />
      <button
        onClick={() => handleSubmit()}
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
  );
});

// ─── isolated memoized suggestions ───────────────────────────────────────
interface CopilotSuggestionsProps {
  visible: boolean;
  onSelect: (suggestion: string) => void;
}

const CopilotSuggestions = React.memo(function CopilotSuggestions({
  visible,
  onSelect,
}: CopilotSuggestionsProps) {
  if (!visible) return null;

  return (
    <div className="flex flex-wrap gap-1.5 px-4 pb-1">
      {SUGGESTIONS.map((s) => (
        <button
          key={s}
          onClick={() => onSelect(s)}
          className="rounded-full border border-border/70 px-2.5 py-1 text-[11px] text-muted-foreground transition-colors hover:border-cyan-500/40 hover:text-cyan-400"
        >
          {s}
        </button>
      ))}
    </div>
  );
});

// ─── isolated memoized header ───────────────────────────────────────────
const CopilotHeader = React.memo(function CopilotHeader({
  onClose,
}: {
  onClose: () => void;
}) {
  return (
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
        onClick={onClose}
        aria-label="Close chat"
        className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
      >
        <X className="size-4" />
      </button>
    </header>
  );
});

// ─── isolated memoized message history list ─────────────────────────────
interface CopilotMessageListProps {
  messages: Msg[];
  result: CopilotQueryResult | null;
  tab: "answer" | "evidence" | "cot" | "graph";
  onSetTab: (tab: "answer" | "evidence" | "cot" | "graph") => void;
  records: any[];
  treeAvailable: boolean;
  onOpenTree: (res: CopilotQueryResult) => void;
  onOpenDataView: () => void;
  scrollRef: React.RefObject<HTMLDivElement | null>;
}

const CopilotMessageList = React.memo(function CopilotMessageList({
  messages,
  result,
  tab,
  onSetTab,
  records,
  treeAvailable,
  onOpenTree,
  onOpenDataView,
  scrollRef,
}: CopilotMessageListProps) {
  return (
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
                onClick={() => onSetTab(t)}
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
                  3D Forensic linking tree ready. Trace connections, entity roles, and anomaly flows from{" "}
                  <span className="font-mono font-semibold text-cyan-400">
                    {pickEntity(result, "") || "the central network entity"}
                  </span>
                  .
                </p>
                <button
                  onClick={() => onOpenTree(result)}
                  className="flex w-full items-center justify-center gap-2 rounded-lg border border-cyan-500/40 bg-cyan-500/15 px-4 py-2.5 text-xs font-semibold text-cyan-300 transition-all hover:bg-cyan-500/25 hover:shadow-md hover:shadow-cyan-500/20 active:scale-[0.99]"
                >
                  <Network className="size-4 animate-pulse text-cyan-400" />
                  Open 3D Investigation Tree
                </button>
              </div>
            )}
          </div>

          {/* options below the answer: prominent 3D LLM tree launcher */}
          <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 rounded-lg border border-border/60 bg-background/50 px-3 py-2 text-[10px]">
            <div className="flex items-center gap-1.5 text-muted-foreground font-mono text-[9px] uppercase tracking-wider">
              <Network className="size-3 text-cyan-400" />
              <span>3D Forensic Graph</span>
            </div>
            <button
              onClick={() => onOpenTree(result)}
              className="flex items-center gap-1.5 rounded-md border border-cyan-500/50 bg-gradient-to-r from-cyan-500/20 to-blue-500/20 px-3 py-1 font-mono text-xs font-bold text-cyan-300 shadow-sm shadow-cyan-500/20 transition-all hover:border-cyan-400 hover:from-cyan-500/30 hover:to-blue-500/30 hover:text-white active:scale-95"
              title="Open the 3D LLM-annotated forensic linking tree for this investigation"
            >
              <Network className="size-3.5 animate-pulse text-cyan-300" />
              3D LLM TREE
            </button>
          </div>
        </div>
      )}
    </div>
  );
});

// ─── main OmniWidget component ──────────────────────────────────────────
export function OmniWidget() {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  const pathname = usePathname();
  const [isIngested, setIsIngested] = useState(false);
  const { user } = useAuth();
  const { pipeline, isFusedReady, isReady } = usePipeline();

  useEffect(() => {
    if (!user) {
      setIsIngested(false);
      return;
    }
    const ingested = Boolean(pipeline?.dataset_id || isFusedReady || isReady);
    setIsIngested(ingested);
    if (ingested) {
      import("@/components/dashboard/sections/reports").then((m) => m.prefetchReports().catch(() => {}));
    }
  }, [user, pipeline?.dataset_id, isFusedReady, isReady]);

  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([
    {
      from: "omni",
      text: "Tri-Netra Forensics Co-Pilot online. Ask anything about the loaded bank / CDR / IPDR corpus.",
    },
  ]);
  const [busy, setBusy] = useState(false);
  const [globe, setGlobe] = useState(false);
  const [result, setResult] = useState<CopilotQueryResult | null>(null);
  const [tab, setTab] = useState<"answer" | "evidence" | "cot" | "graph">("answer");
  const [treeOpen, setTreeOpen] = useState(false);
  const [treeEntity, setTreeEntity] = useState("");
  const [treeNonce, setTreeNonce] = useState(0);
  const [treeAvailable, setTreeAvailable] = useState(false);
  const [lastExtractedEntity, setLastExtractedEntity] = useState("");

  const openTree = useCallback((res?: CopilotQueryResult | null, entityOverride?: string) => {
    const entity = entityOverride || lastExtractedEntity || pickEntity(res, "");
    setTreeEntity(entity || "");
    setTreeNonce((n) => n + 1);
    setGlobe(true);
  }, [lastExtractedEntity]);

  const handleOpenDataView = useCallback(() => {
    setTreeEntity("");
    setTreeNonce((n) => n + 1);
    setGlobe(true);
  }, []);

  const handleCloseChat = useCallback(() => {
    setOpen(false);
  }, []);

  const handleToggleChat = useCallback(() => {
    setOpen((v) => !v);
  }, []);

  const handleCloseTree = useCallback(() => {
    setTreeOpen(false);
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, result, tab]);

  const send = useCallback(async (text: string) => {
    const clean = text.trim();
    if (!clean || busy) return;
    setBusy(true);
    setResult(null);
    setTreeAvailable(false);
    setTab("answer");
    setMessages((m) => [...m, { from: "user", text: clean }]);
    try {
      const res = await api.copilotQuery(clean);
      setResult(res);
      setMessages((m) => [...m, { from: "omni", text: answerText(res) }]);
      setBusy(false);

      const entity = pickEntity(res, clean);
      setLastExtractedEntity(entity);
      setTreeAvailable(true);
    } catch (e) {
      const msg = (e as { message?: string })?.message ?? "Co-Pilot unavailable — is the backend running?";
      setMessages((m) => [...m, { from: "omni", text: msg }]);
      setBusy(false);
    }
  }, [busy]);

  const records = useMemo(() => result?.records ?? [], [result]);
  const suggestionsVisible = useMemo(() => messages.length <= 1 && !result, [messages.length, result]);

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
            onClick={handleCloseChat}
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
            {/* memoized header */}
            <CopilotHeader onClose={handleCloseChat} />

            {/* memoized messages list & markdown (isolated from typing) */}
            <CopilotMessageList
              messages={messages}
              result={result}
              tab={tab}
              onSetTab={setTab}
              records={records}
              treeAvailable={treeAvailable}
              onOpenTree={openTree}
              onOpenDataView={handleOpenDataView}
              scrollRef={scrollRef}
            />

            {/* memoized suggestions (isolated from typing) */}
            <CopilotSuggestions
              visible={suggestionsVisible}
              onSelect={send}
            />

            {/* memoized isolated chat input (only this updates on keystrokes) */}
            <ChatInputForm
              busy={busy}
              onSend={send}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* floating button */}
      <div className="fixed bottom-5 right-5 z-[70]">
        {!open && (
          <span className="omni-ping pointer-events-none absolute inset-0 rounded-full border-2 border-cyan-500/50" />
        )}
        <button
          onClick={handleToggleChat}
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

      {/* analysis spinner */}
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
            onClick={handleCloseTree}
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
                  onClick={handleCloseTree}
                  aria-label="Close tree"
                  className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  <X className="size-4" />
                </button>
              </header>
              <div className="min-h-0 flex-1 bg-background flex items-center justify-center">
                <InvestigationGraph key={treeNonce} initialEntity={treeEntity} />
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

