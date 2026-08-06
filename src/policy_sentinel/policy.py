"""Policy-as-code: the YAML dialect and its loader.

A policy has three parts:

* ``subject``   -- which entities the rule is about (the search)
* ``condition`` -- what must not be true of them (the graph walk)
* ``on_violation`` -- what to write back when it is

Keeping those separate is what lets one generic evaluator run every shipped
template, and what lets the agentic engine emit a policy of the same shape when
it interprets a plain-English rule.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import yaml

from .models import SEVERITY_ORDER

VALID_ACTIONS = {"tag", "structured_property", "document", "pr", "notify"}

SUBJECT_KEYS = {
    "entity_type",
    "has_tag",
    "has_any_tag",
    "has_term",
    "missing_tag",
    "name_matches",
    "platform",
    "domain",
    "sub_type",
    "search",
    "limit",
}

CONDITION_KEYS = {
    "lineage_reaches_type",
    "lineage_reaches_tag",
    "upstream_has_tag",
    "missing_owner",
    "missing_tag",
    "direction",
    "max_hops",
    "without_step",
    "without_tag",
    "require_tag_on_subject",
}

PRIMARY_CONDITIONS = (
    "lineage_reaches_type",
    "lineage_reaches_tag",
    "upstream_has_tag",
    "missing_owner",
    "missing_tag",
)


class PolicyError(ValueError):
    """Raised for a malformed policy file -- always names the offending id."""


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(v) for v in value]
    return [str(value)]


@dataclass
class Subject:
    """Which entities a policy is about."""

    entity_type: str = "dataset"
    has_tag: List[str] = field(default_factory=list)
    has_any_tag: List[str] = field(default_factory=list)
    has_term: List[str] = field(default_factory=list)
    missing_tag: List[str] = field(default_factory=list)
    name_matches: Optional[str] = None
    platform: List[str] = field(default_factory=list)
    domain: Optional[str] = None
    sub_type: Optional[str] = None
    search: Optional[str] = None
    limit: int = 200

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], policy_id: str) -> "Subject":
        unknown = set(raw) - SUBJECT_KEYS
        if unknown:
            raise PolicyError(
                f"policy '{policy_id}': unknown subject key(s) {sorted(unknown)}; "
                f"valid keys are {sorted(SUBJECT_KEYS)}"
            )
        entity_type = str(raw.get("entity_type", "dataset"))
        if entity_type.lower() in {"column", "field", "schemafield"}:
            entity_type = "schemaField"
        return cls(
            entity_type=entity_type,
            has_tag=_as_list(raw.get("has_tag")),
            has_any_tag=_as_list(raw.get("has_any_tag")),
            has_term=_as_list(raw.get("has_term")),
            missing_tag=_as_list(raw.get("missing_tag")),
            name_matches=raw.get("name_matches"),
            platform=_as_list(raw.get("platform")),
            domain=raw.get("domain"),
            sub_type=raw.get("sub_type"),
            search=raw.get("search"),
            limit=int(raw.get("limit", 200)),
        )

    @property
    def is_column_level(self) -> bool:
        return self.entity_type == "schemaField"

    def to_query(self) -> str:
        """Render the subject as a DataHub ``/q`` search string.

        ``search:`` overrides everything, which is the escape hatch for rules the
        structured keys cannot express.
        """
        if self.search:
            return self.search
        clauses: List[str] = []
        for tag in self.has_tag:
            clauses.append(f"tags:{tag}")
        if self.has_any_tag:
            any_of = " OR ".join(f"tags:{t}" for t in self.has_any_tag)
            clauses.append(f"({any_of})")
        for term in self.has_term:
            clauses.append(f"glossaryTerms:{term}")
        for plat in self.platform:
            clauses.append(f"platform:{plat}")
        if self.domain:
            clauses.append(f"domains:{self.domain}")
        if self.sub_type:
            clauses.append(f'typeNames:"{self.sub_type}"')
        return " AND ".join(clauses) if clauses else "*"

    def to_dataset_query(self) -> str:
        """Query used to find *datasets worth opening* for a column-level rule.

        Columns are not top-level search hits, so a column rule first finds
        datasets that carry the tag either on themselves or on any of their
        fields (``fieldTags`` is a real DataHub index field), then filters the
        columns of those datasets with :meth:`matches`.
        """
        if self.search:
            return self.search
        if not self.is_column_level:
            return self.to_query()
        clauses: List[str] = []
        for tag in self.has_tag:
            clauses.append(f"(tags:{tag} OR fieldTags:{tag})")
        if self.has_any_tag:
            any_of = " OR ".join(f"tags:{t} OR fieldTags:{t}" for t in self.has_any_tag)
            clauses.append(f"({any_of})")
        for term in self.has_term:
            clauses.append(f"(glossaryTerms:{term} OR fieldGlossaryTerms:{term})")
        for plat in self.platform:
            clauses.append(f"platform:{plat}")
        if self.domain:
            clauses.append(f"domains:{self.domain}")
        return " AND ".join(clauses) if clauses else "*"

    def matches(self, entity: Any) -> bool:
        """Structural re-check of a candidate returned by search.

        Search is a filter, not a guarantee -- and for column rules it only ever
        narrowed us to the right *datasets*. This is what actually decides.
        """
        if not entity.type_matches(self.entity_type):
            return False
        if self.sub_type and (entity.sub_type or "").lower() != self.sub_type.lower():
            return False
        if any(not entity.has_tag(t) for t in self.has_tag):
            return False
        if self.has_any_tag and not any(entity.has_tag(t) for t in self.has_any_tag):
            return False
        if any(not entity.has_term(t) for t in self.has_term):
            return False
        if any(entity.has_tag(t) for t in self.missing_tag):
            return False
        if self.platform and (entity.platform or "") not in self.platform:
            return False
        if self.domain and (entity.domain or "") != self.domain:
            return False
        if self.name_matches and not re.search(self.name_matches, entity.name, re.IGNORECASE):
            return False
        return True

    def describe(self) -> str:
        bits: List[str] = []
        if self.has_tag:
            bits.append("tagged " + "+".join(self.has_tag))
        if self.has_any_tag:
            bits.append("tagged any of " + "/".join(self.has_any_tag))
        if self.has_term:
            bits.append("term " + "/".join(self.has_term))
        if self.sub_type:
            bits.append(f"sub-type {self.sub_type}")
        if self.platform:
            bits.append("on " + "/".join(self.platform))
        noun = "columns" if self.is_column_level else f"{self.entity_type}s"
        return f"{noun} " + (", ".join(bits) if bits else "(all)")

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}

    def to_yaml_dict(self) -> Dict[str, Any]:
        """Back to policy-file keys, so a compiled rule can be saved and re-run."""
        out: Dict[str, Any] = {
            "entity_type": "column" if self.is_column_level else self.entity_type
        }
        for key in ("has_tag", "has_any_tag", "has_term", "missing_tag", "platform"):
            value = getattr(self, key)
            if value:
                out[key] = value[0] if len(value) == 1 else value
        for key in ("name_matches", "domain", "sub_type", "search"):
            if getattr(self, key):
                out[key] = getattr(self, key)
        if self.limit != 200:
            out["limit"] = self.limit
        return out


@dataclass
class Condition:
    """What must not be true of the subject."""

    kind: str
    reaches_type: List[str] = field(default_factory=list)
    reaches_tag: List[str] = field(default_factory=list)
    upstream_tag: List[str] = field(default_factory=list)
    missing_tag: List[str] = field(default_factory=list)
    direction: str = "downstream"
    max_hops: int = 5
    without_step: List[str] = field(default_factory=list)
    without_tag: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], policy_id: str) -> "Condition":
        unknown = set(raw) - CONDITION_KEYS
        if unknown:
            raise PolicyError(
                f"policy '{policy_id}': unknown condition key(s) {sorted(unknown)}; "
                f"valid keys are {sorted(CONDITION_KEYS)}"
            )
        primary = [k for k in PRIMARY_CONDITIONS if k in raw]
        if len(primary) != 1:
            raise PolicyError(
                f"policy '{policy_id}': condition needs exactly one of "
                f"{list(PRIMARY_CONDITIONS)}, got {primary or 'none'}"
            )
        kind = primary[0]
        direction = str(raw.get("direction", "upstream" if kind == "upstream_has_tag" else "downstream"))
        if direction not in {"downstream", "upstream"}:
            raise PolicyError(f"policy '{policy_id}': direction must be downstream or upstream")
        return cls(
            kind=kind,
            reaches_type=_as_list(raw.get("lineage_reaches_type")),
            reaches_tag=_as_list(raw.get("lineage_reaches_tag")),
            upstream_tag=_as_list(raw.get("upstream_has_tag")),
            missing_tag=_as_list(raw.get("missing_tag")),
            direction=direction,
            max_hops=int(raw.get("max_hops", 5)),
            without_step=_as_list(raw.get("without_step")),
            without_tag=_as_list(raw.get("without_tag")),
        )

    @property
    def is_lineage(self) -> bool:
        return self.kind in {"lineage_reaches_type", "lineage_reaches_tag", "upstream_has_tag"}

    def describe(self) -> str:
        """Infinitive phrasing, so callers can render it as "must not <describe>"."""
        if self.kind == "lineage_reaches_type":
            base = f"reach a {'/'.join(self.reaches_type)} within {self.max_hops} hops"
        elif self.kind == "lineage_reaches_tag":
            base = f"reach anything tagged {'/'.join(self.reaches_tag)} within {self.max_hops} hops"
        elif self.kind == "upstream_has_tag":
            base = f"have an upstream tagged {'/'.join(self.upstream_tag)} within {self.max_hops} hops"
        elif self.kind == "missing_owner":
            base = "lack an owner"
        else:
            base = f"lack the tag {'/'.join(self.missing_tag)}"
        mitigations: List[str] = []
        if self.without_step:
            mitigations.append("no step matching " + "/".join(self.without_step))
        if self.without_tag:
            mitigations.append("no step tagged " + "/".join(self.without_tag))
        return base + (" with " + " and ".join(mitigations) if mitigations else "")

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v not in (None, [], "")}

    def to_yaml_dict(self) -> Dict[str, Any]:
        """Back to policy-file keys (the inverse of :meth:`from_dict`)."""
        primary: Dict[str, Any] = {}
        if self.kind == "missing_owner":
            primary["missing_owner"] = True
        else:
            values = {
                "lineage_reaches_type": self.reaches_type,
                "lineage_reaches_tag": self.reaches_tag,
                "upstream_has_tag": self.upstream_tag,
                "missing_tag": self.missing_tag,
            }[self.kind]
            primary[self.kind] = values[0] if len(values) == 1 else values

        default_direction = "upstream" if self.kind == "upstream_has_tag" else "downstream"
        if self.direction != default_direction:
            primary["direction"] = self.direction
        if self.is_lineage and self.max_hops != 5:
            primary["max_hops"] = self.max_hops
        for key, value in (("without_step", self.without_step), ("without_tag", self.without_tag)):
            if value:
                primary[key] = value[0] if len(value) == 1 else value
        return primary


@dataclass
class Policy:
    id: str
    description: str
    subject: Subject
    condition: Condition
    severity: str = "medium"
    enabled: bool = True
    on_violation: List[str] = field(default_factory=lambda: ["tag", "structured_property", "document"])
    tag_name: str = "policy-violation"
    remediation: Optional[str] = None
    source_file: Optional[str] = None
    engine: str = "template"

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], source: Optional[str] = None) -> "Policy":
        if not isinstance(raw, dict):
            raise PolicyError(f"expected a policy mapping, got {type(raw).__name__}")
        pid = str(raw.get("id") or "").strip()
        if not pid:
            raise PolicyError(f"policy in {source or '<inline>'} is missing an 'id'")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", pid):
            raise PolicyError(f"policy '{pid}': id must be kebab-case (a-z, 0-9, '-')")

        severity = str(raw.get("severity", "medium")).lower()
        if severity not in SEVERITY_ORDER:
            raise PolicyError(
                f"policy '{pid}': severity '{severity}' invalid; use one of {sorted(SEVERITY_ORDER)}"
            )

        if "subject" not in raw or "condition" not in raw:
            raise PolicyError(f"policy '{pid}': both 'subject' and 'condition' are required")

        actions = _as_list(raw.get("on_violation") or ["tag", "structured_property", "document"])
        bad = set(actions) - VALID_ACTIONS
        if bad:
            raise PolicyError(
                f"policy '{pid}': unknown on_violation action(s) {sorted(bad)}; "
                f"valid actions are {sorted(VALID_ACTIONS)}"
            )

        return cls(
            id=pid,
            description=str(raw.get("description", "")).strip(),
            subject=Subject.from_dict(raw.get("subject") or {}, pid),
            condition=Condition.from_dict(raw.get("condition") or {}, pid),
            severity=severity,
            enabled=bool(raw.get("enabled", True)),
            on_violation=actions,
            tag_name=str(raw.get("tag_name", "policy-violation")),
            remediation=raw.get("remediation"),
            source_file=source,
            engine=str(raw.get("engine", "template")),
        )

    def summary(self) -> str:
        return f"{self.subject.describe()} must not {self.condition.describe()}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "severity": self.severity,
            "engine": self.engine,
            "subject": self.subject.to_dict(),
            "condition": self.condition.to_dict(),
            "on_violation": self.on_violation,
            "summary": self.summary(),
        }


def _documents(path: Path) -> Iterable[Any]:
    text = path.read_text(encoding="utf-8")
    for doc in yaml.safe_load_all(text):
        if doc is not None:
            yield doc


def load_policy_file(path: Path) -> List[Policy]:
    """Accepts a bare list, a single mapping, or ``{policies: [...]}``."""
    policies: List[Policy] = []
    for doc in _documents(path):
        if isinstance(doc, dict) and "policies" in doc:
            doc = doc["policies"]
        entries = doc if isinstance(doc, list) else [doc]
        for entry in entries:
            policies.append(Policy.from_dict(entry, source=path.name))
    return policies


def load_policies(
    location: str | Path,
    only: Optional[Sequence[str]] = None,
    include_disabled: bool = False,
) -> List[Policy]:
    """Load every policy under a file or directory, deduplicated by id."""
    path = Path(location)
    if not path.exists():
        raise PolicyError(f"policy path not found: {path}")

    files = (
        sorted(p for p in path.rglob("*") if p.suffix.lower() in {".yaml", ".yml"})
        if path.is_dir()
        else [path]
    )
    if not files:
        raise PolicyError(f"no .yaml policy files found under {path}")

    loaded: List[Policy] = []
    seen: Dict[str, str] = {}
    for f in files:
        for policy in load_policy_file(f):
            if policy.id in seen:
                raise PolicyError(
                    f"duplicate policy id '{policy.id}' in {f.name} "
                    f"(already defined in {seen[policy.id]})"
                )
            seen[policy.id] = f.name
            loaded.append(policy)

    if not include_disabled:
        loaded = [p for p in loaded if p.enabled]
    if only:
        wanted = {o.strip() for o in only if o.strip()}
        missing = wanted - {p.id for p in loaded}
        if missing:
            raise PolicyError(f"no such policy: {', '.join(sorted(missing))}")
        loaded = [p for p in loaded if p.id in wanted]
    return loaded
