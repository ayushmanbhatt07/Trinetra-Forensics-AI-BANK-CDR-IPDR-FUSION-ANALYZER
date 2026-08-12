"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Server, Database, Trash2, RefreshCw, Loader2 } from "lucide-react";
import { api, type IngestStatus } from "@/lib/api";
import { toast } from "sonner";

export function SettingsSection() {
  const [status, setStatus] = useState<IngestStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);

  const load = () => {
    api
      .status()
      .then(setStatus)
      .catch(() => toast.error("Backend unreachable. Is the API running?"))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const clearData = async () => {
    setClearing(true);
    try {
      await api.clearData();
      toast.success("Bundle cleared. Re-run ingestion to load data.");
      load();
    } catch {
      toast.error("Failed to clear data.");
    } finally {
      setClearing(false);
    }
  };

  const serverUp = status !== null;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-semibold text-foreground">System Settings</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Backend status, ingestion state and data management
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <Server className="h-5 w-5 text-emerald-500" />
            <CardTitle>Backend Health</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${serverUp ? "bg-emerald-500" : "bg-red-500"} animate-pulse`} />
              <span className="text-sm text-foreground">
                {loading ? "Checking..." : serverUp ? "API reachable" : "API unreachable"}
              </span>
              {status && (
                <Badge variant="outline" className="text-xs">
                  {status.loaded ? "DATA LOADED" : "EMPTY"}
                </Badge>
              )}
            </div>
            <Button variant="outline" size="sm" onClick={() => { setLoading(true); load(); }} disabled={loading}>
              <RefreshCw className={`mr-2 h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-2">
            <Database className="h-5 w-5 text-amber-500" />
            <CardTitle>Loaded Bundle</CardTitle>
            <CardDescription>SQLite-persisted on the server</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {status ? (
              <>
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {[
                    ["Bank records", status.bank],
                    ["CDR records", status.cdr],
                    ["IPDR records", status.ipdr],
                    ["NCRP complaints", status.complaints],
                  ].map(([label, n]) => (
                    <div key={label as string} className="flex justify-between text-muted-foreground">
                      <span>{label}</span>
                      <span className="font-mono text-foreground">{(n as number).toLocaleString()}</span>
                    </div>
                  ))}
                </div>
                <div className="text-xs text-muted-foreground">
                  Files: {status.files_ok} ok · {status.files_skipped} skipped · {status.errors.length} errors
                </div>
                {status.errors.length > 0 && (
                  <ScrollArea className="h-24 rounded-lg bg-muted/40 p-2 border border-border">
                    {status.errors.map((e, i) => (
                      <p key={i} className="font-mono text-xs text-red-400 mb-1">
                        {e}
                      </p>
                    ))}
                  </ScrollArea>
                )}
                <div className="text-xs text-muted-foreground">
                  Last ingested: {status.last_ingested ? status.last_ingested.replace("T", " ").slice(0, 19) : "never"}
                </div>
                <Button variant="destructive" size="sm" onClick={clearData} disabled={clearing || !status.loaded}>
                  {clearing ? (
                    <>
                      <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />
                      Clearing...
                    </>
                  ) : (
                    <>
                      <Trash2 className="mr-2 h-3.5 w-3.5" />
                      Clear All Data
                    </>
                  )}
                </Button>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Backend offline.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
