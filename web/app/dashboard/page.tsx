import type { Metadata } from "next";
import { GrainOverlay } from "@/components/GrainOverlay";
import { ScanDashboard } from "@/components/ScanDashboard";
import { TopBar } from "@/components/TopBar";
import { report } from "@/lib/report";

export const metadata: Metadata = {
  title: "Scan report — Kestrel",
  description:
    "Findings from a Kestrel scan: the lineage path that proved each violation, and what was written back into DataHub.",
};

/**
 * The in-app view. Reads the JSON a real scan emitted — regenerate it with
 * `kestrel scan --json web/data/report.json`.
 */
export default function DashboardPage() {
  return (
    <div className="relative flex min-h-full flex-1 flex-col bg-page">
      <GrainOverlay />
      <TopBar unread={report.summary.violations} />
      <main className="flex-1 px-4 pb-10 pt-8 min-[560px]:px-6 min-[900px]:px-8">
        <ScanDashboard />
      </main>
    </div>
  );
}
