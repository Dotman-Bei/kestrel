"use client";

import { useEffect, useRef } from "react";
import { getGsap, prefersReducedMotion } from "@/lib/motion";

/**
 * The scroll-drawn diagram, and the argument of the whole page.
 *
 * A per-entity test can only ever ask about ONE of these boxes. The condition
 * Kestrel evaluates spans all five — so the drawing is the point: the path
 * builds hop by hop via stroke-dashoffset, a trace runs it, the dashboard pops
 * in with back.out(2), and the violation badge lands last.
 *
 * Fires once on scroll-in. Reduced motion renders the completed diagram.
 */

const NODES = [
  { x: 60, label: "patients.ssn", sub: "PII · postgres" },
  { x: 250, label: "stg_patients", sub: "snowflake" },
  { x: 440, label: "patient_encounters", sub: "certified" },
  { x: 630, label: "encounter_summary", sub: "view" },
  { x: 820, label: "patient_overview", sub: "dashboard" },
];

const Y = 92;

export function ThesisDiagram() {
  const ref = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = ref.current;
    if (!svg) return;

    const paths = Array.from(svg.querySelectorAll<SVGPathElement>("[data-edge]"));
    const nodes = Array.from(svg.querySelectorAll<SVGGElement>("[data-node]"));
    const sink = svg.querySelector<SVGGElement>("[data-sink]");
    const badge = svg.querySelector<SVGGElement>("[data-badge]");
    const trace = svg.querySelector<SVGCircleElement>("[data-trace]");

    const showFinalFrame = () => {
      paths.forEach((p) => {
        p.style.strokeDasharray = "none";
        p.style.strokeDashoffset = "0";
        p.style.opacity = "1";
      });
      nodes.forEach((n) => {
        n.style.opacity = "1";
        n.style.transform = "none";
      });
      if (sink) {
        sink.style.opacity = "1";
        sink.style.transform = "none";
      }
      if (badge) {
        badge.style.opacity = "1";
        badge.style.transform = "none";
      }
      if (trace) trace.style.opacity = "0";
    };

    if (prefersReducedMotion()) {
      showFinalFrame();
      return;
    }

    const gsap = getGsap();
    const ctx = gsap.context(() => {
      // The sink's initial scale is set here rather than as an inline style:
      // scaling an SVG group about its own centre needs GSAP's svgOrigin, and a
      // CSS `transform-origin` in px does not resolve the same way in SVG.
      const sinkNode = NODES[NODES.length - 1];
      if (sink) {
        gsap.set(sink, { opacity: 0, scale: 0.6, svgOrigin: `${sinkNode.x} ${Y}` });
      }

      const timeline = gsap.timeline({
        scrollTrigger: { trigger: svg, start: "top 78%", once: true },
      });

      timeline.to(nodes, { opacity: 1, y: 0, duration: 0.4, stagger: 0.12, ease: "power2.out" });

      paths.forEach((path, i) => {
        const length = path.getTotalLength();
        gsap.set(path, { strokeDasharray: length, strokeDashoffset: length, opacity: 1 });
        timeline.to(
          path,
          { strokeDashoffset: 0, duration: 0.45, ease: "power1.inOut" },
          0.35 + i * 0.3,
        );
      });

      if (trace) {
        timeline.set(trace, { opacity: 1 }, 0.35);
        NODES.slice(1).forEach((node, i) => {
          timeline.to(
            trace,
            { attr: { cx: node.x }, duration: 0.45, ease: "power1.inOut" },
            0.35 + i * 0.3,
          );
        });
        timeline.to(trace, { opacity: 0, duration: 0.2 });
      }

      if (sink) timeline.to(sink, { opacity: 1, scale: 1, duration: 0.5, ease: "back.out(2)" }, "-=0.1");
      if (badge) timeline.to(badge, { opacity: 1, y: 0, duration: 0.4, ease: "back.out(1.8)" });
    }, svg);

    return () => ctx.revert();
  }, []);

  return (
    <div>
      {/* Below ~760px the diagram cannot shrink further without the hop labels
          becoming unreadable, so it scrolls instead. An overflow with no
          affordance reads as a clipped diagram, hence the explicit hint --
          hidden once the whole thing fits. */}
      <p
        aria-hidden
        className="data-label mb-3 text-left min-[820px]:hidden"
      >
        Scroll to follow the path &rarr;
      </p>
      {/* Full-bleed only while it actually scrolls. Past 820px the diagram fits
          the content column, so the negative margins reset -- otherwise it
          would sit wider than the paragraph above it on desktop. */}
      <div className="-mx-5 w-[calc(100%+40px)] overflow-x-auto px-5 min-[560px]:-mx-6 min-[560px]:w-[calc(100%+48px)] min-[560px]:px-6 min-[820px]:mx-0 min-[820px]:w-full min-[820px]:px-0">
        <svg
          ref={ref}
          viewBox="0 0 900 200"
          className="h-auto w-full min-w-[700px]"
          role="img"
          aria-label="A four-hop lineage path from the column patients.ssn through staging, a certified mart and a reporting view, ending at the dashboard patient_overview — flagged as a violation."
        >
        <defs>
          {/* userSpaceOnUse is required: these edges are perfectly horizontal,
              so their object bounding box has zero height and an
              objectBoundingBox gradient would not render at all. */}
          <linearGradient
            id="kestrel-edge"
            gradientUnits="userSpaceOnUse"
            x1={NODES[0].x}
            x2={NODES[NODES.length - 1].x}
            y1={Y}
            y2={Y}
          >
            <stop offset="0%" stopColor="rgba(25,29,38,0.45)" />
            <stop offset="100%" stopColor="var(--color-signal)" />
          </linearGradient>
        </defs>

        {NODES.slice(0, -1).map((node, i) => (
          <path
            key={`edge-${node.label}`}
            data-edge
            d={`M ${node.x + 26} ${Y} L ${NODES[i + 1].x - 26} ${Y}`}
            stroke="url(#kestrel-edge)"
            strokeWidth={2.5}
            strokeLinecap="round"
            fill="none"
            opacity={0}
          />
        ))}

        {NODES.map((node, i) => {
          const isSink = i === NODES.length - 1;
          return (
            <g
              key={node.label}
              data-node
              opacity={0}
              style={{ transform: "translateY(14px)" }}
            >
              {isSink ? (
                <g data-sink opacity={0}>
                  <rect
                    x={node.x - 24}
                    y={Y - 20}
                    width={48}
                    height={40}
                    rx={6}
                    fill="var(--color-signal)"
                    stroke="var(--color-void)"
                    strokeWidth={2.5}
                  />
                  <path
                    d={`M ${node.x - 12} ${Y + 8} v -8 M ${node.x} ${Y + 8} v -16 M ${node.x + 12} ${Y + 8} v -11`}
                    stroke="var(--color-surface)"
                    strokeWidth={2.5}
                    strokeLinecap="round"
                  />
                </g>
              ) : (
                <circle
                  cx={node.x}
                  cy={Y}
                  r={i === 0 ? 15 : 12}
                  fill={i === 0 ? "var(--color-blush)" : "var(--color-surface)"}
                  stroke="var(--color-void)"
                  strokeWidth={2.5}
                />
              )}

              <text
                x={node.x}
                y={Y + 46}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={11}
                fill="var(--color-text)"
              >
                {node.label}
              </text>
              <text
                x={node.x}
                y={Y + 62}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={9.5}
                letterSpacing="0.08em"
                fill="var(--color-muted-2)"
              >
                {node.sub.toUpperCase()}
              </text>
              <text
                x={node.x}
                y={Y - 32}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={9.5}
                letterSpacing="0.08em"
                fill="var(--color-muted-2)"
              >
                {i === 0 ? "SUBJECT" : `HOP ${i}`}
              </text>
            </g>
          );
        })}

        <circle data-trace cx={NODES[0].x} cy={Y} r={5} fill="var(--color-signal)" opacity={0} />

        <g data-badge opacity={0} style={{ transform: "translateY(10px)" }}>
          <rect
            x={735}
            y={158}
            width={148}
            height={30}
            rx={6}
            fill="var(--color-signal)"
            stroke="var(--color-void)"
            strokeWidth={2.5}
          />
          <text
            x={809}
            y={178}
            textAnchor="middle"
            fontFamily="var(--font-mono)"
            fontSize={11}
            letterSpacing="0.12em"
            fill="var(--color-surface)"
          >
            VIOLATION · 4 HOPS
          </text>
        </g>
        </svg>
      </div>
    </div>
  );
}
