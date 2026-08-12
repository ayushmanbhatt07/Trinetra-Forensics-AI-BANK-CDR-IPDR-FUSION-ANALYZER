"use client";

import { AlertOctagon, Activity } from "lucide-react";

const entities = [
  { name: "Unknown Network", transactions: 24, volume: "$487,500", change: "+15%", rank: 1 },
  { name: "John Doe (E42)", transactions: 19, volume: "$356,200", change: "+8%", rank: 2 },
  { name: "Shell Corp Ltd", transactions: 17, volume: "$312,800", change: "+12%", rank: 3 },
  { name: "Offshore Trust", transactions: 15, volume: "$289,400", change: "+5%", rank: 4 },
  { name: "Crypto Exchange A", transactions: 14, volume: "$267,100", change: "+9%", rank: 5 },
];

export function TopPerformers() {
  return (
    <div className="bg-card border border-border rounded-xl p-5 animate-in fade-in slide-in-from-bottom-4 duration-500 delay-300">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-base font-semibold text-foreground">Highest Risk Entities</h3>
          <p className="text-sm text-muted-foreground mt-0.5">Top flags by volume & connections</p>
        </div>
        <div className="flex items-center gap-1 text-destructive">
          <AlertOctagon className="w-5 h-5" />
        </div>
      </div>

      <div className="space-y-3">
        {entities.map((entity, index) => (
          <div
            key={entity.name}
            className="group flex items-center justify-between p-3 rounded-lg hover:bg-secondary/50 transition-all duration-200 cursor-pointer animate-in fade-in slide-in-from-right-2"
            style={{ animationDelay: `${(index + 4) * 100}ms`, animationFillMode: "both" }}
          >
            <div className="flex items-center gap-3">
              <div className="relative">
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-destructive/80 to-chart-4 flex items-center justify-center text-sm font-semibold text-destructive-foreground">
                  {entity.name.split(" ").map((n) => n[0]).join("").substring(0,2)}
                </div>
                {entity.rank <= 3 && (
                  <div className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-destructive text-[10px] font-bold flex items-center justify-center text-destructive-foreground">
                    {entity.rank}
                  </div>
                )}
              </div>
              <div>
                <p className="text-sm font-medium text-foreground">{entity.name}</p>
                <p className="text-xs text-muted-foreground">{entity.transactions} flagged txns</p>
              </div>
            </div>

            <div className="text-right">
              <p className="text-sm font-semibold text-foreground">{entity.volume}</p>
              <div className="flex items-center justify-end gap-1 text-xs text-destructive">
                <Activity className="w-3 h-3" />
                {entity.change}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
