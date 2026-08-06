"use client";

import { useEffect, useRef } from "react";
import { getGsap, prefersReducedMotion } from "@/lib/motion";

/**
 * Ambient layer: pastel pills carrying real asset names from the sample graph,
 * scattered across the hero, each bobbing on its own sine loop with a different
 * duration so no two are ever in sync.
 *
 * Decoration, so: pointer-events-none, aria-hidden, and dropped entirely below
 * 900px rather than repositioned.
 */

/**
 * Positioned into the page gutters only. The hero content column is
 * `max-w-[1180px]` centred, so anything inside roughly 8%-92% collides with
 * real text -- chips are ambience, and ambience never sits on top of the copy.
 */
const CHIPS = [
  { label: "patients.ssn", tone: "bg-blush", top: "14%", left: "1.8%", rotate: -3 },
  { label: "lab_results", tone: "bg-sky", top: "78%", left: "2.6%", rotate: 2 },
  { label: "claims_by_age", tone: "bg-sage", top: "88%", left: "86%", rotate: -2 },
];

export function FloatingChips() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root || prefersReducedMotion()) return;

    const gsap = getGsap();
    const chips = Array.from(root.querySelectorAll<HTMLElement>("[data-chip]"));
    const tweens = chips.map((chip, i) =>
      gsap.to(chip, {
        y: "+=11",
        duration: 2.6 + i * 0.18,
        ease: "sine.inOut",
        repeat: -1,
        yoyo: true,
      }),
    );
    return () => tweens.forEach((t) => t.kill());
  }, []);

  return (
    <div ref={ref} aria-hidden className="pointer-events-none absolute inset-0 hidden min-[1280px]:block">
      {CHIPS.map((chip) => (
        <span
          key={chip.label}
          data-chip
          className={`absolute rounded-full border-2 border-void ${chip.tone} px-4 py-[7px] font-mono text-[12px] text-void`}
          style={{
            top: chip.top,
            left: chip.left,
            boxShadow: "3px 3px 0 0 var(--color-brut-line)",
            transform: `rotate(${chip.rotate}deg)`,
          }}
        >
          {chip.label}
        </span>
      ))}
    </div>
  );
}
