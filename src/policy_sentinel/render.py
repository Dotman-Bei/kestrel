"""Markdown renderers for everything Kestrel writes out.

The incident document is the artifact that matters most: it is what a human
finds in DataHub tomorrow, and it has to stand on its own -- what rule fired,
the hop-by-hop path that proved it, the real SQL behind those hops, who owns the
asset, and what to do about it.
"""

from __future__ import annotations

from typing import Dict, List, Optional
from urllib.parse import quote

from . import urns
from .models import Entity, ScanReport, Violation
from .policy import Policy

ENTITY_ROUTES = {
    "dataset": "dataset",
    "dashboard": "dashboard",
    "chart": "chart",
    "dataJob": "tasks",
    "dataFlow": "pipelines",
    "container": "container",
}


def entity_url(urn: str, base_url: Optional[str]) -> Optional[str]:
    """Deep link into the DataHub UI, so a report is one click from the asset."""
    if not base_url:
        return None
    base = base_url.rstrip("/")
    if urns.is_field(urn):
        parent = urns.dataset_of_field(urn)
        if not parent:
            return None
        return f"{base}/dataset/{quote(parent, safe='')}/Schema"
    route = ENTITY_ROUTES.get(urns.entity_type(urn))
    if not route:
        return None
    return f"{base}/{route}/{quote(urn, safe='')}"


def _link(urn: str, base_url: Optional[str], label: Optional[str] = None) -> str:
    text = label or urns.qualified_name(urn)
    url = entity_url(urn, base_url)
    return f"[{text}]({url})" if url else f"`{text}`"


def _owner_line(violation: Violation) -> str:
    if not violation.owners:
        return "_unowned_ -- no owner is registered in DataHub."
    return ", ".join(f"`{urns.short_name(o)}`" for o in violation.owners)


def path_table(violation: Violation) -> List[str]:
    """The hop-by-hop table: the evidence a reviewer actually reads."""
    if violation.path is None:
        return []
    lines = [
        "| # | From | To | Level | Transform |",
        "|---|------|----|-------|-----------|",
    ]
    for index, hop in enumerate(violation.path.hops, start=1):
        transform = (hop.transform or "").replace("|", "\\|") or "—"
        lines.append(
            f"| {index} | `{urns.short_name(hop.source)}` | `{urns.short_name(hop.target)}` "
            f"| {hop.level} | {transform} |"
        )
    return lines


def incident_markdown(
    violation: Violation,
    policy: Policy,
    run_id: str,
    base_url: Optional[str] = None,
) -> str:
    """The document written back into DataHub for one violation."""
    subject = violation.subject
    lines: List[str] = [
        f"# Policy violation: `{policy.id}`",
        "",
        f"> {violation.message}",
        "",
        f"**Severity:** {violation.severity.upper()}  ",
        f"**Finding id:** `{violation.id}`  ",
        f"**Detected:** {violation.detected_at}  ",
        f"**Scan:** `{run_id}`  ",
        f"**Engine:** {violation.engine}",
        "",
        "## The rule",
        "",
        f"{policy.description or policy.summary()}",
        "",
        "```yaml",
        f"id: {policy.id}",
        f"subject:   {policy.subject.describe()}",
        f"condition: must not {policy.condition.describe()}",
        "```",
        "",
        "## What was found",
        "",
        f"- **Subject:** {_link(subject.urn, base_url)}"
        + (f" (tags: {', '.join(subject.tags)})" if subject.tags else ""),
    ]

    if violation.sink is not None:
        lines.append(
            f"- **Exposed at:** {_link(violation.sink.urn, base_url)} "
            f"({violation.sink.sub_type or violation.sink.type})"
        )
    if violation.path is not None:
        lines.append(f"- **Distance:** {violation.path.length} hop(s)")
    lines.append(f"- **Owner:** {_owner_line(violation)}")

    if violation.path is not None:
        lines += ["", "## The path", "", "```", violation.path.render(" -> "), "```", ""]
        lines += path_table(violation)
        for note in violation.path.notes:
            lines += ["", f"> Note: {note}"]

    sql_hops = [h for h in (violation.path.hops if violation.path else []) if h.query]
    if sql_hops or violation.queries:
        lines += ["", "## Evidence (SQL observed against these assets)", ""]
        for hop in sql_hops[:3]:
            lines += [
                f"`{urns.short_name(hop.source)}` -> `{urns.short_name(hop.target)}`:",
                "",
                "```sql",
                (hop.query or "").strip(),
                "```",
                "",
            ]
        for sql in violation.queries[:2]:
            lines += ["```sql", sql.strip(), "```", ""]

    if violation.rationale:
        lines += ["", "## Agent reasoning", "", violation.rationale, ""]

    if violation.remediation:
        lines += ["", "## Suggested fix", "", violation.remediation, ""]

    lines += [
        "",
        "---",
        "",
        "_Written by [Kestrel Policy Sentinel](https://github.com/kestrel-sentinel/kestrel) "
        "— governance rules as code, enforced across the lineage graph. "
        "This document was generated by a scan; edit the policy, not the document._",
        "",
    ]
    return "\n".join(lines)


def structured_property_payload(violation: Violation, run_id: str) -> Dict[str, object]:
    """The machine-readable record the next agent can query."""
    payload: Dict[str, object] = {
        "finding_id": violation.id,
        "policy_id": violation.policy_id,
        "severity": violation.severity,
        "detected_at": violation.detected_at,
        "scan_run": run_id,
        "engine": violation.engine,
        "source_urn": violation.subject.urn,
        "summary": violation.message,
    }
    if violation.sink is not None:
        payload["sink_urn"] = violation.sink.urn
    if violation.path is not None:
        payload["hops"] = violation.path.length
        payload["path"] = " -> ".join(violation.path.urn_chain)
    if violation.owners:
        payload["owners"] = ", ".join(violation.owners)
    return payload


def pr_body(violation: Violation, policy: Policy, base_url: Optional[str] = None) -> str:
    """A remediation pull request a data engineer could actually merge."""
    subject = violation.subject
    column = urns.field_path(subject.urn)
    table = urns.dataset_name(subject.urn) or urns.qualified_name(subject.urn)

    lines = [
        f"## Remediate `{policy.id}`: {violation.title}",
        "",
        violation.message,
        "",
        f"Detected by Kestrel Policy Sentinel (`{violation.id}`) at {violation.detected_at}.",
        "",
        "### Path",
        "",
    ]
    if violation.path is not None:
        lines += ["```", violation.path.render(" -> "), "```", ""]

    lines += ["### Proposed change", ""]
    if column:
        lines += [
            f"Mask `{column}` at the first transform downstream of `{table}` so the raw value "
            "never leaves the source boundary:",
            "",
            "```sql",
            f"-- was: select {column} from {table}",
            f"select sha2(lower(trim({column})), 256) as {column}_hash",
            f"from {table}",
            "```",
            "",
            "Then retag the hashed column and drop the raw column from the downstream model.",
        ]
    else:
        lines += [
            violation.remediation
            or "Break the offending path, or record the mitigation so the policy recognises it.",
        ]

    url = entity_url(subject.urn, base_url)
    if url:
        lines += ["", f"Asset in DataHub: {url}"]
    lines += [
        "",
        "---",
        "",
        "_Opened by Kestrel Policy Sentinel. Close this PR to accept the exposure; "
        "amend the policy if the rule itself is wrong._",
    ]
    return "\n".join(lines)


def notification_markdown(
    violation: Violation, policy: Policy, base_url: Optional[str] = None
) -> str:
    """Short message for the asset owner -- the thing a human reads on a phone."""
    owners = ", ".join(urns.short_name(o) for o in violation.owners) or "unassigned"
    url = entity_url(violation.subject.urn, base_url)
    lines = [
        f"*{violation.severity.upper()}* policy violation — `{policy.id}`",
        "",
        violation.message,
        "",
        f"Owner: {owners}",
    ]
    if violation.path is not None:
        lines.append(f"Path: `{violation.path.render(' -> ')}`")
    if url:
        lines.append(f"Asset: {url}")
    lines.append(f"Finding: `{violation.id}`")
    return "\n".join(lines)


def report_markdown(report: ScanReport, policies: Dict[str, Policy]) -> str:
    """The human-readable scan report saved to ``examples/``."""
    summary = report.to_dict()["summary"]
    lines = [
        "# Kestrel scan report",
        "",
        f"- **Run:** `{report.run_id}`",
        f"- **Mode:** {report.mode}"
        + (" (fixture graph — not a live instance)" if report.mode == "offline" else ""),
        f"- **Started:** {report.started_at}",
        f"- **Policies evaluated:** {summary['policies']}",
        f"- **Subjects scanned:** {summary['subjectsScanned']}",
        f"- **Lineage paths walked:** {summary['pathsWalked']}",
        f"- **Violations:** {summary['violations']}",
    ]
    by_sev = summary.get("bySeverity") or {}
    if by_sev:
        lines.append(
            "- **By severity:** "
            + ", ".join(f"{k} {v}" for k, v in sorted(by_sev.items()))
        )
    lines += ["", "## Findings", ""]

    if not report.violations:
        lines.append("No violations. Every policy passed.")
    for violation in report.violations:
        policy = policies.get(violation.policy_id)
        lines += [
            f"### `{violation.policy_id}` — {violation.title}",
            "",
            f"**{violation.severity.upper()}** · finding `{violation.id}`",
            "",
            violation.message,
            "",
        ]
        if violation.path is not None:
            lines += ["```", violation.path.render(" -> "), "```", ""]
        if violation.evidence:
            lines += ["<details><summary>Evidence</summary>", "", "```"]
            lines += violation.evidence
            lines += ["```", "", "</details>", ""]
        if violation.writebacks:
            lines.append("**Written back to DataHub:**")
            lines.append("")
            for wb in violation.writebacks:
                status = "applied" if wb.applied else ("dry-run" if wb.dry_run else "failed")
                lines.append(f"- `{wb.kind}` → {wb.detail} ({status})")
            lines.append("")
        if policy and policy.remediation:
            lines += [f"**Fix:** {policy.remediation}", ""]

    notes = [n for r in report.results for n in r.notes]
    if notes:
        lines += ["## Scan notes", ""]
        lines += [f"- {n}" for n in notes]
        lines.append("")
    if report.warnings:
        lines += ["## Warnings", ""]
        lines += [f"- {w}" for w in report.warnings]
        lines.append("")
    return "\n".join(lines)


def clean_filename(text: str) -> str:
    keep = [c if c.isalnum() or c in "-_" else "-" for c in text]
    return "".join(keep).strip("-").lower()[:80]


def sink_entity_label(entity: Optional[Entity]) -> str:
    return urns.short_name(entity.urn) if entity else "—"
