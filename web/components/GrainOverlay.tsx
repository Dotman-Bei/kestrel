/**
 * Film grain: a fixed, full-screen SVG-noise overlay above everything at very
 * low opacity. `opacity 0.035` + `mix-blend-overlay` is the whole recipe.
 * Barely perceptible; removing it makes the flat surfaces look noticeably
 * sterile. Drop it in last, keep it aria-hidden.
 */
export function GrainOverlay() {
  return (
    <div
      aria-hidden
      className="pointer-events-none fixed inset-0 z-50 h-full w-full opacity-[0.035] mix-blend-overlay"
    >
      <svg className="h-full w-full">
        <filter id="kestrel-grain">
          <feTurbulence
            type="fractalNoise"
            baseFrequency="0.85"
            numOctaves={2}
            stitchTiles="stitch"
          />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#kestrel-grain)" />
      </svg>
    </div>
  );
}
