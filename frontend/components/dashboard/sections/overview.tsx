"use client";

import React, { useEffect, useState } from "react";
import { FlipKpiCard } from "@/components/ui/flip-card";
import { Button } from "@/components/ui/button";
import { Database, ShieldAlert, Users, Target, FileText, PhoneCall, Banknote, Activity, Network, Download, Loader2 } from "lucide-react";
import { api, isNoDataLoaded, isPipelineNotReady, isNetworkOrWarmupError, type Summary, type CopilotStats } from "@/lib/api";
import { toast } from "sonner";
import { usePipeline } from "@/lib/pipeline-context";

export const OverviewSection = React.memo(function OverviewSection() {
  const { isFusedReady, isAnomaliesReady } = usePipeline();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [copilot, setCopilot] = useState<CopilotStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [strDownloading, setStrDownloading] = useState(false);

  const load = () => {
    api
      .summary()
      .then(setSummary)
      .catch((e) => {
        if (!isNoDataLoaded(e) && !isPipelineNotReady(e) && !isNetworkOrWarmupError(e)) {
          toast.error("Failed to load investigation overview.");
        }
      })
      .finally(() => setLoading(false));
  };

  const handleDownloadMasterSTR = async () => {
    setStrDownloading(true);
    toast.info("Generating FIU-IND Master STR Dossier...");
    try {
      await api.downloadReport();
      toast.success("Master STR Dossier downloaded successfully.");
    } catch (e: any) {
      toast.error(e?.message || "Failed to generate STR report.");
    } finally {
      setStrDownloading(false);
    }
  };

  const handleDownloadEntitySTR = async (kind: string, value: string) => {
    toast.info(`Generating ${kind.toUpperCase()} STR for ${value}...`);
    try {
      await api.downloadEntityReport(kind, value);
      toast.success(`Entity STR for ${value} downloaded.`);
    } catch (e: any) {
      toast.error(e?.message || `Failed to generate STR for ${value}.`);
    }
  };

  useEffect(() => {
    load();
  }, [isFusedReady, isAnomaliesReady]);

  useEffect(() => {
    const handleRefresh = () => load();
    window.addEventListener("pipeline:fused_ready", handleRefresh);
    window.addEventListener("pipeline:anomalies_ready", handleRefresh);
    return () => {
      window.removeEventListener("pipeline:fused_ready", handleRefresh);
      window.removeEventListener("pipeline:anomalies_ready", handleRefresh);
    };
  }, []);

  useEffect(() => {
    if (!summary) return;
    api
      .copilotStats()
      .then(setCopilot)
      .catch(() => setCopilot(null));
  }, [summary]);

  const total = summary
    ? summary.bank_records + summary.cdr_records + summary.ipdr_records
    : 0;
  const anomalies = summary ? summary.top_risk_accounts.filter((a) => a.score >= 50).length : 0;
  const entities = summary
    ? summary.entities.phones + summary.entities.accounts
    : 0;
  const avgRisk = summary && summary.top_risk_accounts.length
    ? (
        summary.top_risk_accounts.reduce((s, a) => s + a.score, 0) /
        summary.top_risk_accounts.length
      ).toFixed(1)
    : "0.0";

  return (
    <div className="space-y-6">
      {/* Top Banner Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-card/60 backdrop-blur-md border border-border/80 p-4 rounded-xl">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-red-950/40 border border-red-800/40 text-red-400">
            <ShieldAlert className="size-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-foreground tracking-wide font-mono">
              TRI-NETRA FORENSIC INTELLIGENCE SUITE
            </h2>
            <p className="text-xs text-muted-foreground">
              Cross-Dataset Correlation • Unified Entity Graph • Automated FIU-IND STR Generation
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <Button
            size="sm"
            onClick={handleDownloadMasterSTR}
            disabled={strDownloading || total === 0}
            className="bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs shadow-lg shadow-emerald-950/40"
          >
            {strDownloading ? (
              <Loader2 className="mr-1.5 size-4 animate-spin" />
            ) : (
              <FileText className="mr-1.5 size-4" />
            )}
            Download Master STR (PDF)
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => window.dispatchEvent(new CustomEvent("nav:section", { detail: "reports" }))}
            className="font-mono text-xs border-cyan-500/40 text-cyan-400 hover:bg-cyan-950/20"
          >
            Reports Center &rarr;
          </Button>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <FlipKpiCard
          data={{
            title: "Total Records Fused",
            value: loading ? "..." : total.toLocaleString(),
            change: summary ? `${summary.files.ok.length} files ingested` : "—",
            changeType: "neutral",
            icon: Database,
            delay: 0,
            accent: "#34d399",
            details: [
              { label: "Bank records", value: summary ? summary.bank_records.toLocaleString() : "—" },
              { label: "CDR records", value: summary ? summary.cdr_records.toLocaleString() : "—" },
              { label: "IPDR records", value: summary ? summary.ipdr_records.toLocaleString() : "—" },
              { label: "Files OK", value: summary ? String(summary.files.ok.length) : "—" },
            ],
            copyText: summary
              ? `Tri-Netra KPI — Total Records Fused\nBank: ${summary.bank_records}\nCDR: ${summary.cdr_records}\nIPDR: ${summary.ipdr_records}\nFiles: ${summary.files.ok.length} ingested`
              : "Tri-Netra KPI — Total Records Fused: no data loaded",
          }}
        />
        <FlipKpiCard
          data={{
            title: "High-Risk Accounts",
            value: loading ? "..." : String(anomalies),
            change: summary ? `of ${summary.top_risk_accounts.length} scored` : "—",
            changeType: "negative",
            icon: ShieldAlert,
            delay: 1,
            accent: "#f43f5e",
            details: [
              { label: "Risk ≥ 50", value: String(anomalies) },
              { label: "Scored accounts", value: summary ? String(summary.top_risk_accounts.length) : "—" },
              { label: "Top flag", value: summary?.top_risk_accounts[0]?.flags[0] ?? "—" },
            ],
            copyText: summary
              ? `Tri-Netra KPI — High-Risk Accounts\nRisk ≥ 50: ${anomalies}\nScored: ${summary.top_risk_accounts.length}\nTop flag: ${summary.top_risk_accounts[0]?.flags[0] ?? "—"}`
              : "Tri-Netra KPI — High-Risk Accounts: no data loaded",
          }}
        />
        <FlipKpiCard
          data={{
            title: "Suspicious Entities",
            value: loading ? "..." : entities.toLocaleString(),
            change: summary ? `${summary.entities.upi_ids} UPI ids` : "—",
            changeType: "neutral",
            icon: Users,
            delay: 2,
            accent: "#38bdf8",
            details: [
              { label: "Phones", value: summary ? String(summary.entities.phones) : "—" },
              { label: "Accounts", value: summary ? String(summary.entities.accounts) : "—" },
              { label: "UPI ids", value: summary ? String(summary.entities.upi_ids) : "—" },
            ],
            copyText: summary
              ? `Tri-Netra KPI — Suspicious Entities\nPhones: ${summary.entities.phones}\nAccounts: ${summary.entities.accounts}\nUPI ids: ${summary.entities.upi_ids}`
              : "Tri-Netra KPI — Suspicious Entities: no data loaded",
          }}
        />
        <FlipKpiCard
          data={{
            title: "Avg Risk Score",
            value: loading ? "..." : avgRisk,
            change: "top 10 accounts",
            changeType: "neutral",
            icon: Target,
            delay: 3,
            accent: "#a78bfa",
            details: [
              { label: "Threshold", value: "50 (HIGH)" },
              { label: "Top account", value: summary?.top_risk_accounts[0]?.account_no ?? "—" },
              { label: "Top score", value: summary?.top_risk_accounts[0] ? String(summary.top_risk_accounts[0].score) : "—" },
            ],
            copyText: summary && summary.top_risk_accounts.length
              ? `Tri-Netra KPI — Avg Risk Score\nAvg: ${avgRisk}\nTop: ${summary.top_risk_accounts[0].account_no} @ ${summary.top_risk_accounts[0].score}`
              : "Tri-Netra KPI — Avg Risk Score: no scored accounts",
          }}
        />
      </div>

      {!loading && summary && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <Banknote className="h-4 w-4 text-emerald-500" />
              <h3 className="text-sm font-semibold text-foreground">Top Risk Accounts</h3>
            </div>
            <div className="space-y-2">
              {summary.top_risk_accounts.length === 0 && (
                <p className="text-sm text-muted-foreground">No scored accounts yet.</p>
              )}
              {summary.top_risk_accounts.slice(0, 6).map((a) => (
                <div key={a.account_no} className="flex items-center justify-between text-sm py-1 border-b border-border/40 last:border-0">
                  <span className="font-mono text-xs text-foreground">{a.account_no}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground hidden sm:inline">{a.flags.slice(0, 2).join(", ") || "—"}</span>
                    <span className="font-bold text-red-500 font-mono text-xs">{a.score}</span>
                    <button
                      title={`Download STR PDF for account ${a.account_no}`}
                      onClick={() => handleDownloadEntitySTR("account", a.account_no)}
                      className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-emerald-400 transition-colors"
                    >
                      <Download className="size-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <PhoneCall className="h-4 w-4 text-emerald-500" />
              <h3 className="text-sm font-semibold text-foreground">Top Risk Phones</h3>
            </div>
            <div className="space-y-2">
              {summary.top_risk_phones.length === 0 && (
                <p className="text-sm text-muted-foreground">No scored phones yet.</p>
              )}
              {summary.top_risk_phones.slice(0, 6).map((p) => (
                <div key={p.phone} className="flex items-center justify-between text-sm py-1 border-b border-border/40 last:border-0">
                  <span className="font-mono text-xs text-foreground">{p.phone}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground hidden sm:inline">{p.flags.slice(0, 2).join(", ") || "—"}</span>
                    <span className="font-bold text-red-500 font-mono text-xs">{p.score}</span>
                    <button
                      title={`Download STR PDF for phone ${p.phone}`}
                      onClick={() => handleDownloadEntitySTR("phone", p.phone)}
                      className="p-1 rounded hover:bg-muted text-muted-foreground hover:text-emerald-400 transition-colors"
                    >
                      <Download className="size-3.5" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!loading && summary && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 bg-card border border-border rounded-xl p-5 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Activity className="h-5 w-5 text-emerald-500" />
              <div>
                <p className="text-sm font-medium text-foreground">Ingestion Status</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {summary.files.ok.length} ok · {summary.files.skipped.length} skipped ·{" "}
                  {summary.files.errors.length} errors
                </p>
              </div>
            </div>
            <div className="text-right">
              <p className="text-xs text-muted-foreground">Last ingested</p>
              <p className="text-sm font-mono text-foreground">
                {summary.last_ingested ? summary.last_ingested.replace("T", " ").slice(0, 19) : "never"}
              </p>
            </div>
          </div>
          <div className="bg-card border border-border rounded-xl p-5">
            <div className="flex items-center gap-2 mb-3">
              <FileText className="h-4 w-4 text-emerald-500" />
              <h3 className="text-sm font-semibold text-foreground">Dataset Split</h3>
            </div>
            <div className="space-y-2 text-sm">
              {[
                ["Bank records", summary.bank_records],
                ["CDR records", summary.cdr_records],
                ["IPDR records", summary.ipdr_records],
                ["NCRP complaints", summary.complaints],
              ].map(([label, n]) => (
                <div key={label as string} className="flex justify-between text-muted-foreground">
                  <span>{label}</span>
                  <span className="font-mono text-foreground">{(n as number).toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {!loading && summary && copilot && (
        <div className="bg-card border border-border rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <Network className="h-4 w-4 text-emerald-500" />
            <h3 className="text-sm font-semibold text-foreground">Co-Pilot Knowledge Graph</h3>
            <span className="text-xs text-muted-foreground ml-1">
              {copilot.dataset_source} · max {copilot.max_graph_hops} hops
            </span>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3 text-sm">
            {[
              ["Bank txns", copilot.tables.bank_transactions],
              ["CDR calls", copilot.tables.cdr_records],
              ["IPDR sessions", copilot.tables.ipdr_records],
              ["Bank↔CDR links", copilot.tables.bank_cdr_links],
              ["CDR↔IPDR links", copilot.tables.cdr_ipdr_links],
              ["Anomalies", copilot.tables.anomaly_records],
              ["Subscribers", copilot.tables.subscribers],
              ["Graph nodes", copilot.graph_nodes],
            ].map(([label, n]) => (
              <div key={label as string}>
                <p className="text-xs text-muted-foreground">{label}</p>
                <p className="font-mono font-semibold text-foreground">{(n as number).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
});
