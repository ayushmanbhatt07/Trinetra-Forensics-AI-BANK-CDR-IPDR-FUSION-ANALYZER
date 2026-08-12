"use client";

/**
 * Ripple effect for clickable elements (Animate UI "RippleButton" blend).
 * A span of expanding rings is appended on pointer-down and removed by
 * React when the animation ends. Pure CSS keyframes, zero dependencies.
 */
import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export interface Ripple {
  id: number;
  x: number;
  y: number;
  size: number;
}

function createRipples(
  rect: DOMRect,
  clientX: number,
  clientY: number,
  ripples: Ripple[],
  nextId: React.MutableRefObject<number>
): Ripple[] {
  const size = Math.max(rect.width, rect.height) * 2.4;
  const x = clientX - rect.left - size / 2;
  const y = clientY - rect.top - size / 2;
  return [...ripples, { id: nextId.current++, x, y, size }];
}

/**
 * Renders the ripple spans for a given ripples array.
 * Drop <RippleRipples ripples={ripples} onRippleEnd={removeRipple} /> inside
 * the trigger element. onRippleEnd removes the ripple from React state when
 * its animation completes, so React unmounts the node itself (imperative
 * DOM removal would desync React's reconciler and crash on the next render).
 */
export function RippleRipples({
  ripples,
  onRippleEnd,
  className,
}: {
  ripples: Ripple[];
  onRippleEnd?: (id: number) => void;
  className?: string;
}) {
  return (
    <>
      {ripples.map((r) => (
        <span
          key={r.id}
          data-ripple
          className={cn(
            "ripple-ring pointer-events-none absolute rounded-full",
            className
          )}
          style={{
            left: r.x,
            top: r.y,
            width: r.size,
            height: r.size,
          }}
          onAnimationEnd={(e) => {
            if (e.target === e.currentTarget) onRippleEnd?.(r.id);
          }}
        />
      ))}
    </>
  );
}

/**
 * Hook that attaches a ripple stream to any element. Returns
 * [onPointerDown handler, ripples array, removeRipple] — spread the handler
 * onto your element and render <RippleRipples ripples={ripples}
 * onRippleEnd={removeRipple} /> inside it.
 */
export function useRipples(disabled = false) {
  const [ripples, setRipples] = useState<Ripple[]>([]);
  const nextId = useRef(0);

  const onPointerDown = useCallback(
    (event: React.PointerEvent<HTMLElement>) => {
      if (disabled || event.button !== 0) return;
      const el = event.currentTarget;
      if (!el) return;
      setRipples((prev) =>
        createRipples(el.getBoundingClientRect(), event.clientX, event.clientY, prev, nextId)
      );
    },
    [disabled]
  );

  const removeRipple = useCallback((id: number) => {
    setRipples((prev) => prev.filter((r) => r.id !== id));
  }, []);

  return [onPointerDown, ripples, removeRipple] as const;
}
