import Link from "next/link";
import { Bell } from "lucide-react";

/**
 * In-app top bar: h-16, hairline bottom border, wordmark left, bell + avatar
 * right. Unread state is a tiny signal dot — never a number badge on the icon.
 * The avatar lifts on hover (cards lift; buttons press).
 */
export function TopBar({ unread = 0 }: { unread?: number }) {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-border bg-page/80 px-5 backdrop-blur-md">
      <Link
        href="/"
        aria-label="Kestrel home"
        className="rounded-sm font-display text-[16px] font-extrabold tracking-[-0.02em] text-void focus-visible:ring-2 focus-visible:ring-[var(--color-signal)]"
      >
        KESTREL
      </Link>

      <div className="flex items-center gap-4">
        <button
          type="button"
          aria-label={unread > 0 ? `Notifications, ${unread} unread findings` : "Notifications"}
          className="relative rounded-full p-2 text-muted transition-colors hover:text-text focus-visible:ring-2 focus-visible:ring-[var(--color-signal)]"
        >
          <Bell size={18} aria-hidden />
          {unread > 0 && (
            <span
              aria-hidden
              className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-signal"
            />
          )}
        </button>

        <Link
          href="/"
          aria-label="Account"
          className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-void bg-sand font-mono text-[11px] font-medium text-void transition-transform duration-150 hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-[var(--color-signal)]"
        >
          DO
        </Link>
      </div>
    </header>
  );
}
