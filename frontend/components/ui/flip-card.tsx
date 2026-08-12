"use client";

/**
 * Flip KPI Card (Animate UI blend) — 3D flip on hover; front carries the
 * headline metric, back reveals details on a blurred backdrop with a
 * copy button for the full card contents.
 */
import type { LucideIcon } from "lucide-react";import { TrendingUp, TrendingDown, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";
import { CopyButton } from "@/components/ui/copy-button";

export interface FlipCardData {
  title: string;
  value: string;
  change: string;
  changeType: "positive" | "negative" | "neutral";
  icon: LucideIcon;
  accent?: string;
  details: { label: string; value: string }[];
  copyText: string;
  delay?: number;
}

export function FlipKpiCard({ data }: { data: FlipCardData }) {
  const Icon = data.icon;

  return (
    <div
      className="flip-card group relative h-40 [perspective:1200px]"
      style={{
        animationDelay: `${(data.delay ?? 0) * 100}ms`,
        animationFillMode: "both",
      }}
    >
      <div className="flip-card-inner relative h-full w-full">
        {/* ------- FRONT ------- */}
        <div className="flip-face absolute inset-0 rounded-xl border border-border bg-card p-5 transition-colors duration-300 group-hover:border-accent/50">
          <div className="flex items-start justify-between mb-3">
            <span className="text-sm text-muted-foreground font-medium">
              {data.title}
            </span>
            <div className="w-9 h-9 rounded-lg bg-secondary flex items-center justify-center group-hover:bg-accent/10 transition-colors duration-300">
              <Icon className="w-4 h-4 text-muted-foreground group-hover:text-accent transition-colors duration-300" />
            </div>
          </div>
          <div className="flex items-end gap-3">
            <span className="text-2xl lg:text-3xl font-bold text-foreground tracking-tight">
              {data.value}
            </span>
            <div
              className={cn(
                "flex items-center gap-1 text-sm font-medium mb-1",
                data.changeType === "positive" && "text-success",
                data.changeType === "negative" && "text-destructive",
                data.changeType === "neutral" && "text-muted-foreground"
              )}
            >
              {data.changeType === "positive" && (
                <TrendingUp className="w-3.5 h-3.5" />
              )}
              {data.changeType === "negative" && (
                <TrendingDown className="w-3.5 h-3.5" />
              )}
              <span>{data.change}</span>
            </div>
          </div>
          <div className="absolute bottom-3 right-3 flex items-center gap-1 text-[10px] text-muted-foreground/60 opacity-0 transition-opacity duration-300 group-hover:opacity-100">
            <RefreshCw className="size-3" /> hover for details
          </div>
        </div>

        {/* ------- BACK (blurred backdrop) ------- */}
        <div className="flip-back flip-face absolute inset-0 overflow-hidden rounded-xl border border-accent/40 bg-background/70 backdrop-blur-xl p-5 shadow-lg shadow-black/40">
          <div
            className="absolute inset-0 -z-0 opacity-25"
            style={{
              background: `radial-gradient(circle at 85% 15%, ${data.accent ?? "oklch(0.7 0.18 145)"}66, transparent 55%)`,
            }}
          />
          <div className="relative flex h-full flex-col">
            <div className="flex items-center justify-between">
              <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                {data.title}
              </p>
              <Icon className="size-4" style={{ color: data.accent ?? "oklch(0.7 0.18 145)" }} />
            </div>
            <div className="mt-3 flex-1 space-y-1.5 overflow-hidden">
              {data.details.map((d) => (
                <div
                  key={d.label}
                  className="flex items-center justify-between gap-2 text-xs"
                >
                  <span className="text-muted-foreground">{d.label}</span>
                  <span className="font-mono font-semibold text-foreground truncate">
                    {d.value}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-2 flex justify-end">
              <CopyButton content={data.copyText} label="Copy card" variant="outline" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
