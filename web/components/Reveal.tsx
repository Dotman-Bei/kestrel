"use client";

import { useEffect, useRef } from "react";
import { prefersReducedMotion, refreshOnFontsReady, getGsap } from "@/lib/motion";

type Props = {
  children: React.ReactNode;
  /** Stagger index -- each item waits `index * 0.07s` longer than the last. */
  index?: number;
  y?: number;
  className?: string;
  as?: "div" | "section" | "li" | "article";
};

/**
 * Scroll reveal: start at opacity 0 / y offset, rise when the element hits 88%
 * of the viewport.
 *
 * The reduced-motion branch is not "no animation" -- it renders the correct
 * final frame immediately. An element that never animates and was never made
 * visible is just an invisible element.
 */
export function Reveal({ children, index = 0, y = 20, className, as = "div" }: Props) {
  const ref = useRef<HTMLElement>(null);
  const Tag = as as React.ElementType;

  useEffect(() => {
    const node = ref.current;
    if (!node) return;

    if (prefersReducedMotion()) {
      node.style.opacity = "1";
      node.style.transform = "none";
      return;
    }

    const gsap = getGsap();
    const tween = gsap.fromTo(
      node,
      { opacity: 0, y },
      {
        opacity: 1,
        y: 0,
        duration: 0.6,
        ease: "power3.out",
        delay: index * 0.07,
        scrollTrigger: { trigger: node, start: "top 88%", once: true },
      },
    );
    refreshOnFontsReady();
    return () => {
      tween.scrollTrigger?.kill();
      tween.kill();
    };
  }, [index, y]);

  return (
    <Tag ref={ref} className={className} style={{ opacity: 0 }}>
      {children}
    </Tag>
  );
}
