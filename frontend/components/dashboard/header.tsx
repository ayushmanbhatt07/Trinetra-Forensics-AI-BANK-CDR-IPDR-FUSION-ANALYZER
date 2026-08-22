"use client";

import React, { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { cn } from "@/lib/utils";
export type Section = "dashboard" | "ingestion" | "network" | "fused" | "anomalies" | "timeline" | "reports" | "settings" | "search";
import { LogOut, Settings } from "lucide-react";
import { useAuth } from "@/lib/auth";

import { AccountDialog } from "@/components/dashboard/account-dialog";

interface HeaderProps {
  activeSection: Section;
}

const sectionTitles: Record<Section, string> = {
  dashboard: "Overview",
  ingestion: "Data Ingestion",
  network: "Network Graph",
  fused: "Fused Transactions",
  anomalies: "Anomaly Detection",
  timeline: "Timeline",
  reports: "Reports",
  settings: "Settings",
  search: "Entity Search",
};

export const Header = React.memo(function Header({ activeSection }: HeaderProps) {
  const { user, logout } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const initials = (user?.username ?? "?")
    .split(/[._-]/)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .slice(0, 2)
    .join("");

  return (
    <header className="h-16 border-b border-border bg-background/80 backdrop-blur-sm sticky top-0 z-30 flex items-center justify-between px-6">
      <div className="flex items-center gap-6">
        <Link
          href="/"
          title="Tri-Netra Forensics — go to frontend"
          aria-label="Tri-Netra Forensics home"
          className="group flex items-center gap-2.5 transition-transform duration-200 hover:scale-105"
        >
          <Image
            src="/logo.jpg"
            alt=""
            width={36}
            height={36}
            className="size-9 rounded-lg border border-cyan-500/30 object-cover shadow-md shadow-cyan-950/40 ring-1 ring-cyan-500/20 transition-shadow group-hover:shadow-cyan-900/60"
          />
          <span className="hidden font-mono text-sm font-bold tracking-widest text-foreground sm:inline">
            TRI-NETRA FORENSICS
          </span>
        </Link>
        <h1 className="text-xl font-semibold text-foreground">
          {sectionTitles[activeSection]}
        </h1>
        <div className="hidden md:flex items-center gap-2 text-sm text-muted-foreground">
          <span className="font-mono text-xs text-muted-foreground/70">
            {user ? `${user.username} · ${user.role.toUpperCase()}` : ""}
          </span>
        </div>
      </div>

      <div className="flex items-center gap-4">

        {/* User + logout */}
        <div className="flex items-center gap-3 pl-3 border-l border-border">
          <div className="flex flex-col items-end leading-tight">
            <span className="text-sm font-medium text-foreground">{user?.username}</span>
            <span
              className={cn(
                "text-[10px] uppercase tracking-widest font-mono",
                user?.role === "admin" ? "text-emerald-500" : "text-muted-foreground"
              )}
            >
              {user?.role}
            </span>
          </div>
          <div className="w-9 h-9 rounded-lg overflow-hidden bg-secondary ring-2 ring-transparent">
            <div className="w-full h-full bg-gradient-to-br from-emerald-500/80 to-cyan-500 flex items-center justify-center text-xs font-semibold text-black">
              {initials}
            </div>
          </div>
          <button
            onClick={() => setSettingsOpen(true)}
            title="Account settings"
            className="w-9 h-9 flex items-center justify-center rounded-lg text-muted-foreground hover:text-foreground hover:bg-secondary transition-all duration-200"
          >
            <Settings className="w-5 h-5" />
          </button>
          <button
            onClick={logout}
            title="Sign out"
            className="w-9 h-9 flex items-center justify-center rounded-lg text-muted-foreground hover:text-red-400 hover:bg-secondary transition-all duration-200"
          >
            <LogOut className="w-5 h-5" />
          </button>
        </div>
      </div>
      <AccountDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </header>
  );
});
