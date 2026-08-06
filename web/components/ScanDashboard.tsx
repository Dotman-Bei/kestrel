"use client";

import { useMemo, useState } from "react";
import { Check, FileText, GitPullRequest, Send, Tag } from "lucide-react";
import { PathTrail } from "./PathTrail";
import { Reveal } from "./Reveal";
import {
  POLICY_TONE,
  allViolations,
  entityKind,
  prose,
  report,
  shortName,
  type Violation,
  type WriteBack,
} from "@/lib/report";

const WRITE_ICON = {
  tag: Tag,
  structured_property: Check,
  document: FileText,
  pr: GitPullRequest,
  notify: Send,
} as const;

const WRITE_LABEL = {
  tag: "Tag",
  structured_property: "Record",
  document: "Document",
  pr: "Pull request",
  notify: "Notify",
} as const;

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="min-w-0">
      <p className="data-label">{label}</p>
      <p
        className={`mt-1.5 font-display font-extrabold leading-none tracking-[-0.02em] ${
          accent ? "text-signal" : "text-void"
        }`}
        style={{ fontSize: "clamp(24px, 5.5vw, 32px)" }}
      >
        {value}
      </p>
    </div>
  );
}

function SeverityChip({ severity }: { severity: Violation["severity"] }) {
  const strong = severity === "critical" || severity === "high";
  return (
    <span
      className={`rounded-[6px] border-2 border-void px-2 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.12em] ${
        strong ? "bg-signal text-surface" : "bg-void-3 text-void"
      }`}
      style={{ boxShadow: "2px 2px 0 0 var(--color-brut-line)" }}
    >
      {severity}
    </span>
  );
}

function WriteBackRow({ write }: { write: WriteBack }) {
  const Icon = WRITE_ICON[write.kind] ?? Check;
  const status = write.applied ? "applied" : write.error ? "failed" : "drafted";
  return (
    <li className="flex items-start gap-3">
      <span
        aria-hidden
        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-void ${
          write.applied ? "bg-sage" : write.error ? "bg-signal" : "bg-surface"
        }`}
      >
        <Icon size={12} className={write.error ? "text-surface" : "text-void"} />
      </span>
      <span className="min-w-0">
        <span className="data-label mr-2 text-void">{WRITE_LABEL[write.kind] ?? write.kind}</span>
        <span className="text-[13px] break-words text-muted">{prose(write.detail)}</span>
        <span
          className={`ml-2 font-mono text-[10.5px] uppercase tracking-[0.08em] ${
            write.applied ? "text-muted-2" : "text-signal"
          }`}
        >
          {status}
        </span>
      </span>
    </li>
  );
}

/** Human name on top, machine truth underneath — honest about what is real. */
function AssetRef({ label, urn, kind }: { label: string; urn: string; kind?: string }) {
  return (
    <div className="min-w-0">
      <p className="data-label">{label}</p>
      <p className="mt-1 truncate text-[14px] font-medium text-void">
        {shortName(urn)}
        {kind && <span className="ml-2 font-normal text-muted">{kind.toLowerCase()}</span>}
      </p>
      <p className="machine mt-0.5 truncate" title={urn}>
        {urn}
      </p>
    </div>
  );
}

export function ScanDashboard() {
  const violations = useMemo(() => allViolations(), []);
  const policyIds = useMemo(
    () => Array.from(new Set(report.results.map((r) => r.policyId))),
    [],
  );
  const [active, setActive] = useState<string>("all");

  const shown = active === "all" ? violations : violations.filter((v) => v.policyId === active);
  const started = new Date(report.startedAt);

  return (
    <div className="mx-auto w-full max-w-[1180px]">
      {/* ---------------------------------------------------- run header */}
      <Reveal>
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <p className="eyebrow">Scan report</p>
            <h1
              className="mt-3 font-display font-extrabold leading-[1.05] tracking-[-0.02em] text-void"
              style={{ fontSize: "clamp(30px, 5vw, 46px)" }}
            >
              {report.summary.violations} findings, written back.
            </h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`rounded-full border-2 border-void px-3 py-1 font-mono text-[11px] uppercase tracking-[0.08em] ${
                report.mode === "live" ? "bg-sage text-void" : "bg-sand text-void"
              }`}
              style={{ boxShadow: "3px 3px 0 0 var(--color-brut-line)" }}
            >
              {report.mode}
            </span>
            <span
              className="rounded-full border-2 border-void bg-surface px-3 py-1 font-mono text-[11px] uppercase tracking-[0.08em] text-void"
              style={{ boxShadow: "3px 3px 0 0 var(--color-brut-line)" }}
            >
              {report.dryRun ? "dry run" : "write-back applied"}
            </span>
          </div>
        </div>
      </Reveal>

      {report.warnings?.length ? (
        <Reveal index={1}>
          {/* The provenance banner. It carries the same border + hard offset
              shadow as every other object in the system, and caps its measure
              so it never becomes a full-bleed strip of 13px text on a wide
              monitor. `sand` because this is the same categorical tone the
              mode chip uses for offline. */}
          <div
            className="mt-6 flex max-w-[68ch] flex-col gap-1.5 rounded-[12px] border-2 border-void bg-sand px-4 py-3 min-[560px]:flex-row min-[560px]:items-baseline min-[560px]:gap-3"
            style={{ boxShadow: "4px 4px 0 0 var(--color-brut-line)" }}
          >
            <span className="data-label shrink-0 text-void">Provenance</span>
            <p className="text-[13px] leading-relaxed text-void">
              {prose(report.warnings[0])}
            </p>
          </div>
        </Reveal>
      ) : null}

      {/* ------------------------------------------------------ stat row */}
      <Reveal index={2}>
        <div className="surface-card mt-8 grid grid-cols-2 gap-6 p-5 min-[560px]:grid-cols-3 min-[560px]:gap-8 min-[560px]:p-7 min-[900px]:grid-cols-5 min-[900px]:p-8">
          <Stat label="Violations" value={String(report.summary.violations)} accent />
          <Stat label="Policies" value={String(report.summary.policies)} />
          <Stat label="Subjects" value={String(report.summary.subjectsScanned)} />
          <Stat label="Paths walked" value={String(report.summary.pathsWalked)} />
          <Stat
            label="Write-backs"
            value={`${report.summary.writebacksApplied}/${report.summary.writebacks}`}
          />
        </div>
      </Reveal>

      <Reveal index={3}>
        <p className="machine mt-4">
          run {report.runId} · started {started.toISOString().replace("T", " ").slice(0, 19)} UTC
        </p>
      </Reveal>

      {/* ------------------------------------------------ pill switcher */}
      <Reveal index={4}>
        {/* Full-bleed horizontal scroll: the negative margin and padding must
            stay in step with the page gutter in app/dashboard/page.tsx, or the
            first pill clips at the viewport edge. */}
        <div className="mt-10 -mx-4 flex gap-3 overflow-x-auto px-4 pb-3 min-[560px]:-mx-6 min-[560px]:px-6 min-[900px]:-mx-8 min-[900px]:px-8">
          <PolicyPill
            id="all"
            label="All findings"
            count={violations.length}
            active={active === "all"}
            tone="bg-void-3"
            onSelect={setActive}
          />
          {policyIds.map((id) => (
            <PolicyPill
              key={id}
              id={id}
              label={id}
              count={violations.filter((v) => v.policyId === id).length}
              active={active === id}
              tone={POLICY_TONE[id] ?? "bg-void-3"}
              onSelect={setActive}
            />
          ))}
        </div>
      </Reveal>

      {/* ------------------------------------------------- the findings */}
      <div className="mt-8 space-y-8 pb-10">
        {shown.length === 0 && (
          <p className="rounded-[16px] border-2 border-void bg-sage px-6 py-8 text-center text-[15px] text-void">
            No findings for this policy. It passed.
          </p>
        )}

        {shown.map((violation, i) => (
          <Reveal key={violation.id} index={Math.min(i, 4)}>
            <article className="surface-card p-5 min-[560px]:p-7 min-[900px]:p-8">
              <div className="flex flex-wrap items-center gap-2 min-[560px]:gap-3">
                <SeverityChip severity={violation.severity} />
                <span
                  className={`rounded-full border-2 border-void ${
                    POLICY_TONE[violation.policyId] ?? "bg-void-3"
                  } px-3 py-0.5 font-mono text-[11px] text-void`}
                >
                  {violation.policyId}
                </span>
                {violation.engine === "agent" && (
                  <span className="rounded-full border-2 border-void bg-sand px-3 py-0.5 font-mono text-[11px] text-void">
                    agent
                  </span>
                )}
                <span className="machine w-full break-all min-[560px]:ml-auto min-[560px]:w-auto min-[560px]:break-normal">
                  {violation.id}
                </span>
              </div>

              <p
                className="mt-6 max-w-[70ch] font-display font-semibold leading-snug tracking-[-0.01em] text-void"
                style={{ fontSize: "clamp(17px, 3.6vw, 20px)" }}
              >
                {prose(violation.message)}
              </p>

              <div className="mt-7 grid grid-cols-1 gap-6 border-y border-border py-6 min-[640px]:grid-cols-2 min-[900px]:grid-cols-3">
                <AssetRef
                  label="Subject"
                  urn={violation.subject.urn}
                  kind={entityKind(violation.subject)}
                />
                {violation.sink ? (
                  <AssetRef
                    label="Exposed at"
                    urn={violation.sink.urn}
                    kind={entityKind(violation.sink)}
                  />
                ) : (
                  <div>
                    <p className="data-label">Exposed at</p>
                    <p className="mt-1 text-[14px] text-muted">&mdash;</p>
                  </div>
                )}
                <div>
                  <p className="data-label">Owner</p>
                  <p className="mt-1 text-[14px] font-medium text-void">
                    {violation.owners?.length
                      ? violation.owners.map((o) => o.split(":").pop()).join(", ")
                      : "unassigned"}
                  </p>
                  {!violation.owners?.length && (
                    <p className="machine mt-0.5 text-signal">nobody is accountable</p>
                  )}
                </div>
              </div>

              {violation.path && (
                <div className="mt-7">
                  <p className="data-label mb-4">
                    The path &middot; {violation.path.hops} hops
                  </p>
                  <PathTrail path={violation.path} />
                </div>
              )}

              {violation.rationale && (
                <p className="mt-7 border-l-2 border-signal pl-4 text-[13.5px] italic leading-relaxed text-muted">
                  {prose(violation.rationale)}
                </p>
              )}

              {violation.writebacks?.length ? (
                <div className="mt-8">
                  <p className="data-label mb-4">Written back to DataHub</p>
                  <ul className="space-y-3">
                    {violation.writebacks.map((write, index) => (
                      <WriteBackRow key={`${write.kind}-${index}`} write={write} />
                    ))}
                  </ul>
                </div>
              ) : null}

              {violation.remediation && (
                <div className="mt-8 rounded-[12px] bg-void-3 px-5 py-4">
                  <p className="data-label">Suggested fix</p>
                  <p className="mt-2 text-[13.5px] leading-relaxed text-muted">
                    {prose(violation.remediation)}
                  </p>
                </div>
              )}
            </article>
          </Reveal>
        ))}
      </div>
    </div>
  );
}

function PolicyPill({
  id,
  label,
  count,
  active,
  tone,
  onSelect,
}: {
  id: string;
  label: string;
  count: number;
  active: boolean;
  tone: string;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      aria-pressed={active}
      className={`shrink-0 rounded-full border-2 px-4 py-2 font-mono text-[12px] transition-all duration-150 focus-visible:ring-2 focus-visible:ring-[var(--color-signal)] ${
        active
          ? `border-void text-void ${tone}`
          : "border-border bg-surface text-muted hover:text-text"
      }`}
      style={active ? { boxShadow: "3px 3px 0 0 var(--color-brut-line)" } : undefined}
    >
      {label}
      <span className={active ? "ml-2 text-void/60" : "ml-2 text-muted-2"}>{count}</span>
    </button>
  );
}
