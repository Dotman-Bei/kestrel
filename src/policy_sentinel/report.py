"""Terminal output.

The live run is the demo, so this file matters more than its line count suggests:
a violation has to be legible in one glance -- what rule, what asset, and the
hop-by-hop path that proves it.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from rich.console import Console, Group
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from . import urns
from .models import PolicyResult, ScanReport, Violation
from .policy import Policy

SEVERITY_STYLE = {
    "critical": "bold white on red",
    "high": "bold red",
    "medium": "bold yellow",
    "low": "cyan",
    "info": "dim",
}

ARROW = "->"


def severity_text(severity: str) -> Text:
    return Text(f" {severity.upper()} ", style=SEVERITY_STYLE.get(severity, "white"))


def banner(console: Console, report: ScanReport, policies: List[Policy]) -> None:
    subtitle = "governance as code, enforced across the lineage graph"
    console.print()
    console.print(
        Panel(
            Text.assemble(
                ("KESTREL", "bold magenta"),
                ("  policy sentinel\n", "bold white"),
                (subtitle, "dim"),
            ),
            border_style="magenta",
            padding=(0, 2),
        )
    )
    mode = Text()
    mode.append("mode ", style="dim")
    mode.append(
        report.mode,
        style="green" if report.mode == "live" else "yellow",
    )
    if report.mode == "offline":
        mode.append("  (fixture graph, no live instance)", style="dim yellow")
    mode.append("   policies ", style="dim")
    mode.append(str(len(policies)), style="bold")
    mode.append("   write-back ", style="dim")
    mode.append(
        "enabled" if report.writeback_enabled and not report.dry_run else "dry-run",
        style="green" if report.writeback_enabled and not report.dry_run else "yellow",
    )
    console.print(mode)
    console.print()


def policy_line(console: Console, policy: Policy, result: PolicyResult) -> None:
    if result.error:
        status, style = "ERROR", "bold red"
    elif result.violations:
        status, style = f"{len(result.violations)} VIOLATION" + ("S" if len(result.violations) > 1 else ""), "bold red"
    else:
        status, style = "PASS", "bold green"

    line = Text()
    line.append(f"  {status:<14}", style=style)
    line.append(f"{policy.id:<36}", style="bold")
    line.append(
        f"{result.subjects_scanned} subject(s)"
        + (f", {result.paths_walked} path(s)" if result.paths_walked else "")
        + f", {result.duration_ms}ms",
        style="dim",
    )
    console.print(line)
    if result.error:
        console.print(Text(f"      {result.error}", style="red"))


def violation_panel(violation: Violation, base_url: Optional[str] = None) -> Panel:
    header = Text()
    header.append_text(severity_text(violation.severity))
    header.append("  ")
    header.append(violation.policy_id, style="bold magenta")
    header.append(f"  ({violation.id})", style="dim")

    body = Text()
    body.append("\n")
    body.append(violation.message, style="bold white")
    body.append("\n")

    if violation.path is not None:
        body.append("\n")
        for index, node in enumerate(violation.path.nodes):
            label = urns.short_name(node.urn)
            kind = node.sub_type or node.type
            if index:
                body.append(f"  {ARROW} ", style="magenta")
            else:
                body.append("  ")
            style = "bold red" if index == len(violation.path.nodes) - 1 else "white"
            body.append(label, style=style)
            body.append(f" [{kind}]", style="dim")
        body.append("\n")

        for index, hop in enumerate(violation.path.hops, start=1):
            detail = hop.transform or (" ".join(hop.query.split())[:80] if hop.query else None)
            if detail or hop.level == "table":
                body.append(f"    hop {index}", style="dim")
                if hop.level == "table":
                    body.append(" [table-level]", style="yellow")
                if detail:
                    body.append(f"  {detail}", style="dim italic")
                body.append("\n")
        for note in violation.path.notes:
            body.append(f"    note: {note}\n", style="yellow")

    if violation.owners:
        body.append("\n  owner  ", style="dim")
        body.append(", ".join(urns.short_name(o) for o in violation.owners), style="cyan")
    elif violation.path is not None or violation.sink is not None:
        body.append("\n  owner  ", style="dim")
        body.append("unassigned", style="yellow")

    if violation.rationale:
        body.append("\n  agent  ", style="dim")
        body.append(violation.rationale.strip()[:220], style="italic")

    for wb in violation.writebacks:
        body.append("\n  write  ", style="dim")
        mark = "OK" if wb.applied else ("DRY" if wb.dry_run else "!!")
        style = "green" if wb.applied else ("yellow" if wb.dry_run else "red")
        body.append(f"[{mark}] ", style=style)
        body.append(wb.detail, style="white")
        if wb.error:
            body.append(f"  ({wb.error})", style="red")

    return Panel(
        Group(header, body),
        border_style="red" if violation.severity in {"critical", "high"} else "yellow",
        padding=(0, 2),
    )


def summary_table(report: ScanReport) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    data = report.to_dict()["summary"]
    table.add_row("policies evaluated", str(data["policies"]))
    table.add_row("subjects scanned", str(data["subjectsScanned"]))
    table.add_row("lineage paths walked", str(data["pathsWalked"]))
    table.add_row("violations", str(data["violations"]))
    by_sev = data.get("bySeverity") or {}
    if by_sev:
        table.add_row("by severity", ", ".join(f"{k} {v}" for k, v in sorted(by_sev.items())))
    if data.get("writebacks"):
        table.add_row(
            "write-backs",
            f"{data['writebacksApplied']} applied / {data['writebacks']} produced",
        )
    return table


def render(
    console: Console,
    report: ScanReport,
    policies: Dict[str, Policy],
    show_evidence: bool = True,
) -> None:
    """Print the whole run."""
    banner(console, report, list(policies.values()))

    console.print(Rule("policies", style="dim"))
    for result in report.results:
        policy = policies.get(result.policy_id)
        if policy is not None:
            policy_line(console, policy, result)
        else:
            console.print(
                Text(f"  {'FREEFORM':<14}{result.policy_id:<28}{result.description[:50]}", style="magenta")
            )
    console.print()

    violations = report.violations
    if violations:
        console.print(Rule(f"{len(violations)} violation(s)", style="red"))
        for violation in violations:
            console.print(violation_panel(violation, report.datahub_url))
    else:
        console.print(Rule("clean", style="green"))
        console.print(Text("  No violations. Every policy passed.", style="green"))
    console.print()

    notes = [n for r in report.results for n in r.notes]
    if notes and show_evidence:
        console.print(Rule("scan notes", style="dim"))
        for note in notes:
            console.print(Text(f"  - {note}", style="dim"))
        console.print()

    if report.warnings:
        console.print(Rule("warnings", style="yellow"))
        for warning in report.warnings:
            console.print(Text(f"  ! {warning}", style="yellow"))
        console.print()

    console.print(Rule("summary", style="dim"))
    console.print(summary_table(report))
    console.print()
