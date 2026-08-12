"use client";

import { cn } from "@/lib/utils";
import { ArrowUpRight, Clock, CheckCircle2, XCircle } from "lucide-react";

const anomalies = [
  {
    entity: "Target-Alpha (E213)",
    risk: "98.5",
    status: "critical",
    date: "2 hours ago",
    type: "Smurfing",
  },
  {
    entity: "Node-Sigma (IP: 192.x)",
    risk: "85.2",
    status: "high",
    date: "5 hours ago",
    type: "Burner Phone",
  },
  {
    entity: "Acct-9921",
    risk: "75.0",
    status: "high",
    date: "1 day ago",
    type: "Round Dollar",
  },
  {
    entity: "Unknown Caller (0911)",
    risk: "45.8",
    status: "medium",
    date: "2 days ago",
    type: "Late Night",
  },
  {
    entity: "Target-Beta (E441)",
    risk: "92.1",
    status: "critical",
    date: "3 days ago",
    type: "Fast Funds",
  },
];

const statusConfig = {
  critical: {
    icon: XCircle,
    color: "text-destructive",
    bg: "bg-destructive/10",
    label: "Critical",
  },
  high: {
    icon: Clock,
    color: "text-warning",
    bg: "bg-warning/10",
    label: "High Risk",
  },
  medium: {
    icon: CheckCircle2,
    color: "text-success",
    bg: "bg-success/10",
    label: "Medium Risk",
  },
};

export function RecentDeals() {
  return (
    <div className="bg-card border border-border rounded-xl p-5 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-200">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-base font-semibold text-foreground">Recent Anomalies</h3>
          <p className="text-sm text-muted-foreground mt-0.5">Latest high-risk detections</p>
        </div>
        <button className="flex items-center gap-1 text-sm text-accent hover:text-accent/80 font-medium transition-colors group">
          View all
          <ArrowUpRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
        </button>
      </div>

      <div className="space-y-3">
        {anomalies.map((anomaly, index) => {
          const status = statusConfig[anomaly.status as keyof typeof statusConfig];
          const StatusIcon = status.icon;

          return (
            <div
              key={anomaly.entity}
              className="group flex items-center justify-between p-3 rounded-lg hover:bg-secondary/50 transition-all duration-200 cursor-pointer animate-in fade-in slide-in-from-left-2"
              style={{ animationDelay: `${(index + 3) * 100}ms`, animationFillMode: "both" }}
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-secondary flex items-center justify-center text-sm font-semibold text-muted-foreground group-hover:bg-accent/10 group-hover:text-accent transition-all duration-200">
                  {anomaly.entity.charAt(0)}
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{anomaly.entity}</p>
                  <p className="text-xs text-muted-foreground">{anomaly.type} • {anomaly.date}</p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <span className="text-sm font-semibold text-foreground">Score: {anomaly.risk}</span>
                <div className={cn("flex items-center gap-1 px-2 py-1 rounded-md text-xs font-medium", status.bg, status.color)}>
                  <StatusIcon className="w-3 h-3" />
                  {status.label}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
