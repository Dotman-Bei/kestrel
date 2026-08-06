# Kestrel 

**DataHub's Metadata Tests check one entity at a time. Kestrel checks conditions across the lineage graph** — "does any column tagged `PII` *reach* a BI dashboard, through any multi-hop path, without passing through a masking step?" That question is structurally inexpressible as a per-entity test, and it is the question governance teams actually ask.

> **Semgrep for your data catalog.** Write your governance rules as code. An agent enforces them across your entire lineage graph and writes the findings back into DataHub.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

---

## The 30 seconds

Everyone agrees PII shouldn't land on a dashboard. That rule lives in a Confluence page nobody enforces, because the thing it describes isn't a property of any single table — it's a property of a *path*. Kestrel makes it a file:

```yaml
- id: pii-reaches-bi
  severity: high
  subject:
    entity_type: column
    has_any_tag: [PII, Sensitive, Confidential]
  condition:
    lineage_reaches_type: [Dashboard, Chart]
    max_hops: 6
    without_step: "mask|hash|sha2|redact|anonymi[sz]"
```

…runs it against your catalog over the DataHub MCP Server, and writes what it finds *back into DataHub* — a tag on the offending column **and** on the dashboard it leaked into, a machine-readable violation record, and a human-readable incident document linked to both ends of the path.

The graph is materially richer after a run than it was before. That is the point.

```
$ kestrel scan

  VIOLATIONS     pii-reaches-bi    6 subject(s), 24 path(s), 31ms

  HIGH  pii-reaches-bi  (pii-reaches-bi-4a7c19e2)

  healthcare.raw.patients.ssn reaches Dashboard/Chart 'patient_overview' via a
  4-hop path, with no mask|hash|sha2|redact step on the way.

    patients.ssn [string] -> stg_patients.ssn -> patient_encounters.patient_ssn
    -> encounter_summary.patient_ssn -> patient_overview [Dashboard]

      hop 2  join on patient_id
      hop 4 [table-level]  Looker explore: encounter_summary
      note: column lineage unavailable at this hop; followed table-level lineage

    owner  dana.okoro
    write  [OK] tagged `patients.ssn` with `policy-violation`
    write  [OK] tagged exposure point `patient_overview` with `policy-violation`
    write  [OK] recorded `io.kestrel.policy_violation` on `patients.ssn`
    write  [OK] authored incident document "Policy violation: pii-reaches-bi — …"
```

---

## How this differs from DataHub Metadata Tests

This is the first question a reviewer should ask, so here is the direct answer.

| | Metadata Tests / Assertions | Kestrel |
|---|---|---|
| **Unit of evaluation** | One entity | One **path** through the lineage graph |
| **Can express** | "this column is tagged PII" | "this PII column *reaches* a dashboard in ≤6 hops" |
| **Mitigations** | n/a | "…unless the path passes through a masking step" |
| **Direction** | n/a | Downstream *and* upstream ("no certified asset may depend on a stale source") |
| **Evidence** | pass/fail | The hop-by-hop path, with the transform and real SQL on each edge |
| **Output** | a status | tags + structured properties + an incident document written back |

Metadata Tests are good at what they do, and Kestrel ships a per-entity rule (`certified-without-owner`) precisely because that class of check is still worth having. The difference is that Kestrel's *primary* rules are conditions no per-entity test can state. Concretely: `stg_patients.ssn` in the run above **is not tagged PII** — the tag stopped at the source table while the data kept going. A per-entity test sees a clean column. Kestrel follows the data.

---

## Install

```bash
git clone https://github.com/kestrel-sentinel/kestrel
cd kestrel
pip install -e .            # or: pip install -e ".[agent]" for the agentic engine
```

Python 3.10+. The deterministic engine needs no API key and no network.

### Try it in 10 seconds, with no DataHub

Kestrel ships a DataHub-shaped fixture graph (`fixtures/healthcare.json`) with the same failure modes the sample datapacks plant. Offline mode is the default:

```bash
kestrel scan                       # evaluate every policy
kestrel policies                   # what the shipped rules assert
kestrel explain pii-reaches-bi     # what one rule selects and forbids
```

Every report from offline mode is stamped `mode: offline` and carries a warning. It is for development, tests and the example outputs — never a substitute for a real run.

---

## Run it against a real DataHub

**1. Start DataHub and load sample data**

```bash
pip install acryl-datahub uv
datahub docker quickstart
datahub datapack load showcase-ecommerce      # a broad graph
# the `healthcare` datapack plants PII and quality issues — the demo target
```

Kestrel drives `uvx mcp-server-datahub` to talk to DataHub, so `uv` is required.

**2. Point Kestrel at it, with writes enabled**

The write-back tools are hidden unless the MCP server is started with mutations on:

```bash
export DATAHUB_GMS_URL=http://localhost:8080
export DATAHUB_GMS_TOKEN=<your token>
export TOOLS_IS_MUTATION_ENABLED=true
```

**3. Check the wiring before you trust a run**

```bash
kestrel doctor
```

This starts the MCP server, lists the tools it actually exposes, and tells you whether writes are on. If `add_tags` / `save_document` show as hidden, `TOOLS_IS_MUTATION_ENABLED` didn't take.

**4. Scan**

```bash
kestrel scan --live                 # read-only: find and report
kestrel scan --live --write         # apply the write-back to DataHub
kestrel scan --live --write --json out/report.json --md out/report.md
```

`--write` is opt-in. Without it you get the full report and the incident documents on disk, and nothing is mutated.

Kestrel drives `uvx mcp-server-datahub` by default; override with `--mcp-command` or `KESTREL_MCP_COMMAND`.

### Live mode status

**Verified against DataHub v1.7.0:**
- MCP server connection, tool enumeration, and write-tool availability (`add_tags`, `add_structured_properties`, `save_document`)
- All four shipped policies execute without error against a live catalog
- The three-layer write-back design (tags, structured properties, documents) matches the tools the OSS server actually exposes

**Not verified:**
- An actual violation found and written back live. The `showcase-ecommerce` sample datapack has no PII-tagged columns, so the headline `pii-reaches-bi` policy correctly found nothing to report.

The offline mode and committed `examples/` show real violations with correct multi-hop paths. A live violation requires either manual tagging in the DataHub UI or a datapack with column-level tags already present.

---

## The policy language

Three parts. `subject` selects, `condition` forbids, `on_violation` decides what gets written back.

```yaml
- id: stale-upstream-feeds-live
  severity: high
  description: A certified asset must not depend on a stale or deprecated upstream.
  subject:
    entity_type: dataset
    has_any_tag: [Certified, Production]
  condition:
    upstream_has_tag: [Stale, Deprecated, "Quality:Failed"]
    direction: upstream
    max_hops: 4
  on_violation: [tag, structured_property, document, pr]
```

**Subject keys** — `entity_type` (`dataset` · `dashboard` · `chart` · `column`), `has_tag`, `has_any_tag`, `has_term`, `missing_tag`, `platform`, `domain`, `sub_type`, `name_matches`, and `search` as a raw `/q` escape hatch.

**Condition** — exactly one primary, plus modifiers:

| Primary | Asks |
|---|---|
| `lineage_reaches_type` | does the subject reach an entity of this type? |
| `lineage_reaches_tag` | does it reach anything carrying this tag? |
| `upstream_has_tag` | does anything it depends on carry this tag? |
| `missing_owner` | is it unowned? |
| `missing_tag` | is a required tag absent? |

| Modifier | Effect |
|---|---|
| `max_hops` | traversal depth (default 5) |
| `direction` | `downstream` (default) or `upstream` |
| `without_step` | regex; a path through a matching intermediate, transform or SQL is **excused** |
| `without_tag` | a tag on an intermediate that excuses the path |

`without_step` is what keeps the rule honest. A pipeline that hashes email at the first hop should not be reported, and Kestrel says so out loud in the scan notes:

```
  - patients.email: path suppressed -- passes through masking step 'stg_patients_masked.email_masked'
```

**Shipped policies** — [`pii-reaches-bi`](policies/pii-reaches-bi.yaml) (the headline), [`certified-without-owner`](policies/certified-without-owner.yaml), [`stale-upstream-feeds-live`](policies/stale-upstream-feeds-live.yaml).

---

## The agent

`--ask` takes a rule in English. The agent handles it in two phases, and the first one is the interesting one:

```bash
kestrel scan --ask "no dashboard should depend on a deprecated table" \
             --save-policy policies/no-deprecated-behind-bi.yaml
```

**Phase 1 — compile.** Claude tries to express the rule in Kestrel's DSL. If it fits, the *deterministic* engine evaluates it, so the finding carries the same hop-by-hop evidence as a shipped policy — and `--save-policy` writes the compiled rule out as a file you can review, edit and re-run forever. An agent that turns intent into a reusable policy beats one that answers once.

**Phase 2 — investigate.** For rules the DSL cannot express, Claude plans its own reads — `search`, `get_lineage`, `list_columns`, `get_queries` — walks the graph, and reports what it finds. Every tool call is recorded, so the report shows the read plan it chose, not just its conclusion. Reported findings are validated against the catalog: a URN the agent invented is rejected rather than reported.

Needs `ANTHROPIC_API_KEY` and `pip install -e ".[agent]"`. **The template engine is deliberately LLM-free** — the core enforcement path cannot flake, and the agent is additive.

A real compile-phase run — the rule typed, the policy file it produced, and the violation that came back — is committed under [`examples/agent-compiled/`](examples/agent-compiled/).

---

## Write-back — three layers

For every violation, in increasing order of usefulness to a human:

1. **Tag** — `policy-violation` on the offending column *and* on the asset the data leaked into. The analyst who opens the dashboard sees the finding without knowing the rule exists.
2. **Structured property** — `io.kestrel.policy_violation` carrying `{finding_id, policy_id, severity, source_urn, sink_urn, path, hops, detected_at}`. Machine-readable, queryable by whatever agent runs next.
3. **Document** — the incident write-up, linked to both ends of the path: what rule fired, the hop-by-hop table, the real SQL behind those hops, who owns it, and the suggested fix. ([example](examples/violation-document.md))

Then two optional actions that turn a report into work: `pr` drafts a remediation pull request, `notify` drafts an owner ping. Both write to `out/actions/` by default and only reach the outside world behind an explicit `--open-pr` / `--notify` flag.

> **OSS note:** `update_description` is Cloud-only and hidden on OSS DataHub, so nothing here depends on it. Tags, structured properties and documents are the OSS-safe write surface, and the whole design stands on them.

Structured properties must be registered before first use — see [`scripts/structured_properties.yaml`](scripts/structured_properties.yaml). If the property isn't registered, that layer degrades to a recorded error and the other two still land.

---

## The web report

`web/` is a Next.js app for the people who won't run a CLI: a landing page that makes the
lineage-path argument, and a dashboard that reads the JSON a scan produces — the same
hop-by-hop evidence and write-back record the terminal shows.

```bash
kestrel scan --json web/data/report.json    # point it at any run, live or offline
cd web && npm install && npm run dev
```

`web/data/report.json` is committed as a real offline run so the UI works before you have
DataHub up. Re-run the command above with `--live` to point it at your own catalog.

Built with Tailwind v4 CSS-first tokens (`app/globals.css`) — one accent colour, three
fonts with strict jobs, hard offset shadows with a consistent physics (buttons press *in*,
cards lift *up*), and a categorical pastel per policy that never moves. Every animated
component guards `prefers-reduced-motion` and renders the correct static end-state.

---

## Repo layout

```
policies/                    the shipped rules, as YAML
src/policy_sentinel/
  policy.py                  the policy DSL + loader
  graph.py                   multi-hop lineage traversal  <- the differentiator
  catalog.py                 the read/write interface both backends implement
  mcp_client.py              live DataHub over mcp-server-datahub
  fixture_client.py          the same surface over a local JSON graph
  engine_templates.py        deterministic evaluator (LLM-free)
  engine_agent.py            compile-or-investigate agentic engine
  writeback.py               tags + structured properties + documents + actions
  render.py / report.py      markdown artifacts / terminal output
fixtures/healthcare.json     the offline graph
examples/                    committed sample outputs
scripts/                     setup + a smoke check for the live stack
web/                         Next.js report UI
tests/                       pytest
```

---

## Exit codes

CI-shaped, so this drops into a pipeline as-is:

| Code | Meaning |
|---|---|
| `0` | clean — every policy passed |
| `1` | violations found |
| `2` | a policy errored, or the catalog was unreachable |

---

## License

Apache 2.0 — see [LICENSE](LICENSE).
