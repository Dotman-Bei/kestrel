"""The deterministic engine: one generic evaluator, driven by the policy YAML.

Everything here is LLM-free by design. The headline demo runs on this path, so
it must produce the same findings on every run, and it must be explainable line
by line -- each violation carries the exact hops that proved it.

The agentic engine (``engine_agent``) does not replace this; it *compiles down*
to the same :class:`~policy_sentinel.policy.Policy` shape and hands it back here
for evaluation, so a freeform rule is evidenced exactly like a shipped one.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional

from . import urns
from .catalog import Catalog
from .graph import LineageWalker, PathMatcher
from .models import Entity, LineagePath, PolicyResult, Violation
from .policy import Policy

#: Alternations longer than this get summarised rather than dumped verbatim.
_MAX_ALTERNATIVES_SHOWN = 3


def _humanize_patterns(patterns: List[str]) -> str:
    """Render `without_step` regexes as prose.

    A violation message is read by a person, often in a UI headline. Dumping
    `mask|masked|hash|sha2|redact|anonymi[sz]|tokeni[sz]` there is technically
    accurate and completely unreadable, so show the first few alternatives and
    say how many more there are. The full pattern is still in the policy file.
    """
    alternatives: List[str] = []
    for pattern in patterns:
        for part in pattern.split("|"):
            cleaned = re.sub(r"[\[\]()?*+^$\\]", "", part).strip()
            if not cleaned:
                continue
            # "mask" and "masked" say the same thing to a reader; keep the stem.
            if any(cleaned.startswith(seen) for seen in alternatives):
                continue
            alternatives = [a for a in alternatives if not a.startswith(cleaned)]
            alternatives.append(cleaned)
    if not alternatives:
        return "matching"
    shown = alternatives[:_MAX_ALTERNATIVES_SHOWN]
    label = "/".join(shown)
    remaining = len(alternatives) - len(shown)
    return f"{label} (+{remaining} more)" if remaining > 0 else label


DEFAULT_REMEDIATION = {
    "lineage_reaches_type": (
        "Insert a masking or hashing step upstream of the exposed asset, or drop the "
        "column from the downstream model. If the exposure is intentional and approved, "
        "tag the intermediate step so the policy recognises it as mitigated."
    ),
    "lineage_reaches_tag": (
        "Break the path or tag the intermediate transform that makes this flow acceptable."
    ),
    "upstream_has_tag": (
        "Fix or refresh the flagged upstream before it feeds a certified asset, or drop "
        "the certification until the upstream is healthy."
    ),
    "missing_owner": (
        "Assign a technical and a business owner in DataHub. Certification without an "
        "owner means nobody is accountable when this breaks."
    ),
    "missing_tag": "Apply the required tag, or remove the asset from the certified set.",
}


@dataclass
class TemplateEngine:
    """Evaluates every shipped policy shape against a catalog."""

    catalog: Catalog
    max_hops_cap: int = 8
    max_paths: int = 400
    collect_queries: bool = True
    walker: LineageWalker = field(init=False)

    def __post_init__(self) -> None:
        self.walker = LineageWalker(
            catalog=self.catalog, max_hops=self.max_hops_cap, max_paths=self.max_paths
        )

    # ------------------------------------------------------------ evaluate

    def evaluate(self, policy: Policy) -> PolicyResult:
        started = time.perf_counter()
        result = PolicyResult(
            policy_id=policy.id,
            description=policy.description or policy.summary(),
            severity=policy.severity,
            engine=policy.engine,
        )
        # The walker is shared across policies so its entity cache survives, which
        # means its counters are cumulative -- record a baseline and report deltas.
        before_paths = self.walker.stats.paths_walked
        before_fallbacks = self.walker.stats.fallbacks

        try:
            subjects = self.catalog.find_subjects(policy.subject)
            self.walker.prime(subjects)
            result.subjects_scanned = len(subjects)

            for subject in subjects:
                violation = self._check(policy, subject, result)
                if violation is not None:
                    result.violations.append(violation)

            result.paths_walked = self.walker.stats.paths_walked - before_paths
            fallbacks = self.walker.stats.fallbacks - before_fallbacks
            if fallbacks:
                result.notes.append(
                    f"{fallbacks} hop(s) used table-level lineage because "
                    "column-level lineage was not populated there"
                )
            if self.walker.stats.truncated:
                result.notes.append(
                    f"traversal hit its budget ({self.max_paths} paths / {self.walker.node_budget} "
                    "nodes); raise --max-paths for an exhaustive walk"
                )
        except Exception as exc:  # one bad policy must not sink the whole scan
            result.error = f"{type(exc).__name__}: {exc}"
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        return result

    # --------------------------------------------------------------- rules

    def _check(self, policy: Policy, subject: Entity, result: PolicyResult) -> Optional[Violation]:
        kind = policy.condition.kind
        if kind == "missing_owner":
            return self._check_missing_owner(policy, subject)
        if kind == "missing_tag":
            return self._check_missing_tag(policy, subject)
        return self._check_lineage(policy, subject, result)

    def _check_missing_owner(self, policy: Policy, subject: Entity) -> Optional[Violation]:
        if subject.owners:
            return None
        label = urns.qualified_name(subject.urn)
        marker = " / ".join(subject.tags[:3]) or subject.sub_type or subject.type
        return self._violation(
            policy,
            subject,
            message=(
                f"{label} is marked {marker} but has no owner. "
                "Nobody is accountable for it."
            ),
            evidence=[
                f"entity: {subject.urn}",
                f"tags: {', '.join(subject.tags) or 'none'}",
                "owners: none",
            ],
        )

    def _check_missing_tag(self, policy: Policy, subject: Entity) -> Optional[Violation]:
        missing = [t for t in policy.condition.missing_tag if not subject.has_tag(t)]
        if not missing:
            return None
        return self._violation(
            policy,
            subject,
            message=(
                f"{urns.qualified_name(subject.urn)} is missing required tag(s): "
                f"{', '.join(missing)}."
            ),
            evidence=[f"present tags: {', '.join(subject.tags) or 'none'}"],
        )

    def _check_lineage(
        self, policy: Policy, subject: Entity, result: PolicyResult
    ) -> Optional[Violation]:
        cond = policy.condition
        matcher = PathMatcher(
            sink_types=cond.reaches_type,
            sink_tags=cond.reaches_tag or cond.upstream_tag,
            without_step=cond.without_step,
            without_tag=cond.without_tag,
        )
        self.walker.max_hops = min(cond.max_hops, self.max_hops_cap)
        path = self.walker.find_path(subject, matcher, direction=cond.direction)

        if path is None:
            # Distinguish "no path" from "path, but excused" -- the second is a
            # policy *working*, and saying so out loud builds trust in the run.
            excuse = self.walker.first_mitigated(subject, matcher, direction=cond.direction)
            if excuse:
                note = f"{urns.short_name(subject.urn)}: path suppressed -- {excuse}"
                if note not in result.notes:
                    result.notes.append(note)
            return None

        return self._lineage_violation(policy, subject, path)

    def _lineage_violation(
        self, policy: Policy, subject: Entity, path: LineagePath
    ) -> Violation:
        cond = policy.condition
        sink = path.sink
        subject_label = urns.qualified_name(subject.urn)
        sink_label = urns.qualified_name(sink.urn)
        hop_word = "hop" if path.length == 1 else "hops"  # noun form: "2 hops upstream"

        if cond.kind == "upstream_has_tag":
            tag_label = "/".join(cond.upstream_tag)
            message = (
                f"{subject_label} is {'/'.join(policy.subject.has_tag) or 'certified'} but "
                f"depends on {sink_label}, which is tagged {tag_label}, "
                f"{path.length} {hop_word} upstream."
            )
        else:
            target_label = "/".join(cond.reaches_type or cond.reaches_tag)
            qualifier = ""
            if cond.without_step:
                qualifier = f", with no {_humanize_patterns(cond.without_step)} step on the way"
            elif cond.without_tag:
                qualifier = f", untouched by any {'/'.join(cond.without_tag)} step"
            message = (
                f"{subject_label} reaches {target_label} '{urns.short_name(sink.urn)}' "
                f"via a {path.length}-hop path{qualifier}."
            )

        evidence = self._path_evidence(path, cond.direction)
        queries = (
            self.catalog.get_dataset_queries(subject.urn, limit=2) if self.collect_queries else []
        )
        owners = subject.owners or sink.owners

        return self._violation(
            policy,
            subject,
            message=message,
            evidence=evidence,
            path=path,
            sink=sink,
            queries=queries,
            owners=owners,
        )

    @staticmethod
    def _path_evidence(path: LineagePath, direction: str) -> List[str]:
        arrow = "->" if direction == "downstream" else "<-"
        lines: List[str] = []
        for index, hop in enumerate(path.hops, start=1):
            src = urns.short_name(hop.source)
            dst = urns.short_name(hop.target)
            detail = f"hop {index}: {src} {arrow} {dst}"
            if hop.level == "table":
                detail += "  [table-level]"
            if hop.transform:
                detail += f"\n    transform: {hop.transform}"
            if hop.query:
                first_line = " ".join(hop.query.split())
                detail += f"\n    sql: {first_line[:160]}"
            lines.append(detail)
        lines.extend(path.notes)
        return lines

    @staticmethod
    def _violation(
        policy: Policy,
        subject: Entity,
        message: str,
        evidence: Optional[List[str]] = None,
        path: Optional[LineagePath] = None,
        sink: Optional[Entity] = None,
        queries: Optional[List[str]] = None,
        owners: Optional[List[str]] = None,
    ) -> Violation:
        return Violation(
            policy_id=policy.id,
            severity=policy.severity,
            subject=subject,
            message=message,
            path=path,
            sink=sink,
            evidence=evidence or [],
            queries=queries or [],
            owners=owners or subject.owners,
            remediation=policy.remediation or DEFAULT_REMEDIATION.get(policy.condition.kind),
            engine=policy.engine,
        )
