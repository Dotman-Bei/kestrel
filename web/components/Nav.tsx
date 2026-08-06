"use client";

import Link from "next/link";

/**
 * Glassmorphic floating nav: fixed, pill-shaped, centred, translucent with a
 * heavy backdrop blur. It floats over the hero rather than sitting in a bar.
 *
 * The `0.5px` hairline border is deliberate -- it appears wherever a divider
 * should be barely there, and it establishes the blur + hairline + pill
 * language the rest of the page borrows.
 */
export function Nav() {
  return (
    <header className="fixed inset-x-0 top-5 z-40 flex justify-center px-4">
      <nav
        aria-label="Main"
        className="flex items-center gap-6 rounded-full py-3 pl-[22px] pr-[14px] min-[900px]:gap-8"
        style={{
          background: "rgba(250, 251, 253, 0.65)",
          backdropFilter: "blur(20px) saturate(160%)",
          WebkitBackdropFilter: "blur(20px) saturate(160%)",
          border: "0.5px solid var(--color-border-strong)",
        }}
      >
        <Link
          href="/"
          aria-label="Kestrel home"
          className="font-display text-[16px] font-extrabold tracking-[-0.02em] text-void focus-visible:ring-2 focus-visible:ring-[var(--color-signal)] rounded-sm"
        >
          KESTREL
        </Link>

        <div className="hidden items-center gap-6 min-[900px]:flex">
          <a href="#gap" className="text-[13px] text-muted transition-colors hover:text-text">
            The gap
          </a>
          <a href="#policies" className="text-[13px] text-muted transition-colors hover:text-text">
            Policies
          </a>
          <a href="#writeback" className="text-[13px] text-muted transition-colors hover:text-text">
            Write-back
          </a>
        </div>

        <Link href="/dashboard" className="btn-press-sm bg-signal text-surface hover:bg-[var(--color-signal-deep)]">
          See a scan
        </Link>
      </nav>
    </header>
  );
}
