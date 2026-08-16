"use client";

import React, { useRef, useState, useEffect } from "react";
import { ResponsiveContainer } from "recharts";

interface SafeChartContainerProps {
  width?: string | number;
  height?: string | number;
  minHeight?: number;
  className?: string;
  children: React.ReactNode;
}

/**
 * Layout-aware chart container that uses ResizeObserver to ensure Recharts
 * components are ONLY mounted when their parent container has measurable,
 * non-zero dimensions (> 0x0).
 *
 * This completely eliminates the Recharts "The width(0) and height(0) of chart should be greater than 0"
 * warnings when dashboard sections are mounted in background/hidden (display: none) tabs.
 */
export const SafeChartContainer = React.memo(function SafeChartContainer({
  width = "100%",
  height = "100%",
  minHeight,
  className,
  children,
}: SafeChartContainerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isMeasurable, setIsMeasurable] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const checkSize = () => {
      const rect = el.getBoundingClientRect();
      const hasSize = rect.width > 0 && rect.height > 0 && el.offsetWidth > 0 && el.offsetHeight > 0;
      setIsMeasurable(hasSize);
    };

    checkSize();

    if (typeof ResizeObserver !== "undefined") {
      const ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width: w, height: h } = entry.contentRect;
          setIsMeasurable(w > 0 && h > 0);
        }
      });
      ro.observe(el);
      return () => ro.disconnect();
    }
  }, []);

  return (
    <div
      ref={containerRef}
      className={className ?? "w-full h-full min-w-0 min-h-0"}
      style={minHeight ? { minHeight } : undefined}
    >
      {isMeasurable ? (
        <ResponsiveContainer width={width as any} height={height as any}>
          {children as any}
        </ResponsiveContainer>
      ) : null}
    </div>
  );
});
