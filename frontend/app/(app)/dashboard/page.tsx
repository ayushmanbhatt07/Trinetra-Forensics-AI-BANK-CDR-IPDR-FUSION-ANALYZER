"use client";

import { useState, useEffect, useCallback } from "react";
import { Sidebar } from "@/components/dashboard/sidebar";
import { Header } from "@/components/dashboard/header";
import { OverviewSection } from "@/components/dashboard/sections/overview";
import { IngestionSection } from "@/components/dashboard/sections/ingestion";
import { NetworkSection } from "@/components/dashboard/sections/network";
import { AnomaliesSection } from "@/components/dashboard/sections/anomalies";
import { TimelineSection } from "@/components/dashboard/sections/timeline";
import { ReportsSection } from "@/components/dashboard/sections/reports";
import { SettingsSection } from "@/components/dashboard/sections/settings";
import { SearchSection } from "@/components/dashboard/sections/search";
import { FusedSection } from "@/components/dashboard/sections/fused";
import { TransactionSTRReport } from "@/components/omni/transaction-str";
import { usePipeline } from "@/lib/pipeline-context";

export type Section = "overview" | "ingestion" | "network" | "fused" | "anomalies" | "timeline" | "reports" | "settings" | "search";

export default function Dashboard() {
  const [activeSection, setActiveSection] = useState<Section>("overview");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [strTransactionId, setStrTransactionId] = useState<string | null>(null);
  const [strFallbackTxn, setStrFallbackTxn] = useState<any>(null);
  const [showIngestPrompt, setShowIngestPrompt] = useState(false);

  const { isFusedReady, pipeline, loading: pipelineLoading } = usePipeline();

  const handleCloseStr = useCallback(() => {
    setStrTransactionId(null);
    setStrFallbackTxn(null);
  }, []);

  const handleOpenIngestion = useCallback(() => {
    setActiveSection("ingestion");
    setShowIngestPrompt(false);
  }, []);

  useEffect(() => {
    const handleNav = (e: Event) => {
      const customEvent = e as CustomEvent<Section>;
      if (customEvent.detail) {
        setActiveSection(customEvent.detail);
        if (customEvent.detail === "ingestion") {
          setShowIngestPrompt(false);
        }
      }
    };
    
    const handleStr = (e: Event) => {
      const customEvent = e as CustomEvent<any>;
      if (customEvent.detail) {
        if (typeof customEvent.detail === "string") {
          setStrTransactionId(customEvent.detail);
          setStrFallbackTxn(null);
        } else if (typeof customEvent.detail === "object") {
          setStrTransactionId(customEvent.detail.id || customEvent.detail.transaction_id || "");
          setStrFallbackTxn(customEvent.detail.alert || customEvent.detail.txn || customEvent.detail);
        }
      }
    };

    const handleApi409 = () => {
      if (!isFusedReady && !pipeline?.dataset_id) {
        setShowIngestPrompt(true);
      }
    };

    window.addEventListener("nav:section", handleNav);
    window.addEventListener("pdf:transaction", handleStr);
    window.addEventListener("api:409", handleApi409);
    return () => {
      window.removeEventListener("nav:section", handleNav);
      window.removeEventListener("pdf:transaction", handleStr);
      window.removeEventListener("api:409", handleApi409);
    };
  }, [isFusedReady, pipeline?.dataset_id]);


  return (
    <div className="flex min-h-screen bg-background">
      <Sidebar
        activeSection={activeSection}
        onSectionChange={setActiveSection}
        collapsed={sidebarCollapsed}
        onCollapsedChange={setSidebarCollapsed}
      />
      <div
        className={`flex-1 flex flex-col transition-all duration-300 ease-out ${
          sidebarCollapsed ? "ml-[72px]" : "ml-[260px]"
        }`}
      >
        <Header activeSection={activeSection} />
        <main className="flex-1 p-6 overflow-auto">
          {/* Sections are kept MOUNTED at all times to preserve fetched data and
              prevent the pipeline-context loading race on navigation.
              React.memo on each section prevents inactive sections from re-rendering. */}
          <div style={{ display: activeSection === "overview" ? "block" : "none" }}>
            <OverviewSection />
          </div>
          <div style={{ display: activeSection === "ingestion" ? "block" : "none" }}>
            <IngestionSection />
          </div>
          <div style={{ display: activeSection === "network" ? "block" : "none" }}>
            <NetworkSection />
          </div>
          <div style={{ display: activeSection === "fused" ? "block" : "none" }}>
            <FusedSection />
          </div>
          <div style={{ display: activeSection === "anomalies" ? "block" : "none" }}>
            <AnomaliesSection />
          </div>
          <div style={{ display: activeSection === "timeline" ? "block" : "none" }}>
            <TimelineSection />
          </div>
          <div style={{ display: activeSection === "reports" ? "block" : "none" }}>
            <ReportsSection />
          </div>
          <div style={{ display: activeSection === "settings" ? "block" : "none" }}>
            <SettingsSection />
          </div>
          <div style={{ display: activeSection === "search" ? "block" : "none" }}>
            <SearchSection />
          </div>

        </main>
      </div>

      {strTransactionId && (
        <TransactionSTRReport 
          transactionId={strTransactionId} 
          fallbackTransaction={strFallbackTxn}
          onClose={handleCloseStr} 
        />
      )}

      {showIngestPrompt && !isFusedReady && !pipeline?.dataset_id && !pipelineLoading && activeSection !== "ingestion" && (
        <div className="fixed inset-0 z-[100] flex flex-col items-center justify-center overflow-hidden">
          {/* Background Image with 10-20% blur */}
          <div 
            className="absolute inset-0 scale-105 bg-cover bg-center bg-no-repeat blur-[4px]"
            style={{ backgroundImage: "url('/logo.jpg')" }}
          />
          {/* Dark overlay to ensure text readability */}
          <div className="absolute inset-0 bg-background/70" />
          
          <div className="relative z-10 flex flex-col items-center space-y-6">
            <h2 className="text-2xl font-bold tracking-widest text-emerald-400 drop-shadow-[0_0_8px_rgba(52,211,153,0.8)]">
              NO DATA LOADED
            </h2>
            <button
              onClick={handleOpenIngestion}
              className="group relative overflow-hidden rounded-full border border-emerald-500/50 bg-emerald-950/40 px-10 py-4 font-mono font-bold text-emerald-400 shadow-[0_0_20px_rgba(52,211,153,0.3)] transition-all hover:scale-105 hover:bg-emerald-900/50 hover:shadow-[0_0_30px_rgba(52,211,153,0.6)]"
            >
              <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-emerald-400/10 to-transparent"></div>
              Upload / Ingest Data Now
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
