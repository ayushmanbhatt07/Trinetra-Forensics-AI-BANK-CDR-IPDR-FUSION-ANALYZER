"use client";

/**
 * Radial Intro (Animate UI blend) — items fly in from a hidden center and
 * settle into a slowly rotating orbit. Used by the Network section when a
 * money-flow cycle is detected ("when a NetworkX cycle comes into the
 * picture").
 */
import { useMemo } from "react";
import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";

export interface OrbitItem {
  id: string;
  label: string;
  icon?: LucideIcon;
  accent?: string;
}

export function RadialIntro({
  items,
  stageSize = 340,
  chipSize = 64,
  duration = 26,
  replayKey,
}: {
  items: OrbitItem[];
  stageSize?: number;
  chipSize?: number;
  duration?: number;
  replayKey?: string | number;
}) {
  const orbit = useMemo(() => {
    const r = stageSize / 2 - chipSize / 2 - 12;
    return items.map((item, i) => {
      const angle = (i / Math.max(items.length, 1)) * 2 * Math.PI;
      return {
        ...item,
        x: Math.cos(angle) * r,
        y: Math.sin(angle) * r,
        delay: i * 0.12,
      };
    });
  }, [items, stageSize, chipSize]);

  if (items.length === 0) return null;

  return (
    <div
      className="relative grid place-items-center"
      style={{ width: stageSize, height: stageSize }}
    >
      {/* pulsing core */}
      <div className="absolute grid place-items-center">
        <div className="absolute size-24 rounded-full border border-cyan-400/30 bg-cyan-500/10 blur-md" />
        <div className="absolute size-16 animate-pulse rounded-full border border-cyan-400/50 bg-cyan-500/15" />
        <span className="font-mono text-[10px] uppercase tracking-[0.3em] text-cyan-300">
          {items.length}·CYCLE
        </span>
      </div>

      {/* orbit ring */}
      <div
        key={replayKey}
        className="radial-intro-orbit absolute inset-0"
        style={{ "--orbit-duration": `${duration}s` } as React.CSSProperties}
      >
        {orbit.map((item) => (
          <div
            key={item.id}
            className="absolute"
            style={{
              left: stageSize / 2 + item.x - chipSize / 2,
              top: stageSize / 2 + item.y - chipSize / 2,
              width: chipSize,
              height: chipSize,
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0, y: 24 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{
                delay: item.delay,
                type: "spring",
                stiffness: 260,
                damping: 20,
              }}
              className="radial-intro-item flex h-full w-full flex-col items-center justify-center gap-0.5 rounded-full border border-border bg-card/80 text-center backdrop-blur-sm"
              style={{ boxShadow: `0 0 18px ${item.accent ?? "#22d3ee"}33` }}
              title={item.label}
            >
              {item.icon ? (
                <item.icon className="size-4" style={{ color: item.accent ?? "#67e8f9" }} />
              ) : (
                <span className="size-1.5 rounded-full" style={{ background: item.accent ?? "#67e8f9" }} />
              )}
              <span className="max-w-full truncate px-1 font-mono text-[8px] text-foreground/80">
                {item.label}
              </span>
            </motion.div>
          </div>
        ))}
      </div>
    </div>
  );
}
