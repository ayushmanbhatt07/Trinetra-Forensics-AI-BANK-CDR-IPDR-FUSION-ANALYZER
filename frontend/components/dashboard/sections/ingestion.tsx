"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { FileUp, Database, FileText, PhoneCall, CheckCircle, Loader2, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { motion, AnimatePresence } from "framer-motion";
import { api } from "@/lib/api";
import { usePipeline } from "@/lib/pipeline-context";

export function IngestionSection() {
  const { refetchPipeline } = usePipeline();
  const [files, setFiles] = useState<File[]>([]);
  const [folder, setFolder] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isFolderIngesting, setIsFolderIngesting] = useState(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const newFiles = Array.from(e.target.files);
      if (files.length + newFiles.length > 6) {
        toast.error("Maximum 6 files allowed.");
        return;
      }
      setFiles((prev) => [...prev, ...newFiles]);
    }
  };

  const handleFusionPipeline = async () => {
    if (files.length === 0) {
      toast.error("Please select at least one Bank statement, CDR, or IPDR file.");
      return;
    }
    setIsUploading(true);
    try {
      const data = await api.uploadFiles(files);
      await refetchPipeline();
      toast.success(`Ingestion started! Parsing ${data.files.length} datasets.`);
      if (data.errors.length > 0) {
        toast.error(`Skipped ${data.skipped.length} files · errors: ${data.errors.join("; ").slice(0, 200)}`);
      }
      setFiles([]);
      window.dispatchEvent(new CustomEvent("nav:section", { detail: "fused" }));
    } catch (error) {
      toast.error(`Error: ${error instanceof Error ? error.message : "Upload failed"}`);
    } finally {
      setIsUploading(false);
    }
  };

  const handleFolderIngest = async () => {
    if (!folder.trim()) {
      toast.error("Enter the server-side folder path (e.g. /data/police_case).");
      return;
    }
    setIsFolderIngesting(true);
    try {
      const data = await api.ingestFolder(folder.trim());
      await refetchPipeline();
      toast.success(`Folder ingested: ${data.files_ok} files ok`);
      if (data.errors.length) toast.error(`Errors: ${data.errors.slice(0, 3).join("; ")}`);
      window.dispatchEvent(new CustomEvent("nav:section", { detail: "fused" }));
    } catch (error) {
      toast.error(`Error: ${error instanceof Error ? error.message : "Folder ingest failed"}`);
    } finally {
      setIsFolderIngesting(false);
    }
  };


  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <Card className="col-span-full border-dashed border-2 bg-muted/20 hover:bg-muted/40 transition-colors">
          <CardContent className="flex flex-col items-center justify-center h-56 relative">
            <input
              type="file"
              multiple
              onChange={handleFileChange}
              className="absolute inset-0 opacity-0 cursor-pointer"
            />
            <FileUp className="h-12 w-12 text-emerald-500 mb-4 animate-pulse" />
            <h3 className="text-lg font-semibold text-foreground">Upload Datasets (Drop Files Here)</h3>
            <p className="text-sm text-muted-foreground mt-2 max-w-sm text-center">
              Bank Statements (PDF/CSV/XLSX), Telecom Call Detail Records (CDR), and IP Data Records (IPDR). Max 6 files.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-2 max-w-xl">
              <AnimatePresence>
                {files.map((f, i) => (
                  <motion.div
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    key={i}
                    className="bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 px-3 py-1 rounded-full text-xs font-mono flex items-center gap-2"
                  >
                    <CheckCircle className="w-3 h-3" />
                    {f.name}
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
            {files.length === 0 && (
              <Button className="mt-4 pointer-events-none" variant="secondary">Browse Files</Button>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Bank Statements</CardTitle>
            <FileText className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{files.filter(f => f.name.toLowerCase().includes('bank') || f.name.toLowerCase().endsWith('pdf') || f.name.toLowerCase().endsWith('xlsx')).length} files</div>
            <p className="text-xs text-muted-foreground mt-1">Ready for parsing</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Call Detail Records</CardTitle>
            <PhoneCall className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{files.filter(f => f.name.toLowerCase().includes('cdr') || f.name.toLowerCase().includes('call')).length} files</div>
            <p className="text-xs text-muted-foreground mt-1">Ready for correlation</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">IP Detail Records</CardTitle>
            <Database className="h-4 w-4 text-emerald-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{files.filter(f => f.name.toLowerCase().includes('ipdr')).length} files</div>
            <p className="text-xs text-muted-foreground mt-1">Ready for mapping</p>
          </CardContent>
        </Card>
      </div>

      <div className="flex justify-end gap-3">
        <Button
          size="lg"
          onClick={handleFusionPipeline}
          disabled={isUploading || files.length === 0}
          className="bg-emerald-600 hover:bg-emerald-700 text-white shadow-[0_0_15px_rgba(16,185,129,0.3)] border border-emerald-500/50 holographic-border transition-all"
        >
          {isUploading ? (
            <>
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              Fusing Datasets...
            </>
          ) : (
            "BEGIN FUSION PIPELINE"
          )}

        </Button>
      </div>
    </div>
  );
}
