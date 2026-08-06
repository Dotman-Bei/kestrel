"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { getGsap, prefersReducedMotion } from "@/lib/motion";
import { FloatingChips } from "./FloatingChips";
import { LineageCanvas } from "./LineageCanvas";
import { Swipe } from "./Swipe";

/**
 * Hero stagger-in: everything marked `data-hero-in` starts at opacity 0 / y 20
 * and rises in sequence on load. JS/GSAP for entrances and ambient life; CSS
 * for interaction. That split is the rule the whole system follows.
 */
export function Hero() {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const items = Array.from(root.querySelectorAll<HTMLElement>("[data-hero-in]"));

    if (prefersReducedMotion()) {
      items.forEach((el) => {
        el.style.opacity = "1";
        el.style.transform = "none";
      });
      return;
    }

    const gsap = getGsap();
    const tween = gsap.fromTo(
      items,
      { opacity: 0, y: 20 },
      { opacity: 1, y: 0, duration: 0.6, ease: "power3.out", stagger: 0.1, delay: 0.1 },
    );
    return () => {
      tween.kill();
    };
  }, []);

  return (
    <section
      ref={ref}
      className="relative flex min-h-[100svh] items-center overflow-hidden px-5 pb-[60px] pt-[110px] min-[560px]:px-6 min-[900px]:pt-[100px]"
    >
      <LineageCanvas />
      <FloatingChips />

      <div className="relative mx-auto grid w-full max-w-[1180px] grid-cols-1 items-center gap-12 min-[900px]:grid-cols-[1.05fr_0.95fr] min-[900px]:gap-14">
        <div className="text-center min-[900px]:text-left">
          <p data-hero-in className="eyebrow" style={{ opacity: 0 }}>
            DataHub · MCP · Policy as code
          </p>

          <h1
            data-hero-in
            className="mt-6 font-display font-extrabold leading-[0.94] tracking-[-0.02em] text-void"
            style={{ opacity: 0, fontSize: "clamp(52px, 8vw, 104px)" }}
          >
            KESTREL
          </h1>

          <p
            data-hero-in
            className="mt-7 max-w-[30ch] font-body leading-[1.35] text-text mx-auto min-[900px]:mx-0"
            style={{ opacity: 0, fontSize: "clamp(18px, 2.2vw, 24px)" }}
          >
            Your rules. Your whole graph. <Swipe>Enforced.</Swipe>
          </p>

          <p data-hero-in className="mt-6 max-w-[46ch] text-[15px] leading-[1.55] text-muted mx-auto min-[900px]:mx-0" style={{ opacity: 0 }}>
            Metadata Tests check one entity at a time. Kestrel checks conditions{" "}
            <em className="not-italic font-semibold text-text">across the lineage graph</em> — then
            writes what it finds back into the catalog.
          </p>

          <div
            data-hero-in
            className="mt-9 flex flex-col items-center gap-4 min-[480px]:flex-row min-[900px]:justify-start justify-center"
            style={{ opacity: 0 }}
          >
            <Link href="/dashboard" className="btn-press bg-signal text-surface hover:bg-[var(--color-signal-deep)]">
              See a real scan
            </Link>
            <a
              href="#gap"
              className="btn-press bg-surface"
              style={{ boxShadow: "5px 5px 0 0 var(--color-signal-dim)" }}
            >
              Why this isn&apos;t Metadata Tests
            </a>
          </div>

          <p data-hero-in className="data-label mt-9" style={{ opacity: 0 }}>
            Apache 2.0 · Open source · Runs on OSS DataHub
          </p>
        </div>

        {/* The terminal: the product's actual output, not a mockup of one.
            Shown from 640px up — below that the 11.5px mono would need to
            shrink past legibility, so the copy carries the hero alone. */}
        <div data-hero-in style={{ opacity: 0 }} className="hidden min-[640px]:block">
          <div
            className="rounded-2xl border-2 border-void bg-void p-5 min-[900px]:p-6"
            style={{ boxShadow: "7px 7px 0 0 var(--color-brut-line)" }}
          >
            <div className="flex items-center gap-2 pb-4">
              <span className="h-2.5 w-2.5 rounded-full bg-signal" />
              <span className="h-2.5 w-2.5 rounded-full bg-sand" />
              <span className="h-2.5 w-2.5 rounded-full bg-sage" />
              <span className="ml-2 font-mono text-[11px] uppercase tracking-[0.08em] text-muted-2">
                kestrel scan
              </span>
            </div>

            <pre className="overflow-x-auto font-mono text-[11.5px] leading-[1.75] text-page">
{`$ kestrel scan --live --write

  `}<span className="text-[var(--color-blush)]">VIOLATIONS</span>{`   pii-reaches-bi
  `}<span className="text-[var(--color-sage)]">PASS</span>{`         certified-without-owner

  `}<span className="text-[var(--color-signal)]">HIGH</span>{`  patients.ssn reaches Dashboard
        'patient_overview' via a 4-hop path,
        with no masking step on the way.

    patients.ssn
      -> stg_patients.ssn
      -> patient_encounters.patient_ssn
      -> encounter_summary.patient_ssn
      -> `}<span className="text-[var(--color-signal)]">patient_overview</span>{`

    `}<span className="text-[var(--color-sage)]">[OK]</span>{` tagged column + dashboard
    `}<span className="text-[var(--color-sage)]">[OK]</span>{` wrote violation record
    `}<span className="text-[var(--color-sage)]">[OK]</span>{` authored incident document`}
            </pre>
          </div>
        </div>
      </div>
    </section>
  );
}
