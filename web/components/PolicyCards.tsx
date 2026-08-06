"use client";

import { Reveal } from "./Reveal";

/**
 * The categorical layer. Each policy owns exactly one pastel, and that mapping
 * holds everywhere it appears — here, in the dashboard pill switcher, in the
 * hero chips. The colour encodes WHICH POLICY; it is not variety.
 *
 * Cards lift UP on hover (shadow grows, card rises) and their resting tilt
 * relaxes toward 0 — the opposite mechanic to the buttons, which press in. The
 * tilt alternates per card so the grid looks hand-placed.
 */

type Policy = {
  id: string;
  kind: string;
  title: string;
  body: string;
  tone: string;
  rotate: number;
  hoverRotate: number;
  glyph: React.ReactNode;
};

const stroke = {
  fill: "none",
  stroke: "var(--color-void)",
  strokeWidth: 2,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
};

const POLICIES: Policy[] = [
  {
    id: "pii-reaches-bi",
    kind: "Lineage path · downstream",
    title: "PII reaches BI",
    body: "A column tagged PII must not reach a dashboard through any path, unless it was masked on the way.",
    tone: "bg-blush",
    rotate: -1.6,
    hoverRotate: -0.7,
    glyph: (
      <svg viewBox="0 0 48 48" className="h-11 w-11" aria-hidden>
        <circle cx="7" cy="24" r="4" {...stroke} />
        <path d="M11 24h9" {...stroke} />
        <circle cx="24" cy="24" r="4" {...stroke} />
        <path d="M28 24h6" {...stroke} />
        <rect x="34" y="16" width="12" height="16" rx="2" {...stroke} />
        <path d="M37 27v-4M41 27v-7" {...stroke} />
      </svg>
    ),
  },
  {
    id: "certified-without-owner",
    kind: "Entity condition",
    title: "Certified, unowned",
    body: "Anything marked Certified must have an owner. Certification without accountability is a promise nobody made.",
    tone: "bg-sage",
    rotate: 1.3,
    hoverRotate: 0.6,
    glyph: (
      <svg viewBox="0 0 48 48" className="h-11 w-11" aria-hidden>
        <circle cx="24" cy="18" r="10" {...stroke} />
        <path d="M19 18l3.5 3.5L29 15" {...stroke} />
        <path d="M17 30l-3 12 10-5 10 5-3-12" {...stroke} />
        <path d="M10 40l6-6M38 40l-6-6" {...stroke} strokeDasharray="2 3" />
      </svg>
    ),
  },
  {
    id: "stale-upstream-feeds-live",
    kind: "Lineage path · upstream",
    title: "Stale feeds live",
    body: "A certified asset must not depend on a stale or deprecated upstream, anywhere within four hops.",
    tone: "bg-sky",
    rotate: -1.4,
    hoverRotate: -0.5,
    glyph: (
      <svg viewBox="0 0 48 48" className="h-11 w-11" aria-hidden>
        <circle cx="14" cy="14" r="8" {...stroke} strokeDasharray="3 3" />
        <path d="M14 10v4l3 2" {...stroke} />
        <path d="M22 20l8 8" {...stroke} />
        <path d="M26 28h4v-4" {...stroke} transform="rotate(45 28 26)" />
        <rect x="30" y="30" width="12" height="12" rx="2" {...stroke} />
      </svg>
    ),
  },
  {
    id: "freeform",
    kind: "Agentic",
    title: "Whatever you can say",
    body: "Type a rule in English. The agent compiles it into a policy file, or plans its own reads and investigates.",
    tone: "bg-sand",
    rotate: 1.5,
    hoverRotate: 0.7,
    glyph: (
      <svg viewBox="0 0 48 48" className="h-11 w-11" aria-hidden>
        <path d="M8 12h20M8 20h26M8 28h14" {...stroke} />
        <path d="M22 28l4 4-4 4" {...stroke} />
        <path d="M34 22l2.5 5.5L42 30l-5.5 2.5L34 38l-2.5-5.5L26 30l5.5-2.5z" {...stroke} />
      </svg>
    ),
  },
];

export function PolicyCards() {
  return (
    <div className="grid grid-cols-1 gap-7 min-[900px]:grid-cols-2">
      {POLICIES.map((policy, index) => (
        <Reveal key={policy.id} index={index} as="article">
          <article
            className={`card-lift group relative overflow-hidden ${policy.tone} p-6 min-[560px]:p-8 min-[900px]:p-9`}
            style={{ rotate: `${policy.rotate}deg` }}
            onMouseEnter={(e) => {
              e.currentTarget.style.rotate = `${policy.hoverRotate}deg`;
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.rotate = `${policy.rotate}deg`;
            }}
          >
            <div
              aria-hidden
              className="absolute right-5 top-5 opacity-90 min-[560px]:right-7 min-[560px]:top-7"
              style={{ transform: `rotate(${policy.rotate * 3}deg)` }}
            >
              {policy.glyph}
            </div>

            <p className="eyebrow" style={{ color: "var(--color-signal-deep)" }}>
              {policy.kind}
            </p>
            <h3 className="mt-4 max-w-[62%] font-display text-[21px] font-extrabold leading-tight tracking-[-0.02em] text-void min-[560px]:max-w-[70%] min-[560px]:text-[24px]">
              {policy.title}
            </h3>
            <p className="mt-3 max-w-[92%] text-[14px] leading-[1.55] text-void/75">{policy.body}</p>
            <p className="machine mt-5 text-void/55">{policy.id}</p>
          </article>
        </Reveal>
      ))}
    </div>
  );
}
