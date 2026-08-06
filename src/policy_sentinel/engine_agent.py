"""The agentic engine: a plain-English rule, interpreted and enforced.

This is what makes Kestrel an agent rather than a linter with a config file. It
runs in two phases, and the first one matters as much as the second:

**Phase 1 — compile.** Claude reads the English rule and tries to express it in
Kestrel's policy DSL. If it can, the *deterministic* engine evaluates it. The
finding is then identical in kind to a shipped policy: same traversal, same
hop-by-hop evidence, same write-back. An agent that can turn intent into a
reusable, reviewable policy file is worth more than one that answers once.

**Phase 2 — investigate.** For rules the DSL cannot express, Claude plans its
own reads against the catalog: search, walk lineage, open columns, read SQL, and
judge what it finds. Every tool call is recorded, so the report shows the read
plan it chose, not just its conclusion.

The template engine stays LLM-free on purpose -- the headline demo must not be
able to flake. This module is additive.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml

from . import urns
from .catalog import Catalog
from .engine_templates import TemplateEngine
from .models import Entity, Hop, LineagePath, PolicyResult, Violation
from .policy import Policy, PolicyError

MODEL = "claude-opus-5"
MAX_TOKENS = 16000
MAX_STEPS = 14

COMPILE_SYSTEM = """You translate plain-English data-governance rules into Kestrel policy YAML.

Kestrel evaluates conditions across a DataHub lineage graph. A policy has three parts:

subject   -- which entities the rule is about
condition -- what must NOT be true of them
severity  -- critical | high | medium | low | info

Valid subject keys:
  entity_type: dataset | dashboard | chart | column   (column selects schema fields)
  has_tag: <tag or list, ALL must be present>
  has_any_tag: <list, ANY match>
  has_term: <glossary term>
  missing_tag: <tag that must be absent>
  platform: <platform key, e.g. snowflake>
  name_matches: <regex>
  sub_type: <DataHub sub-type, e.g. View>
  search: <raw DataHub /q string, escape hatch>

Valid condition keys -- exactly ONE primary, plus optional modifiers:
  primary:
    lineage_reaches_type: <entity type the subject must not reach, e.g. Dashboard>
    lineage_reaches_tag: <tag the subject must not reach>
    upstream_has_tag: <tag no upstream may carry>
    missing_owner: true
    missing_tag: <tag that must be present on the subject>
  modifiers:
    direction: downstream | upstream    (default downstream; upstream for upstream_has_tag)
    max_hops: <int, default 5>
    without_step: <regex list; a path passing a matching intermediate is excused>
    without_tag: <tag list; an intermediate carrying it excuses the path>

Rules:
- Emit ONE policy as a YAML mapping. No list, no markdown fence, no commentary.
- The id must be kebab-case and describe the rule.
- Use only the keys above. If the rule needs something outside this vocabulary
  (counting, comparing values, time windows, aggregate conditions, anything
  requiring judgement about content), set expressible=false and explain why.
- Prefer the DSL whenever it genuinely fits: a compiled policy is deterministic,
  reusable and produces hop-by-hop evidence."""

INVESTIGATE_SYSTEM = """You are Kestrel's investigation agent, enforcing one governance rule against a DataHub catalog.

You have read-only tools over the metadata graph. Plan your own reads:
find candidate entities, walk their lineage, inspect columns and SQL, then judge.

Method:
1. Search for the entities the rule is about. Column-level rules need
   list_columns on the datasets you find -- columns are not search hits.
2. Walk lineage one hop at a time with get_lineage, following paths that matter.
3. Call report_violation for each entity that genuinely breaks the rule, with
   the full URN chain that proves it.
4. Call finish when done, including when you found nothing.

Discipline:
- Report only what the graph shows. Never invent a URN, a tag, or a hop.
- A rule about reaching somewhere needs the actual path, not an assumption.
- If the evidence is ambiguous, say so in the rationale rather than reporting.
- Be economical: you have a limited number of tool calls. Search narrowly first."""


class AgentUnavailable(RuntimeError):
    """The agentic engine cannot run (missing SDK or API key)."""


def _tool(name: str, description: str, properties: Dict[str, Any], required: List[str]) -> Dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


READ_TOOLS = [
    _tool(
        "search",
        "Search the catalog with DataHub /q syntax, e.g. `tags:PII AND platform:snowflake`, "
        "`(tags:Certified OR tags:Production)`, or a bare word matched against names. "
        "Returns matching entities with their tags, owners and types. "
        "Columns are never returned here -- use list_columns on a dataset instead.",
        {
            "query": {"type": "string", "description": "The /q query string."},
            "entity_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Restrict to these types, e.g. ['dataset'] or ['dashboard','chart'].",
            },
            "limit": {"type": "integer", "description": "Max results (default 25)."},
        },
        ["query"],
    ),
    _tool(
        "get_lineage",
        "One hop of lineage from an entity or column. Call repeatedly to walk a multi-hop path. "
        "Returns each neighbour with its type, tags and the transform/SQL on the edge.",
        {
            "urn": {"type": "string", "description": "Entity or schemaField URN."},
            "direction": {
                "type": "string",
                "enum": ["downstream", "upstream"],
                "description": "downstream = where the data goes; upstream = where it came from.",
            },
        },
        ["urn", "direction"],
    ),
    _tool(
        "get_entity",
        "Full metadata for one URN: type, sub-type, tags, glossary terms, owners, domain.",
        {"urn": {"type": "string"}},
        ["urn"],
    ),
    _tool(
        "list_columns",
        "The columns of a dataset, with each column's tags. Required for any column-level rule.",
        {"dataset_urn": {"type": "string"}},
        ["dataset_urn"],
    ),
    _tool(
        "get_queries",
        "Real SQL observed against a dataset or column. Use as evidence in a finding.",
        {"urn": {"type": "string"}},
        ["urn"],
    ),
    _tool(
        "report_violation",
        "Record one entity that breaks the rule. Call once per violation. "
        "Only report what the graph actually showed you.",
        {
            "subject_urn": {"type": "string", "description": "The offending entity or column."},
            "message": {
                "type": "string",
                "description": "One sentence stating what is wrong, naming the assets involved.",
            },
            "rationale": {
                "type": "string",
                "description": "Why this breaks the rule, citing the specific evidence you read.",
            },
            "path_urns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ordered URN chain from subject to the problem asset, if lineage is involved.",
            },
            "sink_urn": {"type": "string", "description": "The asset the data reached, if any."},
        },
        ["subject_urn", "message", "rationale"],
    ),
    _tool(
        "finish",
        "End the investigation. Call this once, after reporting every violation you found "
        "(or immediately, if the graph is clean).",
        {
            "summary": {
                "type": "string",
                "description": "What you checked and what you concluded, in two or three sentences.",
            }
        },
        ["summary"],
    ),
]


@dataclass
class AgentEngine:
    """Interprets a freeform rule and enforces it."""

    catalog: Catalog
    model: str = MODEL
    max_steps: int = MAX_STEPS
    effort: str = "high"
    api_key: Optional[str] = None
    transcript: List[Dict[str, Any]] = field(default_factory=list, init=False)
    compiled_policy: Optional[Policy] = field(default=None, init=False)
    _client: Any = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------- client

    def _connect(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise AgentUnavailable(
                "the agentic engine needs the Anthropic SDK: pip install 'kestrel-policy-sentinel[agent]'"
            ) from exc
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise AgentUnavailable(
                "set ANTHROPIC_API_KEY to use --ask (the template policies need no API key)"
            )
        self._client = anthropic.Anthropic(api_key=key)
        return self._client

    # ------------------------------------------------------------ phase 1

    def compile(self, rule: str) -> Optional[Policy]:
        """Try to express the English rule in the policy DSL.

        Returns the compiled policy, or None when the rule needs the
        investigation loop instead.
        """
        client = self._connect()
        schema = {
            "type": "object",
            "properties": {
                "expressible": {
                    "type": "boolean",
                    "description": "True only if the rule fits the DSL exactly, with nothing lost.",
                },
                "reasoning": {
                    "type": "string",
                    "description": "One or two sentences: how you mapped it, or what the DSL cannot express.",
                },
                "policy_yaml": {
                    "type": "string",
                    "description": "The policy as a YAML mapping. Empty string when expressible is false.",
                },
            },
            "required": ["expressible", "reasoning", "policy_yaml"],
            "additionalProperties": False,
        }

        response = client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=COMPILE_SYSTEM,
            thinking={"type": "adaptive"},
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": f"Rule: {rule}"}],
        )
        if response.stop_reason == "refusal":
            raise AgentUnavailable("the model declined to interpret this rule")

        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            payload = json.loads(text)
        except ValueError as exc:
            raise AgentUnavailable(f"could not parse the compile response: {exc}") from exc

        self.transcript.append(
            {"phase": "compile", "expressible": payload.get("expressible"), "reasoning": payload.get("reasoning")}
        )
        if not payload.get("expressible"):
            return None

        raw = (payload.get("policy_yaml") or "").strip()
        if raw.startswith("```"):  # be forgiving about fences
            raw = raw.strip("`")
            raw = raw.split("\n", 1)[-1] if raw.lower().startswith("yaml") else raw
        try:
            data = yaml.safe_load(raw)
            if isinstance(data, list):
                data = data[0]
            data.setdefault("engine", "agent")
            policy = Policy.from_dict(data, source="<agent>")
        except (PolicyError, AttributeError, IndexError, yaml.YAMLError) as exc:
            # A malformed compile is not fatal: fall through to investigation.
            self.transcript.append({"phase": "compile", "error": str(exc), "yaml": raw})
            return None

        self.compiled_policy = policy
        self.transcript.append({"phase": "compile", "policy": policy.to_dict()})
        return policy

    # ------------------------------------------------------------ phase 2

    def _dispatch(self, name: str, args: Dict[str, Any], found: List[Violation], rule: str, severity: str) -> str:
        """Execute one agent tool call against the catalog."""
        if name == "search":
            hits = self.catalog.search(
                args.get("query", "*"),
                entity_types=args.get("entity_types"),
                limit=int(args.get("limit", 25)),
            )
            return json.dumps(
                {"count": len(hits), "results": [self._describe(e) for e in hits[:25]]}, indent=1
            )

        if name == "get_lineage":
            direction = args.get("direction", "downstream")
            hops = self.catalog.neighbors(args["urn"], direction)
            if not hops and urns.is_field(args["urn"]):
                parent = urns.dataset_of_field(args["urn"])
                hops = self.catalog.neighbors(parent, direction) if parent else []
                if hops:
                    return json.dumps(
                        {
                            "note": "no column-level lineage here; showing table-level lineage "
                            f"of {parent}",
                            "neighbors": [self._describe_hop(h, direction) for h in hops],
                        },
                        indent=1,
                    )
            return json.dumps(
                {"neighbors": [self._describe_hop(h, direction) for h in hops]}, indent=1
            )

        if name == "get_entity":
            entity = self.catalog.get_entity(args["urn"])
            return json.dumps(self._describe(entity) if entity else {"error": "not found"}, indent=1)

        if name == "list_columns":
            columns = self.catalog.list_schema_fields(args["dataset_urn"])
            return json.dumps(
                {"columns": [{"urn": c.urn, "name": urns.field_path(c.urn), "tags": c.tags} for c in columns]},
                indent=1,
            )

        if name == "get_queries":
            return json.dumps({"queries": self.catalog.get_dataset_queries(args["urn"], limit=3)}, indent=1)

        if name == "report_violation":
            violation = self._build_violation(args, rule, severity)
            if violation is None:
                return "REJECTED: subject_urn is not an entity in this catalog. Do not invent URNs."
            found.append(violation)
            return f"Recorded finding {violation.id}."

        if name == "finish":
            return "Investigation closed."

        return f"Unknown tool: {name}"

    def _describe(self, entity: Optional[Entity]) -> Dict[str, Any]:
        if entity is None:
            return {}
        data = {
            "urn": entity.urn,
            "name": entity.name,
            "type": entity.type,
            "subType": entity.sub_type,
            "tags": entity.tags,
            "owners": entity.owners,
        }
        return {k: v for k, v in data.items() if v}

    def _describe_hop(self, hop: Hop, direction: str) -> Dict[str, Any]:
        other = hop.target if direction == "downstream" else hop.source
        entity = self.catalog.get_entity(other)
        data = self._describe(entity) or {"urn": other}
        if hop.transform:
            data["transform"] = hop.transform
        if hop.query:
            data["sql"] = " ".join(hop.query.split())[:240]
        data["lineageLevel"] = hop.level
        return data

    def _build_violation(self, args: Dict[str, Any], rule: str, severity: str) -> Optional[Violation]:
        """Turn a reported finding into a Violation, refusing invented URNs."""
        subject = self.catalog.get_entity(args["subject_urn"])
        if subject is None:
            return None

        chain = [u for u in (args.get("path_urns") or []) if isinstance(u, str)]
        path: Optional[LineagePath] = None
        if len(chain) > 1:
            nodes = [self.catalog.get_entity(u) or Entity(urn=u) for u in chain]
            hops = [
                Hop(source=chain[i], target=chain[i + 1], level="column" if urns.is_field(chain[i]) else "table")
                for i in range(len(chain) - 1)
            ]
            path = LineagePath(nodes=nodes, hops=hops)

        sink_urn = args.get("sink_urn") or (chain[-1] if len(chain) > 1 else None)
        sink = self.catalog.get_entity(sink_urn) if sink_urn else None

        return Violation(
            policy_id="freeform",
            severity=severity,
            subject=subject,
            message=args["message"],
            path=path,
            sink=sink,
            evidence=[f"rule: {rule}"] + ([path.render(" -> ")] if path else []),
            owners=subject.owners or (sink.owners if sink else []),
            rationale=args.get("rationale"),
            engine="agent",
            remediation="Reviewed by the agentic engine. Promote this rule to a policy file "
            "under policies/ to have it enforced on every scan.",
        )

    def investigate(self, rule: str, severity: str = "medium") -> PolicyResult:
        """Run the tool-use loop for a rule the DSL could not express."""
        client = self._connect()
        result = PolicyResult(
            policy_id="freeform",
            description=rule,
            severity=severity,
            engine="agent",
        )
        started = time.perf_counter()
        found: List[Violation] = []

        messages: List[Dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    f"Rule to enforce: {rule}\n\n"
                    "Investigate the catalog and report every violation. "
                    "Call finish when you are done."
                ),
            }
        ]

        try:
            for step in range(self.max_steps):
                response = client.messages.create(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=INVESTIGATE_SYSTEM,
                    thinking={"type": "adaptive"},
                    output_config={"effort": self.effort},
                    tools=READ_TOOLS,
                    messages=messages,
                )

                if response.stop_reason == "refusal":
                    result.error = "the model declined to investigate this rule"
                    break

                messages.append({"role": "assistant", "content": response.content})
                calls = [b for b in response.content if b.type == "tool_use"]
                if not calls:
                    text = " ".join(b.text for b in response.content if b.type == "text")
                    result.notes.append(f"agent finished: {text.strip()[:300]}")
                    break

                results_block: List[Dict[str, Any]] = []
                finished = False
                for call in calls:
                    args = dict(call.input or {})
                    try:
                        output = self._dispatch(call.name, args, found, rule, severity)
                        is_error = False
                    except Exception as exc:  # a bad read must not kill the loop
                        output = f"Tool error: {type(exc).__name__}: {exc}"
                        is_error = True
                    self.transcript.append(
                        {"phase": "investigate", "step": step, "tool": call.name, "input": args}
                    )
                    results_block.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "content": output,
                            **({"is_error": True} if is_error else {}),
                        }
                    )
                    if call.name == "finish":
                        finished = True
                        result.notes.append(f"agent summary: {args.get('summary', '').strip()[:300]}")

                messages.append({"role": "user", "content": results_block})
                if finished:
                    break
            else:
                result.notes.append(
                    f"agent hit its {self.max_steps}-step budget; findings so far are reported"
                )
        except AgentUnavailable:
            raise
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"

        result.violations = found
        result.subjects_scanned = sum(
            1 for t in self.transcript if t.get("tool") in {"search", "list_columns"}
        )
        result.paths_walked = sum(1 for t in self.transcript if t.get("tool") == "get_lineage")
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result

    # ---------------------------------------------------------------- run

    def run(self, rule: str, severity: str = "medium") -> PolicyResult:
        """Compile the rule if possible, otherwise investigate it."""
        policy = self.compile(rule)
        if policy is not None:
            policy.severity = severity if severity != "medium" else policy.severity
            result = TemplateEngine(self.catalog).evaluate(policy)
            result.engine = "agent"
            result.description = f"{rule} (compiled to `{policy.id}`)"
            result.notes.insert(
                0,
                f"agent compiled this rule into the policy DSL as `{policy.id}`: {policy.summary()}",
            )
            for violation in result.violations:
                violation.engine = "agent"
                violation.rationale = (
                    "Compiled from the plain-English rule into a deterministic policy, then "
                    "evaluated by the template engine. Evidence below is the actual graph walk."
                )
            return result
        return self.investigate(rule, severity=severity)

    def policy_yaml(self) -> Optional[str]:
        """The compiled policy, ready to save into ``policies/``."""
        if self.compiled_policy is None:
            return None
        policy = self.compiled_policy
        data = {
            "id": policy.id,
            "severity": policy.severity,
            "description": policy.description,
            "subject": policy.subject.to_yaml_dict(),
            "condition": policy.condition.to_yaml_dict(),
            "on_violation": policy.on_violation,
        }
        return yaml.safe_dump([data], sort_keys=False, default_flow_style=False)
