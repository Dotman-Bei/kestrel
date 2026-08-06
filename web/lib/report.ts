import reportJson from "@/data/report.json";

/**
 * Types for the JSON a scan emits (`kestrel scan --json`). This file is the
 * only place that knows the wire shape — the components take typed objects.
 *
 * `data/report.json` is a committed real run against the fixture graph. Point
 * it at a live run by re-running `kestrel scan --live --json web/data/report.json`.
 */

export type Entity = {
  urn: string;
  type: string;
  name: string;
  platform?: string;
  subType?: string;
  tags?: string[];
  owners?: string[];
  domain?: string;
};

export type Hop = {
  source: string;
  target: string;
  transform?: string;
  query?: string;
  level: "column" | "table";
};

export type LineagePath = {
  hops: number;
  nodes: Entity[];
  edges: Hop[];
  rendered: string;
  notes?: string[];
};

export type WriteBack = {
  kind: "tag" | "structured_property" | "document" | "pr" | "notify";
  target: string;
  detail: string;
  applied?: boolean;
  dryRun?: boolean;
  error?: string;
};

export type Violation = {
  id: string;
  policyId: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  engine: string;
  title: string;
  message: string;
  subject: Entity;
  sink?: Entity;
  path?: LineagePath;
  evidence?: string[];
  queries?: string[];
  owners?: string[];
  remediation?: string;
  rationale?: string;
  detectedAt: string;
  writebacks?: WriteBack[];
};

export type PolicyResult = {
  policyId: string;
  description: string;
  severity: string;
  engine: string;
  subjectsScanned: number;
  pathsWalked: number;
  violationCount: number;
  violations: Violation[];
  error?: string;
  durationMs: number;
  notes?: string[];
};

export type ScanReport = {
  runId: string;
  mode: "live" | "offline";
  target?: string;
  datahubUrl?: string;
  startedAt: string;
  finishedAt?: string;
  writebackEnabled: boolean;
  dryRun: boolean;
  summary: {
    policies: number;
    violations: number;
    subjectsScanned: number;
    pathsWalked: number;
    bySeverity: Record<string, number>;
    writebacks: number;
    writebacksApplied: number;
  };
  results: PolicyResult[];
  warnings?: string[];
};

export const report = reportJson as unknown as ScanReport;

/** Categorical colour per policy. This mapping is fixed everywhere it appears. */
export const POLICY_TONE: Record<string, string> = {
  "pii-reaches-bi": "bg-blush",
  "certified-without-owner": "bg-sage",
  "certified-dashboard-without-owner": "bg-sage",
  "stale-upstream-feeds-live": "bg-sky",
  freeform: "bg-sand",
};

const SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"];

export function allViolations(source: ScanReport = report): Violation[] {
  return source.results
    .flatMap((r) => r.violations)
    .sort(
      (a, b) =>
        SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
        a.policyId.localeCompare(b.policyId),
    );
}

/** The display name DataHub would show, derived from the URN. */
export function shortName(urn: string): string {
  if (urn.startsWith("urn:li:schemaField:")) {
    const inner = urn.slice(urn.indexOf("(") + 1, urn.lastIndexOf(")"));
    const column = inner.slice(inner.lastIndexOf(",") + 1);
    const parent = inner.slice(0, inner.lastIndexOf(","));
    return `${datasetLeaf(parent)}.${column}`;
  }
  if (urn.startsWith("urn:li:dataset:")) return datasetLeaf(urn);
  const parts = urn.slice(urn.indexOf("(") + 1, urn.lastIndexOf(")")).split(",");
  return parts[parts.length - 1] || urn;
}

function datasetLeaf(urn: string): string {
  const inner = urn.slice(urn.indexOf("(") + 1, urn.lastIndexOf(")"));
  const name = inner.split(",")[1] ?? inner;
  return name.split(".").pop() ?? name;
}

export function entityKind(entity?: Entity): string {
  if (!entity) return "";
  return entity.subType || entity.type;
}
