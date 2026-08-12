"use client";

import React, { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { api, type PipelineStatus } from "@/lib/api";
import { useAuth } from "@/lib/auth";

interface PipelineContextType {
  pipeline: PipelineStatus | null;
  loading: boolean;
  refetchPipeline: () => Promise<void>;
  isFusedReady: boolean;
  isAnomaliesReady: boolean;
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
  isReady: false,
  isProcessing: false,
  isError: false,
});

export function PipelineProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    if (!user) {
      setPipeline(null);
      setLoading(false);
      return;
    }
    try {
      const res = await api.pipelineStatus();
      setPipeline(res);
    } catch (e) {
      // Don't clear pipeline on intermittent network error
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    let isActive = true;
    let timer: number | undefined;

    const poll = async () => {
      if (!user) return;
      try {
        const res = await api.pipelineStatus();
        if (!isActive) return;
        setPipeline(res);
        setLoading(false);

        // Continue polling if actively processing
        if (res && !res.ready && res.status !== "IDLE" && res.status !== "ERROR") {
          timer = window.setTimeout(poll, 2000);
        }
      } catch (e) {
        if (!isActive) return;
        setLoading(false);
        timer = window.setTimeout(poll, 5000);
      }
    };

    poll();

    return () => {
      isActive = false;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, [user]);

  const refetchPipeline = useCallback(async () => {
    await fetchStatus();
  }, [fetchStatus]);

  const isFusedReady = Boolean(
    pipeline?.fused_ready ||
    (pipeline && ["FUSED_READY", "SCORING", "ANOMALIES_READY", "GRAPHS", "READY"].includes(pipeline.status))
  );

  const isAnomaliesReady = Boolean(
    pipeline?.anomalies_ready ||
    (pipeline && ["ANOMALIES_READY", "GRAPHS", "READY"].includes(pipeline.status))
  );

  const isReady = Boolean(pipeline?.ready || pipeline?.status === "READY");
  const isProcessing = Boolean(pipeline && ["PARSING", "FUSING", "SCORING", "GRAPHS"].includes(pipeline.status));
  const isError = Boolean(pipeline?.status === "ERROR");

  return (
    <PipelineContext.Provider
      value={{
        pipeline,
        loading,
        refetchPipeline,
        isFusedReady,
        isAnomaliesReady,
        isReady,
        isProcessing,
        isError,
      }}
    >
      {children}
    </PipelineContext.Provider>
  );
}

export function usePipeline() {
  return useContext(PipelineContext);
}
