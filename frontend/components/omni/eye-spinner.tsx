"use client";

/**
 * Full-screen analysis loader for the Tri-Netra Forensics "search" moment:
 * a pulsing OmniEye inside an expanding radar ring, over a dimmed,
 * blurred backdrop. Replaces the globe-to-map transition.
 */
import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export function EyeSpinner({
  onDone,
  durationMs = 1400,
}: {
  onDone?: () => void;
  durationMs?: number;
}) {
  const [phase, setPhase] = useState<"scanning" | "linking" | "done">("scanning");
  const doneRef = useRef(false);

  useEffect(() => {
    const t1 = window.setTimeout(() => setPhase("linking"), Math.floor(durationMs * 0.5));
    const t2 = window.setTimeout(() => setPhase("done"), durationMs);
    const t3 = window.setTimeout(() => {
      if (!doneRef.current) {
        doneRef.current = true;
        onDone?.();
      }
    }, durationMs + 220);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
    };
  }, [durationMs, onDone]);

  const label =
    phase === "done"
      ? "linked"
      : phase === "linking"
        ? "linking evidence…"
        : "scanning bank · CDR · IPDR…";

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
      className="fixed inset-0 z-[75] grid place-items-center bg-black/60 backdrop-blur-md"
      aria-label="Analysing the loaded corpus"
    >
      <div className="relative grid size-52 place-items-center">
        {/* radar rings */}
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="absolute inset-0 rounded-full border border-cyan-500/40"
            animate={{ scale: [1, 1.9], opacity: [0.5, 0] }}
            transition={{
              duration: 1.8,
              repeat: Infinity,
              delay: i * 0.6,
              ease: "easeOut",
            }}
          />
        ))}
        {/* rotating arc */}
        <motion.span
          className="absolute inset-4 rounded-full border-2 border-transparent border-t-cyan-400 border-r-violet-500/70"
          animate={{ rotate: 360 }}
          transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
        />
        <div className="grid size-28 place-items-center">
        </div>
        <p className="absolute top-full mt-5 w-max font-mono text-xs uppercase tracking-[0.25em] text-cyan-300">
          {label}
        </p>
      </div>
    </motion.div>
  );
}
