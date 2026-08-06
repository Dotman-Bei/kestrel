"use client";

import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

let registered = false;

/** Register ScrollTrigger once, on the client only. Not a hook -- callable
 *  from inside effects, where the plugin actually needs to exist. */
export function getGsap() {
  if (typeof window !== "undefined" && !registered) {
    gsap.registerPlugin(ScrollTrigger);
    registered = true;
  }
  return gsap;
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return true;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * Webfonts change layout after ScrollTrigger has measured, which leaves reveal
 * positions wrong on first paint. Refresh once the fonts are in.
 */
export function refreshOnFontsReady() {
  if (typeof document === "undefined") return;
  const fonts = (document as Document & { fonts?: FontFaceSet }).fonts;
  if (fonts?.ready) {
    fonts.ready.then(() => ScrollTrigger.refresh());
  }
}
