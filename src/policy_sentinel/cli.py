"""``kestrel`` -- the command line.

    kestrel scan                       # every policy, against the fixture graph
    kestrel scan --live --write        # against a real DataHub, writing findings back
    kestrel scan --ask "no PowerBI dashboard should read a deprecated table"
    kestrel policies                   # what the shipped rules actually say
    kestrel doctor                     # can we reach DataHub, and are writes on?

Exit codes are CI-shaped: 0 clean, 1 violations found, 2 a policy errored.
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

# Windows terminals still default to a legacy codepage. Do this before the
# Console exists, or the first non-ASCII byte in a report kills the run.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):  # pragma: no cover - non-standard stream
        pass

from . import render, report as report_ui
from .catalog import Catalog, CatalogError
from .engine_templates import TemplateEngine
from .fixture_client import FixtureCatalog
from .models import ScanReport, utc_now
from .policy import Policy, PolicyError, load_policies
from .writeback import WriteBackConfig, WriteBackWriter

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Kestrel -- Semgrep for your data catalog. Governance rules as code, "
    "enforced across the DataHub lineage graph.",
)
console = Console()

DEFAULT_POLICIES = "policies"
DEFAULT_FIXTURE = "healthcare"


# ------------------------------------------------------------------ helpers


def _open_catalog(
    live: bool,
    fixture: str,
    gms_url: Optional[str],
    token: Optional[str],
    mcp_command: Optional[str],
    warnings: List[str],
) -> Catalog:
    if not live:
        catalog = FixtureCatalog.load(fixture)
        warnings.append(
            "offline mode: findings come from the bundled fixture graph, not a live DataHub. "
            "Use --live once your instance is up."
        )
        return catalog

    from .mcp_client import McpCatalog  # imported lazily: offline mode needs no MCP

    catalog = McpCatalog(
        command=mcp_command or "",
        gms_url=gms_url or "",
        gms_token=token or "",
    ).connect()
    if not catalog.writes_enabled:
        warnings.append(
            "the MCP server exposed no write tools -- start it with TOOLS_IS_MUTATION_ENABLED=true "
            "to let Kestrel write findings back. Running read-only."
        )
    return catalog


def _load(policies_path: str, only: List[str]) -> List[Policy]:
    try:
        return load_policies(policies_path, only=only or None)
    except PolicyError as exc:
        console.print(Text(f"policy error: {exc}", style="bold red"))
        raise typer.Exit(code=2)


def _emit(
    scan: ScanReport,
    policies: Dict[str, Policy],
    json_path: Optional[str],
    md_path: Optional[str],
    out_dir: Path,
) -> None:
    if json_path:
        target = Path(json_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(scan.to_dict(), indent=2), encoding="utf-8")
        console.print(Text(f"  json report  {target}", style="dim"))
    if md_path:
        target = Path(md_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render.report_markdown(scan, policies), encoding="utf-8")
        console.print(Text(f"  md report    {target}", style="dim"))
    docs = out_dir / "documents"
    if docs.exists() and any(docs.iterdir()):
        console.print(Text(f"  documents    {docs}", style="dim"))


# --------------------------------------------------------------------- scan


@app.command()
def scan(
    policies_path: str = typer.Option(DEFAULT_POLICIES, "--policies", "-p", help="Policy file or directory."),
    only: List[str] = typer.Option([], "--only", help="Run just these policy ids (repeatable)."),
    ask: Optional[str] = typer.Option(
        None, "--ask", help="A plain-English rule for the agentic engine, instead of the policy files."
    ),
    live: bool = typer.Option(False, "--live/--offline", help="Scan a real DataHub over MCP, or the fixture graph."),
    fixture: str = typer.Option(DEFAULT_FIXTURE, "--fixture", help="Fixture graph to use in offline mode."),
    gms_url: Optional[str] = typer.Option(None, "--gms-url", help="DataHub GMS URL (default $DATAHUB_GMS_URL)."),
    token: Optional[str] = typer.Option(None, "--token", help="DataHub token (default $DATAHUB_GMS_TOKEN)."),
    mcp_command: Optional[str] = typer.Option(None, "--mcp-command", help="Command that starts the MCP server."),
    write: bool = typer.Option(
        False, "--write/--dry-run", help="Actually write findings back. Default is a dry run."
    ),
    open_pr: bool = typer.Option(False, "--open-pr", help="Open remediation PRs with gh (needs --pr-repo)."),
    pr_repo: Optional[str] = typer.Option(None, "--pr-repo", help="owner/repo for remediation PRs."),
    notify: bool = typer.Option(False, "--notify", help="Send owner notifications (needs KESTREL_SLACK_WEBHOOK)."),
    out_dir: str = typer.Option("out", "--out", help="Where documents and action drafts are written."),
    json_path: Optional[str] = typer.Option(None, "--json", help="Write the machine-readable report here."),
    md_path: Optional[str] = typer.Option(None, "--md", help="Write a markdown report here."),
    max_hops: int = typer.Option(8, "--max-hops", help="Traversal ceiling, overriding per-policy max_hops."),
    max_paths: int = typer.Option(400, "--max-paths", help="Path budget per policy."),
    severity: str = typer.Option("medium", "--severity", help="Severity for --ask findings."),
    save_policy: Optional[str] = typer.Option(
        None, "--save-policy", help="With --ask: write the compiled rule to this YAML file."
    ),
) -> None:
    """Evaluate policies against the catalog and write the findings back."""
    warnings: List[str] = []
    run_id = f"kestrel-{utc_now()[:19].replace(':', '')}-{uuid.uuid4().hex[:6]}"
    out_path = Path(out_dir)

    try:
        catalog = _open_catalog(live, fixture, gms_url, token, mcp_command, warnings)
    except CatalogError as exc:
        console.print(Text(f"\ncannot reach the catalog:\n{exc}\n", style="bold red"))
        raise typer.Exit(code=2)

    scan_report = ScanReport(
        run_id=run_id,
        started_at=utc_now(),
        mode=catalog.mode,
        target=ask or policies_path,
        writeback_enabled=catalog.writes_enabled,
        dry_run=not write,
        warnings=warnings,
        datahub_url=catalog.base_url,
    )
    writer = WriteBackWriter(
        catalog=catalog,
        run_id=run_id,
        config=WriteBackConfig(
            enabled=True,
            dry_run=not write,
            out_dir=out_path,
            open_pr=open_pr,
            send_notify=notify,
            pr_repo=pr_repo,
        ),
    )

    policy_map: Dict[str, Policy] = {}
    try:
        if ask:
            policy_map = _run_ask(
                ask, severity, catalog, scan_report, writer, save_policy, warnings
            )
        else:
            loaded = _load(policies_path, only)
            policy_map = {p.id: p for p in loaded}
            engine = TemplateEngine(catalog, max_hops_cap=max_hops, max_paths=max_paths)
            for policy in loaded:
                result = engine.evaluate(policy)
                for violation in result.violations:
                    writer.apply(violation, policy)
                scan_report.results.append(result)
    finally:
        scan_report.finished_at = utc_now()
        catalog.close()

    report_ui.render(console, scan_report, policy_map)
    _emit(scan_report, policy_map, json_path, md_path, out_path)

    if scan_report.violations and not write:
        console.print(
            Text(
                "  dry run: nothing was written to the catalog. Re-run with --write to apply.\n",
                style="yellow",
            )
        )
    raise typer.Exit(code=scan_report.exit_code)


def _run_ask(
    rule: str,
    severity: str,
    catalog: Catalog,
    scan_report: ScanReport,
    writer: WriteBackWriter,
    save_policy: Optional[str],
    warnings: List[str],
) -> Dict[str, Policy]:
    """The agentic path: interpret one English rule and enforce it."""
    from .engine_agent import AgentEngine, AgentUnavailable

    console.print(Text(f'\n  interpreting: "{rule}"', style="italic magenta"))
    engine = AgentEngine(catalog=catalog)
    try:
        result = engine.run(rule, severity=severity)
    except AgentUnavailable as exc:
        console.print(Text(f"\nagentic engine unavailable: {exc}\n", style="bold red"))
        raise typer.Exit(code=2)

    policy = engine.compiled_policy
    if policy is not None:
        console.print(Text(f"  compiled to policy `{policy.id}`", style="green"))
        if save_policy:
            target = Path(save_policy)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(engine.policy_yaml() or "", encoding="utf-8")
            console.print(Text(f"  saved policy {target}", style="green"))
    else:
        console.print(Text("  no DSL equivalent -- investigating the graph directly", style="yellow"))

    effective = policy or Policy.from_dict(
        {
            "id": "freeform",
            "description": rule,
            "severity": severity,
            "subject": {"entity_type": "dataset"},
            "condition": {"missing_owner": True},
        },
        source="<agent>",
    )
    for violation in result.violations:
        writer.apply(violation, effective)

    scan_report.results.append(result)
    return {result.policy_id: effective}


# ----------------------------------------------------------------- policies


@app.command()
def policies(
    policies_path: str = typer.Option(DEFAULT_POLICIES, "--policies", "-p"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show the full condition."),
) -> None:
    """List the shipped policies and what each one actually asserts."""
    loaded = _load(policies_path, [])
    table = Table(title="Kestrel policies", title_style="bold magenta", header_style="dim")
    table.add_column("id", style="bold")
    table.add_column("sev")
    table.add_column("asserts")
    table.add_column("writes", style="dim")
    for policy in loaded:
        table.add_row(
            policy.id,
            Text(policy.severity, style=report_ui.SEVERITY_STYLE.get(policy.severity, "white")),
            policy.summary() if verbose else (policy.description or policy.summary()),
            ", ".join(policy.on_violation),
        )
    console.print()
    console.print(table)
    console.print(
        Text(
            "\n  Every condition above is evaluated across lineage paths, not per entity.\n",
            style="dim italic",
        )
    )


# ------------------------------------------------------------------- doctor


@app.command()
def doctor(
    gms_url: Optional[str] = typer.Option(None, "--gms-url"),
    token: Optional[str] = typer.Option(None, "--token"),
    mcp_command: Optional[str] = typer.Option(None, "--mcp-command"),
) -> None:
    """Check the live setup: MCP server, read tools, and whether writes are on."""
    from .mcp_client import READ_TOOLS, WRITE_TOOLS, McpCatalog

    console.print()
    console.print(Text("  connecting to the DataHub MCP server...", style="dim"))
    try:
        catalog = McpCatalog(
            command=mcp_command or "", gms_url=gms_url or "", gms_token=token or ""
        ).connect()
    except CatalogError as exc:
        console.print(Text(f"\n  FAILED\n{exc}\n", style="bold red"))
        raise typer.Exit(code=2)

    available = set(catalog.available_tools)
    table = Table(show_header=True, header_style="dim", box=None, padding=(0, 2))
    table.add_column("tool", style="bold")
    table.add_column("kind")
    table.add_column("status")
    for name in READ_TOOLS:
        table.add_row(
            name,
            "read",
            Text("available", style="green") if name in available else Text("missing", style="yellow"),
        )
    for name in WRITE_TOOLS:
        table.add_row(
            name,
            "write",
            Text("available", style="green")
            if name in available
            else Text("hidden (set TOOLS_IS_MUTATION_ENABLED=true)", style="yellow"),
        )
    console.print(table)

    extra = sorted(available - set(READ_TOOLS) - set(WRITE_TOOLS))
    if extra:
        console.print(Text(f"\n  other tools on this server: {', '.join(extra)}", style="dim"))

    if catalog.writes_enabled:
        console.print(Text("\n  writes enabled -- three-layer write-back is available.\n", style="bold green"))
    else:
        console.print(
            Text(
                "\n  writes unavailable. Restart the MCP server with TOOLS_IS_MUTATION_ENABLED=true.\n",
                style="bold yellow",
            )
        )
    catalog.close()


# ------------------------------------------------------------------ explain


@app.command()
def explain(
    policy_id: str = typer.Argument(..., help="Policy id to explain."),
    policies_path: str = typer.Option(DEFAULT_POLICIES, "--policies", "-p"),
) -> None:
    """Explain one policy: what it selects, what it forbids, what it writes."""
    loaded = {p.id: p for p in _load(policies_path, [])}
    policy = loaded.get(policy_id)
    if policy is None:
        console.print(Text(f"no such policy: {policy_id}", style="bold red"))
        console.print(Text(f"available: {', '.join(sorted(loaded))}", style="dim"))
        raise typer.Exit(code=2)

    console.print()
    console.print(Text(policy.id, style="bold magenta"))
    console.print(Text(f"  {policy.description}\n", style="white"))
    console.print(Text("  subject    ", style="dim") + Text(policy.subject.describe()))
    console.print(Text("  must not   ", style="dim") + Text(policy.condition.describe()))
    console.print(Text("  severity   ", style="dim") + Text(policy.severity))
    console.print(Text("  writes     ", style="dim") + Text(", ".join(policy.on_violation)))
    console.print(Text("  search     ", style="dim") + Text(policy.subject.to_dataset_query(), style="cyan"))
    if policy.condition.is_lineage:
        console.print(
            Text(
                "\n  This is a lineage-path condition: it walks the graph up to "
                f"{policy.condition.max_hops} hops {policy.condition.direction} of every subject. "
                "DataHub Metadata Tests evaluate one entity at a time and cannot express it.\n",
                style="italic dim",
            )
        )
    console.print()


@app.command()
def version() -> None:
    """Print the version."""
    from . import __version__

    console.print(f"kestrel {__version__}")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
