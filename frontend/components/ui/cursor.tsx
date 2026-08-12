"use client";

/**
 * Tri-Netra Forensics cursor layer — works ALONGSIDE the global Animate UI Cursor.
 * - Global (non-interactive areas): handled by the real Animate UI
 *   Cursor + CursorFollow ("Designer") mounted in the root layout.
 * - Over clickable elements (a, button, inputs, ...): this provider
 *   shows the Tri-Netra Forensics glow cursor (cyan dot + trailing spring ring
 *   + "OMNI" pill) instead.
 */
import { useEffect, useState } from "react";
import { motion, useMotionValue, useSpring } from "framer-motion";
import { cn } from "@/lib/utils";

export function CursorProvider({
  children,
  label = "OMNI",
}: {
  children?: React.ReactNode;
  label?: string;
}) {
  const [enabled, setEnabled] = useState(false);
  const [hoveringInteractive, setHoveringInteractive] = useState(false);
  const [visible, setVisible] = useState(false);
  const x = useMotionValue(-100);
  const y = useMotionValue(-100);
  const ringX = useSpring(x, { stiffness: 500, damping: 50, bounce: 0 });
  const ringY = useSpring(y, { stiffness: 500, damping: 50, bounce: 0 });
  const [pressed, setPressed] = useState(false);

  useEffect(() => {
    const fine = window.matchMedia?.("(pointer: fine)").matches ?? false;
    if (!fine) return; // touch devices keep the native cursor
    document.documentElement.classList.add("omni-cursor-active");

    const onMove = (e: MouseEvent) => {
      x.set(e.clientX);
      y.set(e.clientY);
      setEnabled(true);
      setVisible(true);
    };
    const onLeave = () => setVisible(false);
    const onDown = () => setPressed(true);
    const onUp = () => setPressed(false);
    const onOver = (e: MouseEvent) => {
      const t = e.target as HTMLElement;
      setHoveringInteractive(
        !!t.closest(
          "a, button, [role=button], input, textarea, select, [data-cursor-hover]"
        )
      );
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    document.documentElement.addEventListener("mouseleave", onLeave);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);
    window.addEventListener("mouseover", onOver, { passive: true });
    return () => {
      document.documentElement.classList.remove("omni-cursor-active");
      window.removeEventListener("mousemove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      window.removeEventListener("mouseover", onOver);
    };
  }, [x, y]);

  if (!enabled) return <>{children}</>;

  return (
    <>
      {children}

      {/* OMNI glow cursor — only over clickable elements */}
      <motion.div
        aria-hidden
        className="pointer-events-none fixed left-0 top-0 z-[100] size-1.5 rounded-full bg-cyan-300 shadow-[0_0_8px_rgba(103,232,249,0.9)]"
        style={{
          x,
          y,
          translateX: "-50%",
          translateY: "-50%",
          opacity: visible && hoveringInteractive ? 1 : 0,
          scale: hoveringInteractive ? (pressed ? 0.6 : 1) : 0.4,
        }}
      />
      <motion.div
        aria-hidden
        className="pointer-events-none fixed left-0 top-0 z-[99] size-8 rounded-full border border-cyan-400/40"
        style={{
          x: ringX,
          y: ringY,
          translateX: "-50%",
          translateY: "-50%",
          opacity: visible && hoveringInteractive ? 1 : 0,
          scale: hoveringInteractive ? 1 : 0.7,
        }}
      >
        <div
          className={cn(
            "absolute inset-0 grid place-items-center rounded-full transition-opacity duration-200",
            hoveringInteractive ? "opacity-100" : "opacity-0"
          )}
        >
          <span className="rounded-full bg-cyan-500/15 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.2em] text-cyan-300 backdrop-blur-sm">
            {label}
          </span>
        </div>
      </motion.div>
    </>
  );
}
