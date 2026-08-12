"use client";

/**
 * Tri-Netra Forensics mascot: an all-seeing cyber-eye that tracks the cursor.
 * Extracted + re-themed from the cybersecurity-scout-chatbot reference.
 */
type Offset = { x: number; y: number };

export function OmniEye({
  pupil,
  ringPupil,
  className,
}: {
  pupil: Offset;
  ringPupil: Offset;
  className?: string;
}) {
  return (
    <svg
      viewBox="0 0 120 120"
      className={className}
      role="img"
      aria-label="Tri-Netra Forensics all-seeing cyber eye"
    >
      <defs>
        <radialGradient id="omni-iris" cx="50%" cy="38%" r="70%">
          <stop offset="0%" stopColor="oklch(0.78 0.14 195)" />
          <stop offset="55%" stopColor="oklch(0.5 0.13 230)" />
          <stop offset="100%" stopColor="oklch(0.28 0.1 250)" />
        </radialGradient>
        <radialGradient id="omni-glow" cx="50%" cy="45%" r="60%">
          <stop offset="0%" stopColor="oklch(0.55 0.15 210 / 0.5)" />
          <stop offset="70%" stopColor="oklch(0.4 0.12 235 / 0.18)" />
          <stop offset="100%" stopColor="oklch(0.25 0.1 250 / 0)" />
        </radialGradient>
        <linearGradient id="omni-ring" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="oklch(0.85 0.12 190)" />
          <stop offset="100%" stopColor="oklch(0.45 0.15 260)" />
        </linearGradient>
      </defs>

      {/* outer radar ring */}
      <circle cx="60" cy="60" r="46" fill="url(#omni-glow)" />
      <circle
        cx="60" cy="60" r="46"
        fill="none" stroke="oklch(0.7 0.13 200 / 0.35)"
        strokeWidth="1.5" strokeDasharray="4 6"
      />
      <circle cx="60" cy="60" r="38" fill="none"
        stroke="oklch(0.7 0.13 200 / 0.2)" strokeWidth="1" />

      {/* rotating scan line */}
      <g className="omni-scan">
        <line x1="60" y1="60" x2="60" y2="14"
          stroke="oklch(0.8 0.14 190 / 0.5)" strokeWidth="1.6"
          strokeLinecap="round" />
      </g>

      {/* brow */}
      <path d="M24 40 Q60 24 96 40" fill="none"
        stroke="oklch(0.75 0.13 195)" strokeWidth="3"
        strokeLinecap="round" />

      {/* eye socket */}
      <ellipse cx="60" cy="60" rx="34" ry="30"
        fill="oklch(0.1 0.04 250)" stroke="url(#omni-ring)"
        strokeWidth="4" />

      {/* tracking iris */}
      <g transform={`translate(${pupil.x} ${pupil.y})`}>
        <circle cx="60" cy="60" r="20" fill="url(#omni-iris)" />
        <circle cx="60" cy="60" r="9.5" fill="oklch(0.12 0.04 260)" />
        <circle cx="55" cy="55" r="3.2" fill="oklch(0.95 0.01 240 / 0.9)" />
      </g>

      {/* magnifier-lens iris (strong tracking) */}
      <clipPath id="omni-lens-clip">
        <circle cx="60" cy="60" r="11" />
      </clipPath>
      <g clipPath="url(#omni-lens-clip)">
        <g transform={`translate(${ringPupil.x * 1.6} ${ringPupil.y * 1.6})`}>
          <circle cx="60" cy="60" r="11" fill="oklch(0.75 0.14 195 / 0.55)" />
        </g>
      </g>

      {/* lens ring + shine */}
      <circle cx="60" cy="60" r="11" fill="none"
        stroke="oklch(0.85 0.12 190 / 0.8)" strokeWidth="1.6" />
      <path d="M50 52 Q55 48 60 49" fill="none"
        stroke="oklch(0.98 0.02 240 / 0.75)" strokeWidth="2"
        strokeLinecap="round" />

      {/* cheek nodes */}
      <circle cx="24" cy="76" r="2" fill="oklch(0.6 0.14 220 / 0.8)" />
      <circle cx="96" cy="76" r="2" fill="oklch(0.6 0.14 220 / 0.8)" />
    </svg>
  );
}
