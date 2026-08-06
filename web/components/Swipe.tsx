/**
 * The system's highlighter: wraps 2-3 words inside a headline in a tilted,
 * signal-filled sticker. Used once per headline, on the last beat.
 *
 * Note the shadow here is full `--color-void` rather than `--color-brut-line`
 * -- this is the one place the shadow needs to read as fully solid.
 */
export function Swipe({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="inline-block rounded-[6px] border-2 border-void bg-signal px-3 py-0.5 text-surface"
      style={{ boxShadow: "3px 3px 0 0 var(--color-void)", transform: "rotate(-1deg)" }}
    >
      {children}
    </span>
  );
}
