"""Core data types shared by the readers, the engines and the write-back layer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import urns

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _clean(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


@dataclass
class Entity:
    """Any node in the catalog: dataset, dashboard, chart, data job, column."""

    urn: str
    type: str = ""
    name: str = ""
    platform: Optional[str] = None
    sub_type: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    terms: List[str] = field(default_factory=list)
    owners: List[str] = field(default_factory=list)
    domain: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.type:
            self.type = urns.entity_type(self.urn)
        if not self.name:
            self.name = urns.qualified_name(self.urn)
        if self.platform is None:
            self.platform = urns.platform_of(self.urn)

    @property
    def is_column(self) -> bool:
        return self.type == "schemaField"

    @property
    def short_name(self) -> str:
        return urns.short_name(self.urn)

    def has_tag(self, name: str) -> bool:
        want = urns.tag_name(name).lower()
        return any(urns.tag_name(t).lower() == want for t in self.tags)

    def has_term(self, name: str) -> bool:
        want = urns.tag_name(name).lower()
        return any(urns.tag_name(t).lower() == want for t in self.terms)

    def type_matches(self, wanted: str) -> bool:
        """Match on entity type or DataHub sub-type, case-insensitively."""
        want = wanted.strip().lower()
        if self.type.lower() == want:
            return True
        if (self.sub_type or "").lower() == want:
            return True
        return False

    def to_dict(self) -> Dict[str, Any]:
        return _clean(
            {
                "urn": self.urn,
                "type": self.type,
                "name": self.name,
                "platform": self.platform,
                "subType": self.sub_type,
                "tags": self.tags,
                "terms": self.terms,
                "owners": self.owners,
                "domain": self.domain,
            }
        )


@dataclass
class Hop:
    """One edge of a lineage path."""

    source: str
    target: str
    transform: Optional[str] = None
    query: Optional[str] = None
    via: Optional[str] = None  # data job / task URN when the platform reports one
    level: str = "column"  # column | table -- which lineage granularity proved it

    def to_dict(self) -> Dict[str, Any]:
        return _clean(
            {
                "source": self.source,
                "target": self.target,
                "transform": self.transform,
                "via": self.via,
                "query": self.query,
                "level": self.level,
            }
        )


@dataclass
class LineagePath:
    """An ordered walk through the graph, ``nodes[0]`` -> ``nodes[-1]``."""

    nodes: List[Entity]
    hops: List[Hop] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def length(self) -> int:
        """Hop count. A path of 5 nodes is a 4-hop path."""
        return max(len(self.nodes) - 1, 0)

    @property
    def source(self) -> Entity:
        return self.nodes[0]

    @property
    def sink(self) -> Entity:
        return self.nodes[-1]

    @property
    def urn_chain(self) -> List[str]:
        return [n.urn for n in self.nodes]

    def render(self, arrow: str = " -> ") -> str:
        return arrow.join(urns.short_name(n.urn) for n in self.nodes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hops": self.length,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [h.to_dict() for h in self.hops],
            "rendered": self.render(),
            "notes": self.notes,
        }


@dataclass
class WriteBack:
    """A record of one thing Kestrel wrote (or would write) into the catalog."""

    kind: str  # tag | structured_property | document | pr | notify
    target_urn: str
    detail: str
    applied: bool = False
    dry_run: bool = False
    error: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return _clean(
            {
                "kind": self.kind,
                "target": self.target_urn,
                "detail": self.detail,
                "applied": self.applied,
                "dryRun": self.dry_run,
                "error": self.error,
                "payload": self.payload or None,
            }
        )


@dataclass
class Violation:
    """One policy failing on one subject, with the evidence that proves it."""

    policy_id: str
    severity: str
    subject: Entity
    message: str
    path: Optional[LineagePath] = None
    sink: Optional[Entity] = None
    evidence: List[str] = field(default_factory=list)
    queries: List[str] = field(default_factory=list)
    owners: List[str] = field(default_factory=list)
    remediation: Optional[str] = None
    detected_at: str = field(default_factory=utc_now)
    engine: str = "template"
    rationale: Optional[str] = None  # the agent's reasoning, for freeform rules
    writebacks: List[WriteBack] = field(default_factory=list)

    @property
    def id(self) -> str:
        """Stable id, so re-running a scan does not create duplicate findings."""
        seed = f"{self.policy_id}|{self.subject.urn}|{self.sink.urn if self.sink else ''}"
        return f"{self.policy_id}-{hashlib.sha1(seed.encode()).hexdigest()[:8]}"

    @property
    def severity_rank(self) -> int:
        return SEVERITY_ORDER.get(self.severity.lower(), 99)

    @property
    def title(self) -> str:
        subject = urns.qualified_name(self.subject.urn)
        if self.sink is not None:
            return f"{subject} -> {urns.short_name(self.sink.urn)}"
        return subject

    def to_dict(self) -> Dict[str, Any]:
        return _clean(
            {
                "id": self.id,
                "policyId": self.policy_id,
                "severity": self.severity,
                "engine": self.engine,
                "title": self.title,
                "message": self.message,
                "subject": self.subject.to_dict(),
                "sink": self.sink.to_dict() if self.sink else None,
                "path": self.path.to_dict() if self.path else None,
                "evidence": self.evidence,
                "queries": self.queries,
                "owners": self.owners,
                "remediation": self.remediation,
                "rationale": self.rationale,
                "detectedAt": self.detected_at,
                "writebacks": [w.to_dict() for w in self.writebacks],
            }
        )


@dataclass
class PolicyResult:
    """Outcome of evaluating one policy: what it looked at, what it found."""

    policy_id: str
    description: str
    severity: str
    engine: str
    subjects_scanned: int = 0
    paths_walked: int = 0
    violations: List[Violation] = field(default_factory=list)
    error: Optional[str] = None
    duration_ms: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.error is None and not self.violations

    def to_dict(self) -> Dict[str, Any]:
        return _clean(
            {
                "policyId": self.policy_id,
                "description": self.description,
                "severity": self.severity,
                "engine": self.engine,
                "subjectsScanned": self.subjects_scanned,
                "pathsWalked": self.paths_walked,
                "violationCount": len(self.violations),
                "violations": [v.to_dict() for v in self.violations],
                "error": self.error,
                "durationMs": self.duration_ms,
                "notes": self.notes,
            }
        )


@dataclass
class ScanReport:
    """Everything one ``kestrel scan`` produced -- the JSON the web UI reads."""

    run_id: str
    started_at: str
    mode: str  # live | offline
    target: Optional[str] = None
    finished_at: Optional[str] = None
    results: List[PolicyResult] = field(default_factory=list)
    writeback_enabled: bool = False
    dry_run: bool = True
    warnings: List[str] = field(default_factory=list)
    datahub_url: Optional[str] = None

    @property
    def violations(self) -> List[Violation]:
        out: List[Violation] = []
        for r in self.results:
            out.extend(r.violations)
        return sorted(out, key=lambda v: (v.severity_rank, v.policy_id, v.title))

    @property
    def severity_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for v in self.violations:
            counts[v.severity] = counts.get(v.severity, 0) + 1
        return counts

    @property
    def writebacks(self) -> List[WriteBack]:
        return [w for v in self.violations for w in v.writebacks]

    @property
    def exit_code(self) -> int:
        """0 clean, 1 violations found, 2 a policy errored -- CI-friendly."""
        if any(r.error for r in self.results):
            return 2
        return 1 if self.violations else 0

    def to_dict(self) -> Dict[str, Any]:
        wb = self.writebacks
        return _clean(
            {
                "runId": self.run_id,
                "mode": self.mode,
                "target": self.target,
                "datahubUrl": self.datahub_url,
                "startedAt": self.started_at,
                "finishedAt": self.finished_at,
                "writebackEnabled": self.writeback_enabled,
                "dryRun": self.dry_run,
                "summary": {
                    "policies": len(self.results),
                    "violations": len(self.violations),
                    "subjectsScanned": sum(r.subjects_scanned for r in self.results),
                    "pathsWalked": sum(r.paths_walked for r in self.results),
                    "bySeverity": self.severity_counts,
                    "writebacks": len(wb),
                    "writebacksApplied": sum(1 for w in wb if w.applied),
                },
                "results": [r.to_dict() for r in self.results],
                "warnings": self.warnings,
            }
        )
