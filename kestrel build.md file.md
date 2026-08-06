# kestrel.md — Kestrel (Policy Sentinel)

> **Semgrep for your data catalog.** Write your governance rules as code; an agent enforces them across your entire lineage graph and writes the findings back into DataHub.

**Hackathon:** Build with DataHub — The Agent Hackathon (Devpost)
**Category:** Open / Wildcard
**Deadline:** Aug 10, 2026 · 5:00pm EDT
**Target:** Grand Prize / Wildcard Challenge ($6,000 / $3,000)

---

## 0. The one paragraph that has to land

DataHub already has Metadata Tests and Assertions that check **one entity at a time** ("does this table have an owner?"). Policy Sentinel checks **conditions across the lineage graph** — "does any column tagged `PII` *reach* a BI dashboard through any multi-hop path, unmasked?" That is the thing per-entity tests structurally cannot express, and it is the entire reason this project is not a reimplementation of a shipped feature. **Every piece of positioning — README, video, description — leads with this sentence.** If a judge walks away thinking "isn't this just Metadata Tests?", we lose Originality. Pre-empt it everywhere.

---

## 1. What it is (the loop)

A CLI + agent that runs one loop, per policy:

1. **READ** the DataHub graph via the MCP Server — find entities matching the policy's subject (e.g. columns tagged `PII`), then trace their lineage.
2. **EVALUATE** — walk each lineage path and test the policy's condition (e.g. "path terminates at or passes through a `Dashboard`"). For off-template rules, an **LLM reasoning step** interprets the plain-English policy into a read plan and judges the result.
3. **ACT + WRITE BACK** — for each violation: (a) tag the offending entity/column, (b) write a structured violation record via structured properties, (c) author a human-readable incident document into DataHub's knowledge base, and (d) optionally open a remediation PR / notify the owner.

The graph is materially richer after a run than before it. That is the win condition.

---

## 2. How it scores (strategy baked in)

All six criteria are **equally weighted** — presentation is a full third of the score.

| Criterion | How we win it |
|---|---|
| **Use of DataHub** (ranks #1, breaks ties first) | Multi-hop lineage reads + three-layer write-back (tags, structured properties, documents). Not read-only, not a single tag. |
| **Technical Execution** | Runs end-to-end against the `healthcare` sample; `dbt`-free, deterministic core; live green run on camera. |
| **Originality** | Lineage-path policies that Metadata Tests can't express. Framed as "OPA/Semgrep for the catalog." |
| **Real-World Usefulness** | Finds a real exposed-PII path in the sample data; *acts* on it (PR/notify), not just reports. |
| **Submission Quality** | Plain-English rule in → red violations out → catalog updated. Legible in one watch. |
| **Bonus: OSS** | Ship the policy pack as a DataHub Skill / contribute a lineage-path-condition example upstream. |

**Category choice rationale:** Wildcard is a thinner field than Code-Gen, and one $3k Challenge prize is awarded *per category* — better odds for the same quality bar.

---

## 3. Hard gates (Stage One pass/fail — get any wrong and nothing else matters)

- [ ] Uses the open-source platform **+ the MCP Server** (satisfies the "at least one of MCP/ACK/Skills/Analytics Agent" rule).
- [ ] **Apache 2.0 `LICENSE` file, visible in the repo's About section.** Common silent disqualifier — do this on day 1.
- [ ] Public repo with **all source + full setup instructions**.
- [ ] Working demo URL (hosted app **or** repo with clear run steps).
- [ ] Demo video **< 3 min**, public on YouTube/Vimeo, **no copyrighted music or trademarks**.
- [ ] `examples/` folder with sample outputs (generated violation docs + before/after).
- [ ] **New project, built within Jul 6–Aug 10.** Disclose any pre-existing code. Do not lift substantial code from prior projects (e.g. BlindPay) without disclosure.
- [ ] Opt into the **$50 Most Valuable Feedback** survey at submission — separate, near-free prize.

---

## 4. Architecture

```
                 ┌──────────────────────────────┐
   policies/*.yaml ─▶│  Policy Sentinel (CLI/agent)  │
                 │                              │
                 │  1. compile policy → plan    │
   LLM reasoning ─▶│  2. read graph (MCP read)    │◀── DataHub MCP Server
   (freeform rules) │  3. evaluate lineage paths   │      (uvx mcp-server-datahub)
                 │  4. write findings (MCP write)│──▶ DataHub GMS (localhost:8080)
                 └───────────────┬──────────────┘
                                 │
              ┌──────────────────┼───────────────────┐
              ▼                  ▼                   ▼
        add_tags        add_structured_properties  save_document
     (flag entity)      (machine-readable record)  (incident writeup)
                                 │
                                 ▼  (P1/P2)
                    remediation PR  /  owner notify
```

**Two engines, one interface:**
- **Template engine (P0):** deterministic. Each shipped policy is code that knows exactly which read tools to call and how to test the condition. Robust — this is what the live demo runs on.
- **Agentic engine (P1):** an LLM that takes a *novel* plain-English policy the templates don't cover, plans the reads using the MCP tools, and judges violations. This is what makes it "an agent" and not a shell script. Demo it on one freeform rule; keep templates as the reliable core.

---

## 5. DataHub / MCP integration — verified facts to build against

**Run the stack:**
- Spin up DataHub locally via Quickstart. Load a sample datapack:
  `datahub datapack load showcase-ecommerce` (broad graph) and use the `healthcare` dataset (planted PII/quality issues) as the demo target.
- MCP Server: `uvx mcp-server-datahub` (or `npx -y @acryldata/mcp-server-datahub init`), env `DATAHUB_GMS_URL=http://localhost:8080` and `DATAHUB_GMS_TOKEN=<token>`.
- **Enable writes:** set `TOOLS_IS_MUTATION_ENABLED=true`. Without it, the write-back tools are hidden.

**Read tools (confirmed available):**
- `search` — keyword search with `/q` syntax, filters like `tag:PII`, boolean logic. → find policy subjects.
- `get_lineage` — upstream/downstream for any entity, **table and column level**, with hop control. → trace flows.
- `get_lineage_paths` — exact path between two assets/columns incl. intermediate transforms + SQL. → prove "PII reaches dashboard."
- `get_entities` — batch metadata fetch by URN. → resolve owners/types.
- `list_schema_fields` — columns for a dataset.
- `get_dataset_queries` — real SQL referencing a dataset/column. → evidence in the violation writeup.

**Write tools (confirmed, gated by `TOOLS_IS_MUTATION_ENABLED=true`):**
- `add_tags` / `remove_tags` — on entities **or** schema fields (columns). → flag violations.
- `add_structured_properties` / `remove_structured_properties` — typed metadata. → machine-readable violation record (policy id, severity, path, timestamp).
- `save_document` — write a standalone knowledge doc into DataHub. → the human-readable incident report, linked to source + sink.

**⚠️ OSS constraint:** `update_description` is **Cloud-only** and hidden on OSS. Do **not** design write-back around editing descriptions. Tags + structured properties + documents are the OSS-safe write surface.

**Day 0 must-verify locally (an hour, before building anything pretty):**
1. `TOOLS_IS_MUTATION_ENABLED=true` actually exposes `add_tags` / `save_document` on your OSS instance → run the repo's `scripts/smoke_check.py` (it does add-then-remove mutation tests).
2. The `healthcare` / `showcase-ecommerce` sample data has **column-level lineage populated** deep enough for a multi-hop PII→Dashboard path. If column lineage is thin, fall back to **table-level** lineage for the demo path and say so — table-level still proves the concept.

---

## 6. The policy set

Ship **3 deterministic templates + 1 agentic freeform**. Resist adding more; breadth is not the win here.

1. **`pii-reaches-bi`** *(headline)* — any column tagged `PII`/sensitive whose downstream lineage reaches a `Dashboard`/`Chart` without a masking step. This is the multi-hop differentiator; make it the star of the video.
2. **`certified-without-owner`** — any entity marked certified/production that has no owner. Simple, fast, always finds hits in messy sample data.
3. **`stale-upstream-feeds-live`** — a live/certified model whose upstream has a freshness/quality issue (pairs with the `healthcare` planted issues, or `nyc-taxi` freshness if you swap datasets).
4. **`freeform` (agentic)** — user types a rule in English not covered above (e.g. "no PowerBI dashboard should depend on a `deprecated` table"). The LLM plans the reads via MCP tools and judges violations. One good live example proves the agent is real.

Policy file shape:
```yaml
- id: pii-reaches-bi
  severity: high
  description: "PII columns must not reach a BI dashboard unmasked."
  subject:   { has_tag: "PII" }
  condition: { lineage_reaches_type: "Dashboard", without_step: "mask" }
  on_violation: [tag, structured_property, document]   # + pr | notify at P1/P2
```

---

## 7. Write-back design (the differentiator — do it well)

For each violation, write **all three** layers:
1. **Tag** the offending entity/column: `urn:li:tag:policy-violation` (via `add_tags`). Instantly visible in the UI.
2. **Structured property**: `policy_violation = {policy_id, severity, source_urn, sink_urn, path, detected_at}` (via `add_structured_properties`). Machine-readable, queryable by the next agent.
3. **Document** (via `save_document`): a titled incident — what rule, what path (with the hop-by-hop lineage + the real SQL from `get_dataset_queries`), who owns it, suggested fix. This is the "materially richer graph" artifact judges reward.

This three-layer write is the sentence that beats a read-only tool on criterion #1 **and** wins tie-breaks.

---

## 8. Tech stack

- **Python** (matches DataHub's SDK ecosystem; `datahub` package available as a fallback emitter if any MCP write is missing on OSS).
- **MCP client** driving `mcp-server-datahub` for both read and write.
- **LLM** for the agentic engine (any provider; keep the template engine LLM-free so the core demo can't flake).
- **CLI**: `sentinel scan --policies policies/ --target <urn-or-domain>`; `sentinel scan --ask "<english rule>"` for freeform.
- Output: colorized terminal report + JSON + the write-backs.

---

## 9. Repo structure

```
policy-sentinel/
├── LICENSE                 # Apache 2.0 — visible in About (do first)
├── README.md               # leads with the anti-Metadata-Tests sentence
├── policies/               # the 3 templates as yaml
├── src/policy_sentinel/
│   ├── cli.py
│   ├── mcp_client.py       # read + write wrappers
│   ├── engine_templates.py # deterministic policies
│   ├── engine_agent.py     # freeform LLM policy
│   └── writeback.py        # tag + structured prop + document
├── examples/               # REQUIRED: sample outputs
│   ├── pii-reaches-bi.report.md
│   ├── violation-document.md      # what got written to DataHub
│   └── before-after/              # screenshots of the entity pre/post scan
├── scripts/setup.sh        # quickstart + datapack load + mutation env
└── demo/                   # video script, screenshots
```

---

## 10. MVP cut lines

**P0 — must ship (this is a passing, competent submission):**
- Quickstart + `healthcare` loaded; MCP server running with writes enabled.
- `pii-reaches-bi` + `certified-without-owner` templates working end-to-end.
- Write-back: tag + document (structured property if time).
- Live terminal run that finds real violations in the sample data.
- README (anti-Metadata-Tests lead), Apache license, `examples/` populated, <3-min video.

**P1 — the win condition (do not cut unless out of time):**
- Third template (`stale-upstream-feeds-live`) + the **agentic freeform** policy.
- One **action**: auto-open a remediation PR **or** notify the owner. (Earns the "Sentinel" name; lifts Real-World Usefulness.)
- Structured-property write-back layer.

**P2 — upside only if P0+P1 are solid:**
- OSS contribution: policy pack as a DataHub Skill / upstream example (banks the bonus).
- GitHub Action wrapper (the "plug-and-play in CI" story).
- Web view of the violation report.

---

## 11. Demo video script (< 3 min — a third of your score)

1. **(0:00–0:20) The hook.** "Everyone agrees PII shouldn't land on a dashboard. But that rule lives in a Confluence doc nobody enforces. Policy Sentinel is Semgrep for your data catalog." Show the plain-English policy file.
2. **(0:20–0:35) The gap.** One line: "DataHub's own tests check one entity at a time. Sentinel checks conditions *across the lineage graph*." (Kills the originality objection on camera.)
3. **(0:35–1:20) The run.** `sentinel scan`. Terminal lights red: "PII column `ssn` reaches Dashboard `patient_overview` via a 4-hop path, unmasked." Show the hop-by-hop path.
4. **(1:20–2:00) The write-back.** Cut to the DataHub UI. Refresh the dashboard entity — the **violation tag + incident document Sentinel just wrote** are sitting there. "The next person who opens this inherits the finding."
5. **(2:00–2:35) The agent.** Type a *new* English rule not in the templates; watch the agent plan the reads and find a violation. "It's not a fixed ruleset — it reasons over any policy."
6. **(2:35–3:00) The action + close.** Show the remediation PR / owner ping. "Write your governance as code. Let the agent enforce it." Repo + license on screen.

---

## 12. README checklist (Submission Quality criterion)

- [ ] First line = the anti-Metadata-Tests positioning sentence.
- [ ] 30-second "what/why" + the one-line pitch.
- [ ] Architecture diagram (§4).
- [ ] Exact setup: Quickstart → datapack → MCP server w/ `TOOLS_IS_MUTATION_ENABLED=true` → `sentinel scan`.
- [ ] "How this differs from DataHub Metadata Tests" section (multi-hop lineage).
- [ ] Link to demo video + `examples/`.
- [ ] Apache 2.0 badge/notice.

---

## 13. Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Judge thinks it's Metadata Tests | High | Lead every artifact with the multi-hop-lineage differentiator. |
| Column lineage thin in sample data | Medium | Verify Day 1; fall back to table-level path, state it. |
| MCP write fails on OSS | Low (verified supported) | `TOOLS_IS_MUTATION_ENABLED=true`; fallback to `datahub` SDK emitter for tags/props. |
| "Where's the agent?" | Medium | Ship the freeform agentic policy; demo it live. |
| Read-only / passive critique | Medium | Add one real action (PR/notify) at P1. |
| Runs out of time on polish | Medium | Video + README are P0, not afterthoughts — a third of the score. |

---

## 14. Anti-objection cheat sheet

- *"Isn't this Metadata Tests?"* → "Those are per-entity. We express **multi-hop lineage-path** conditions they can't — PII that *reaches* a dashboard N hops away."
- *"Where's the agent?"* → "The freeform engine reasons over any English policy and plans its own graph reads; templates are the reliable core."
- *"It just reports."* → "It tags, writes a structured record, authors an incident doc back into DataHub, and opens a remediation PR."
- *"Does it actually run?"* → Green live run against the `healthcare` sample in the video; `examples/` proves output without running.
