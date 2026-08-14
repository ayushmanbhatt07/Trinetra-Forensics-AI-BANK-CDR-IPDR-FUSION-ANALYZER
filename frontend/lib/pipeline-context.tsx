"use client";

import React, { createContext, useContext, useEffect, useRef, useState, useCallback, useMemo, ReactNode } from "react";
import { api, type PipelineStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { prefetchAlerts } from "@/components/dashboard/sections/anomalies";

interface PipelineContextType {
  pipeline: PipelineStatus | null;
  /** True until the FIRST pipeline-status poll has completed */
  loading: boolean;
  refetchPipeline: () => Promise<void>;
  isFusedReady: boolean;
  isAnomaliesReady: boolean;
  isGraphReady: boolean;
  isReady: boolean;
  isProcessing: boolean;
  isError: boolean;
}

const PipelineContext = createContext<PipelineContextType>({
  pipeline: null,
  loading: true,
  refetchPipeline: async () => {},
  isFusedReady: false,
  isAnomaliesReady: false,
  isGraphReady: false,
  isReady: false,
  isProcessing: false,
  isError: false,
});

// Stage-aware constant sets defined once at module scope to avoid re-allocation
const FUSED_STAGES = new Set(["FUSED_READY", "SCORING", "ANOMALIES_READY", "GRAPHS", "READY"]);
const ANOMALY_STAGES = new Set(["ANOMALIES_READY", "GRAPHS", "READY"]);
const GRAPH_STAGES = new Set(["GRAPHS", "READY"]);
const PROCESSING_STAGES = new Set(["PARSING", "FUSING", "SCORING", "GRAPHS"]);
const TERMINAL_STAGES = new Set(["IDLE", "ERROR", "READY", "CANCELLED"]);

function isSamePipelineStatus(prev: PipelineStatus | null, next: PipelineStatus | null): boolean {
  if (prev === next) return true;
  if (!prev || !next) return false;
  return (
    prev.status === next.status &&
    prev.progress === next.progress &&
    prev.ready === next.ready &&
    prev.fused_ready === next.fused_ready &&
    prev.anomalies_ready === next.anomalies_ready &&
    prev.graphs_ready === next.graphs_ready &&
    prev.dataset_id === next.dataset_id &&
    prev.job_id === next.job_id &&
    prev.error === next.error
  );
}

export function PipelineProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [pollTrigger, setPollTrigger] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const isActiveRef = useRef(true);
  const lastPrefetchedStageRef = useRef<string>("");

  const fetchStatus = useCallback(async () => {
    if (!user) {
      setPipeline((prev) => (prev === null ? prev : null));
      setLoading(false);
      return;
    }
    try {
      const res = await api.pipelineStatus();
      setPipeline((prev) => (isSamePipelineStatus(prev, res) ? prev : res));
    } catch {
      // Don't clear pipeline on intermittent network error
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    isActiveRef.current = true;

    const poll = async () => {
      if (!user) {
        setLoading(false);
        return;
      }
      try {
        const res = await api.pipelineStatus();
        if (!isActiveRef.current) return;
        setPipeline((prev) => (isSamePipelineStatus(prev, res) ? prev : res));
        setLoading(false);

        // Proactive background prefetching ONCE when stage transitions
        const stageKey = `${res.job_id || "default"}:${res.status}`;
        if (lastPrefetchedStageRef.current !== stageKey) {
          lastPrefetchedStageRef.current = stageKey;
          if (res.anomalies_ready || ANOMALY_STAGES.has(res.status)) {
            prefetchAlerts(res.job_id, true).catch(() => {});
            if (typeof window !== "undefined") {
              window.dispatchEvent(new CustomEvent("pipeline:anomalies_ready"));
            }
          }
          if (res.fused_ready || FUSED_STAGES.has(res.status)) {
            api.summary().catch(() => {});
            if (typeof window !== "undefined") {
              window.dispatchEvent(new CustomEvent("pipeline:fused_ready"));
            }
          }
        }

        // Only continue polling if actively processing (not yet at a terminal state)
        const isTerminal =
          !res ||
          res.ready ||
          TERMINAL_STAGES.has(res.status);

        if (!isTerminal) {
          // Fast responsive polling during active processing stages (PARSING, FUSING, SCORING, GRAPHS)
          const interval = 600;
          timerRef.current = setTimeout(poll, interval);
        }
      } catch {
        if (!isActiveRef.current) return;
        setLoading(false);
        // On error, retry in 3000ms
        timerRef.current = setTimeout(poll, 3000);
      }
    };

    poll();

    return () => {
      isActiveRef.current = false;
      if (timerRef.current !== undefined) clearTimeout(timerRef.current);
    };
  }, [user, pollTrigger]);

  const refetchPipeline = useCallback(async () => {
    setPollTrigger((t) => t + 1);
    await fetchStatus();
  }, [fetchStatus]);

  // Stage-aware derived booleans memoized against pipeline status
  const isFusedReady = useMemo(
    () => Boolean(pipeline?.fused_ready || (pipeline && FUSED_STAGES.has(pipeline.status))),
    [pipeline]
  );

  const isAnomaliesReady = useMemo(
    () => Boolean(pipeline?.anomalies_ready || (pipeline && ANOMALY_STAGES.has(pipeline.status))),
    [pipeline]
  );

  const isGraphReady = useMemo(
    () => Boolean(pipeline && GRAPH_STAGES.has(pipeline.status)),
    [pipeline]
  );

  const isReady = useMemo(
    () => Boolean(pipeline?.ready || pipeline?.status === "READY"),
    [pipeline]
  );

  const isProcessing = useMemo(
    () => Boolean(!loading && pipeline && PROCESSING_STAGES.has(pipeline.status)),
    [loading, pipeline]
  );

  const isError = useMemo(
    () => Boolean(pipeline?.status === "ERROR"),
    [pipeline]
  );

  // Stable memoized context value object to prevent broadcasting re-renders to all consumers
  const value = useMemo(
    () => ({
      pipeline,
      loading,
      refetchPipeline,
      isFusedReady,
      isAnomaliesReady,
      isGraphReady,
      isReady,
      isProcessing,
      isError,
    }),
    [
      pipeline,
      loading,
      refetchPipeline,
      isFusedReady,
      isAnomaliesReady,
      isGraphReady,
      isReady,
      isProcessing,
      isError,
    ]
  );

  return (
    <PipelineContext.Provider value={value}>
      {children}
    </PipelineContext.Provider>
  );
}

export function usePipeline() {
  return useContext(PipelineContext);
}
