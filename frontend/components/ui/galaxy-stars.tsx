"use client";

/**
 * Interactive gravity-stars background (permanent, all pages).
 * Canvas-based: stars drift upward, are attracted/repelled by the mouse,
 * twinkle via radial glow, and gently connect into constellations.
 */
import { useEffect, useRef } from "react";

interface Star {
  x: number;
  y: number;
  r: number;
  vx: number;
  vy: number;
  baseAlpha: number;
  phase: number;
  pulse: number;
}

interface Props {
  starsCount?: number;
  starsSize?: number;
  starsOpacity?: number;
  glowIntensity?: number;
  movementSpeed?: number;
  mouseInfluence?: number;
  mouseGravity?: "attract" | "repel";
  gravityStrength?: number;
  className?: string;
}

export function GalaxyStarsBackground({
  starsCount = 110,
  starsSize = 1.6,
  starsOpacity = 0.75,
  glowIntensity = 14,
  movementSpeed = 0.28,
  mouseInfluence = 90,
  mouseGravity = "attract",
  gravityStrength = 60,
  className = "",
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let raf = 0;
    let w = 0;
    let h = 0;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const stars: Star[] = [];
    const mouse = { x: -9999, y: -9999 };

    const resize = () => {
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize);

    for (let i = 0; i < starsCount; i++) {
      stars.push({
        x: Math.random() * window.innerWidth,
        y: Math.random() * window.innerHeight,
        r: Math.random() * starsSize + 0.35,
        vx: (Math.random() - 0.5) * movementSpeed * 0.4,
        vy: -Math.random() * movementSpeed * 0.9 - 0.02,
        baseAlpha: Math.random() * 0.5 + starsOpacity * 0.35,
        phase: Math.random() * Math.PI * 2,
        pulse: Math.random() * 0.02 + 0.005,
      });
    }

    const onMove = (e: MouseEvent) => {
      mouse.x = e.clientX;
      mouse.y = e.clientY;
    };
    window.addEventListener("mousemove", onMove);

    let t = 0;
    const tick = () => {
      t += 1;
      ctx.clearRect(0, 0, w, h);

      for (let i = 0; i < stars.length; i++) {
        const s = stars[i];
        const dx = mouse.x - s.x;
        const dy = mouse.y - s.y;
        const dist2 = dx * dx + dy * dy;
        if (dist2 < mouseInfluence * mouseInfluence && dist2 > 1) {
          const dist = Math.sqrt(dist2);
          const force =
            (gravityStrength / dist) *
            (mouseGravity === "attract" ? 1 : -1) *
            0.6;
          s.vx += (dx / dist) * force * 0.05;
          s.vy += (dy / dist) * force * 0.05;
        }
        s.vx *= 0.995;
        s.vy *= 0.995;
        s.x += s.vx;
        s.y += s.vy;

        if (s.x < -10) s.x = w + 10;
        if (s.x > w + 10) s.x = -10;
        if (s.y < -10) s.y = h + 10;
        if (s.y > h + 10) s.y = -10;

        const twinkle =
          0.6 + 0.4 * Math.sin(t * s.pulse * 8 + s.phase);
        const alpha = Math.min(1, s.baseAlpha * twinkle);
        const glow = glowIntensity * s.r;

        const grad = ctx.createRadialGradient(
          s.x, s.y, 0, s.x, s.y, glow
        );
        grad.addColorStop(0, `rgba(148, 220, 255, ${alpha})`);
        grad.addColorStop(0.35, `rgba(99, 160, 255, ${alpha * 0.45})`);
        grad.addColorStop(1, "rgba(60, 90, 200, 0)");
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(s.x, s.y, glow, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = `rgba(230, 245, 255, ${alpha})`;
        ctx.beginPath();
        ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
        ctx.fill();
      }

      // faint constellations (only when few stars — cheap loop)
      if (stars.length <= 140) {
        ctx.strokeStyle = "rgba(120, 160, 255, 0.045)";
        ctx.lineWidth = 0.6;
        for (let i = 0; i < stars.length; i += 3) {
          const a = stars[i];
          const b = stars[(i + 1) % stars.length];
          const ddx = a.x - b.x;
          const ddy = a.y - b.y;
          if (ddx * ddx + ddy * ddy < 16000) {
            ctx.beginPath();
            ctx.moveTo(a.x, a.y);
            ctx.lineTo(b.x, b.y);
            ctx.stroke();
          }
        }
      }

      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
    };
  }, [
    starsCount, starsSize, starsOpacity, glowIntensity,
    movementSpeed, mouseInfluence, mouseGravity, gravityStrength,
  ]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden
      className={`pointer-events-none fixed inset-0 z-[15] h-full w-full ${className}`}
    />
  );
}
