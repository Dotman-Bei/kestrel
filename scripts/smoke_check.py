#!/usr/bin/env python
"""Day-0 verification against a live DataHub, before building anything on it.

Answers three questions the rest of the project depends on:

1. Does the MCP server start, and which tools does it actually expose?
2. Are the write tools present -- i.e. did ``TOOLS_IS_MUTATION_ENABLED=true``
   take effect?
3. Is column-level lineage populated deeply enough for a multi-hop
   PII -> Dashboard path, or must the demo fall back to table level?

The mutation test is add-then-remove on a single entity, so a green run leaves
the catalog exactly as it found it.

    python scripts/smoke_check.py
    python scripts/smoke_check.py --no-write   # read-only checks only
"""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.table import Table
from rich.text import Text

from policy_sentinel import urns
from policy_sentinel.catalog import CatalogError
from policy_sentinel.mcp_client import READ_TOOLS, WRITE_TOOLS, McpCatalog

console = Console()
PROBE_TAG = "kestrel-smoke-check"


def check(label: str, ok: bool, detail: str = "") -> bool:
    mark = Text("  PASS  ", style="bold white on green") if ok else Text("  FAIL  ", style="bold white on red")
    console.print(mark, Text(f" {label}", style="bold"), Text(f"  {detail}", style="dim"))
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gms-url", default=None)
    parser.add_argument("--token", default=None)
    parser.add_argument("--mcp-command", default=None)
    parser.add_argument("--no-write", action="store_true", help="Skip the mutation test.")
    args = parser.parse_args()

    console.print()
    console.rule("[bold magenta]Kestrel smoke check")
    console.print()

    # 1 -- connect ---------------------------------------------------------
    try:
        catalog = McpCatalog(
            command=args.mcp_command or "",
            gms_url=args.gms_url or "",
            gms_token=args.token or "",
        ).connect()
    except CatalogError as exc:
        check("MCP server starts", False, str(exc).splitlines()[0])
        console.print(Text(f"\n{exc}\n", style="red"))
        return 1

    ok = check("MCP server starts", True, f"{len(catalog.available_tools)} tools exposed")
    available = set(catalog.available_tools)

    table = Table(show_header=True, header_style="dim", box=None, padding=(0, 2))
    table.add_column("tool", style="bold")
    table.add_column("kind")
    table.add_column("status")
    for name in READ_TOOLS:
        table.add_row(name, "read", "available" if name in available else "MISSING")
    for name in WRITE_TOOLS:
        table.add_row(name, "write", "available" if name in available else "hidden")
    console.print()
    console.print(table)
    console.print()

    ok &= check(
        "required read tools present",
        {"search", "get_lineage"} <= available,
        "search + get_lineage",
    )
    writes_on = {"add_tags", "save_document"} <= available
    check(
        "TOOLS_IS_MUTATION_ENABLED=true",
        writes_on,
        "write-back available" if writes_on else "restart the MCP server with mutations enabled",
    )

    # 2 -- can we find PII at all? ----------------------------------------
    datasets = []
    try:
        datasets = catalog.search("(tags:PII OR fieldTags:PII)", entity_types=["dataset"], limit=10)
    except CatalogError as exc:
        console.print(Text(f"  search failed: {exc}", style="red"))
    check(
        "sample data has PII-tagged assets",
        bool(datasets),
        f"{len(datasets)} dataset(s)" if datasets else "load a datapack: datahub datapack load showcase-ecommerce",
    )

    # 3 -- is column lineage deep enough for the demo? --------------------
    column_hops = 0
    table_hops = 0
    for dataset in datasets[:5]:
        for column in catalog.list_schema_fields(dataset.urn)[:10]:
            if not column.has_tag("PII"):
                continue
            if catalog.neighbors(column.urn, "downstream"):
                column_hops += 1
            elif catalog.neighbors(dataset.urn, "downstream"):
                table_hops += 1

    if column_hops:
        check("column-level lineage populated", True, f"{column_hops} tagged column(s) have downstream edges")
    elif table_hops:
        check(
            "column-level lineage populated",
            False,
            "thin -- Kestrel will fall back to table-level lineage and say so in the report",
        )
    else:
        check("lineage populated", False, "no downstream edges found on the PII assets sampled")

    # 4 -- mutation round trip --------------------------------------------
    if writes_on and not args.no_write and datasets:
        target = datasets[0]
        try:
            catalog.add_tags(target.urn, [PROBE_TAG])
            catalog.remove_tags(target.urn, [PROBE_TAG])
            check("mutation round trip (add then remove)", True, urns.short_name(target.urn))
        except CatalogError as exc:
            ok &= check("mutation round trip (add then remove)", False, str(exc)[:120])
            console.print(
                Text(
                    f"  a tag named `{PROBE_TAG}` may be left on {target.urn} -- remove it manually.",
                    style="yellow",
                )
            )
    elif args.no_write:
        console.print(Text("  mutation test skipped (--no-write)", style="dim"))

    catalog.close()
    console.print()
    if ok:
        console.print(Text("  Ready. Run: kestrel scan --live --write\n", style="bold green"))
    else:
        console.print(Text("  Fix the failures above before relying on a live run.\n", style="bold red"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
