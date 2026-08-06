"use client";

import { useEffect, useRef } from "react";
import { prefersReducedMotion } from "@/lib/motion";

/**
 * The hero's domain moment.
 *
 * FLOAT put a particle field here because it sold a network product. Kestrel's
 * subject is a lineage graph, so that is what this draws: a layered DAG where
 * one path — source column to BI dashboard — periodically lights up in signal
 * and a trace runs along it. It is the product in one image.
 *
 * Decoration only: aria-hidden, pointer-events-none, and reduced-motion gets a
 * single static frame with the violating path already highlighted (the correct
 * end state, not a blank canvas).
 */

type Node = { x: number; y: number; layer: number; r: number; phase: number };

const LAYER_X = [0.08, 0.31, 0.53, 0.74, 0.93];

// layer index -> how many nodes sit in it
const LAYER_SIZES = [3, 3, 3, 2, 2];

// [fromIndex, toIndex] into the flattened node list
const EDGES: Array<[number, number]> = [
  [0, 3], [0, 4], [1, 4], [2, 5], [1, 3],
  [3, 6], [4, 7], [4, 6], [5, 8], [3, 7],
  [6, 9], [7, 9], [8, 10], [7, 10],
  [9, 11], [10, 12], [9, 12],
];

/** The violating path: raw PII column -> staging -> mart -> reporting view -> dashboard. */
const VIOLATION_PATH = [0, 3, 6, 9, 11];

function buildNodes(): Node[] {
  const nodes: Node[] = [];
  LAYER_SIZES.forEach((count, layer) => {
    for (let i = 0; i < count; i += 1) {
      nodes.push({
        x: LAYER_X[layer],
        y: (i + 1) / (count + 1),
        layer,
        r: layer === 4 ? 7 : 4.5,
        phase: Math.random() * Math.PI * 2,
      });
    }
  });
  return nodes;
}

function isOnPath(a: number, b: number): boolean {
  for (let i = 0; i < VIOLATION_PATH.length - 1; i += 1) {
    if (VIOLATION_PATH[i] === a && VIOLATION_PATH[i + 1] === b) return true;
  }
  return false;
}

export function LineageCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const nodes = buildNodes();
    const reduced = prefersReducedMotion();
    let width = 0;
    let height = 0;
    let raf = 0;
    let start = performance.now();

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const rect = canvas.getBoundingClientRect();
      width = rect.width;
      height = rect.height;
      canvas.width = Math.floor(width * dpr);
      canvas.height = Math.floor(height * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const pos = (node: Node, t: number) => ({
      x: node.x * width,
      // Each node bobs on its own sine loop, so no two are ever in sync.
      y: node.y * height + (reduced ? 0 : Math.sin(t / 1400 + node.phase) * 6),
    });

    const draw = (now: number) => {
      const t = now - start;
      // The trace runs the path over 4.2s, then rests for 1.8s.
      const cycle = 6000;
      const progress = reduced ? 1 : Math.min(((t % cycle) / 4200), 1);

      ctx.clearRect(0, 0, width, height);

      // edges
      EDGES.forEach(([a, b]) => {
        const from = pos(nodes[a], t);
        const to = pos(nodes[b], t);
        const onPath = isOnPath(a, b);
        ctx.beginPath();
        ctx.moveTo(from.x, from.y);
        // Gentle curve so the graph reads as flow, not a wire diagram.
        const midX = (from.x + to.x) / 2;
        ctx.bezierCurveTo(midX, from.y, midX, to.y, to.x, to.y);
        ctx.strokeStyle = onPath
          ? `rgba(217, 79, 56, ${0.25 + progress * 0.5})`
          : "rgba(25, 29, 38, 0.13)";
        ctx.lineWidth = onPath ? 1.8 : 1;
        ctx.stroke();
      });

      // the trace travelling the violating path
      if (progress > 0 && progress < 1) {
        const segments = VIOLATION_PATH.length - 1;
        const scaled = progress * segments;
        const index = Math.min(Math.floor(scaled), segments - 1);
        const local = scaled - index;
        const from = pos(nodes[VIOLATION_PATH[index]], t);
        const to = pos(nodes[VIOLATION_PATH[index + 1]], t);
        const x = from.x + (to.x - from.x) * local;
        const y = from.y + (to.y - from.y) * local;

        ctx.beginPath();
        ctx.arc(x, y, 4, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(217, 79, 56, 0.95)";
        ctx.fill();
        ctx.beginPath();
        ctx.arc(x, y, 11, 0, Math.PI * 2);
        ctx.fillStyle = "rgba(217, 79, 56, 0.14)";
        ctx.fill();
      }

      // nodes
      nodes.forEach((node, i) => {
        const p = pos(node, t);
        const onPath = VIOLATION_PATH.includes(i);
        const arrived =
          onPath && progress >= (VIOLATION_PATH.indexOf(i)) / (VIOLATION_PATH.length - 1);

        if (arrived && i === VIOLATION_PATH[VIOLATION_PATH.length - 1]) {
          // The sink flashes when the trace lands: this is the finding.
          ctx.beginPath();
          ctx.arc(p.x, p.y, node.r + 8, 0, Math.PI * 2);
          ctx.strokeStyle = "rgba(217, 79, 56, 0.4)";
          ctx.lineWidth = 1.5;
          ctx.stroke();
        }

        ctx.beginPath();
        ctx.arc(p.x, p.y, node.r, 0, Math.PI * 2);
        ctx.fillStyle = arrived ? "rgba(217, 79, 56, 0.9)" : "rgba(25, 29, 38, 0.28)";
        ctx.fill();

        if (node.layer === 4) {
          // BI nodes render as squares -- the shape says "this is a dashboard".
          ctx.beginPath();
          ctx.rect(p.x - node.r, p.y - node.r, node.r * 2, node.r * 2);
          ctx.fillStyle = arrived ? "rgba(217, 79, 56, 0.9)" : "rgba(25, 29, 38, 0.32)";
          ctx.fill();
        }
      });

      if (!reduced) raf = requestAnimationFrame(draw);
    };

    resize();
    if (reduced) {
      draw(performance.now());
    } else {
      raf = requestAnimationFrame(draw);
    }

    const onResize = () => {
      resize();
      start = performance.now();
      if (reduced) draw(performance.now());
    };
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    /* Held at low opacity: this sits behind the wordmark and the lead line, and
       ambient decoration must never compete with the copy for attention. */
    <canvas
      ref={ref}
      aria-hidden
      className="pointer-events-none absolute inset-0 h-full w-full opacity-25 min-[900px]:opacity-50"
    />
  );
}
