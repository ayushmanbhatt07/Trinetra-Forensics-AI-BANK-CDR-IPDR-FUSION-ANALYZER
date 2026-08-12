// eslint-disable-next-line @typescript-eslint/ban-ts-comment -- demo chart component
// @ts-nocheck
"use client";

import { useState, useEffect } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

const data = [
  { month: "Jan", flagged: 1860, reviewed: 1800 },
  { month: "Feb", flagged: 2050, reviewed: 1900 },
  { month: "Mar", flagged: 2370, reviewed: 2000 },
  { month: "Apr", flagged: 2730, reviewed: 2200 },
  { month: "May", flagged: 2090, reviewed: 2300 },
  { month: "Jun", flagged: 3140, reviewed: 2500 },
  { month: "Jul", flagged: 3520, reviewed: 2700 },
  { month: "Aug", flagged: 3890, reviewed: 2900 },
  { month: "Sep", flagged: 4210, reviewed: 3100 },
  { month: "Oct", flagged: 4580, reviewed: 3300 },
  { month: "Nov", flagged: 4920, reviewed: 3500 },
  { month: "Dec", flagged: 5470, reviewed: 3800 },
];

export function RevenueChart() {
  const [isLoaded, setIsLoaded] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setIsLoaded(true), 300);
    return () => clearTimeout(timer);
  }, []);

  return (
    <div className="bg-card border border-border rounded-xl p-5 h-[380px] animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-base font-semibold text-foreground">Anomaly Detection Trend</h3>
          <p className="text-sm text-muted-foreground mt-0.5">Flagged vs Reviewed Transactions</p>
        </div>
        <div className="flex items-center gap-4 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-chart-1" />
            <span className="text-muted-foreground">Flagged</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-chart-2" />
            <span className="text-muted-foreground">Reviewed</span>
          </div>
        </div>
      </div>

      <div className={`h-[280px] transition-opacity duration-700 ${isLoaded ? 'opacity-100' : 'opacity-0'}`}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="flaggedGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="oklch(0.7 0.18 220)" stopOpacity={0.4} />
                <stop offset="100%" stopColor="oklch(0.7 0.18 220)" stopOpacity={0} />
              </linearGradient>
              <linearGradient id="reviewedGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="oklch(0.7 0.18 145)" stopOpacity={0.3} />
                <stop offset="100%" stopColor="oklch(0.7 0.18 145)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.22 0.005 260)" vertical={false} />
            <XAxis
              dataKey="month"
              axisLine={false}
              tickLine={false}
              tick={{ fill: "oklch(0.65 0 0)", fontSize: 12 }}
              dy={10}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              tick={{ fill: "oklch(0.65 0 0)", fontSize: 12 }}
              dx={-10}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "oklch(0.12 0.005 260)",
                border: "1px solid oklch(0.22 0.005 260)",
                borderRadius: "8px",
                fontSize: "12px",
              }}
              labelStyle={{ color: "oklch(0.95 0 0)", fontWeight: 600 }}
              itemStyle={{ color: "oklch(0.65 0 0)" }}
            />
            <Area
              type="monotone"
              dataKey="reviewed"
              stroke="oklch(0.7 0.18 145)"
              strokeWidth={2}
              fill="url(#reviewedGradient)"
              dot={false}
            />
            <Area
              type="monotone"
              dataKey="flagged"
              stroke="oklch(0.7 0.18 220)"
              strokeWidth={2}
              fill="url(#flaggedGradient)"
              dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
