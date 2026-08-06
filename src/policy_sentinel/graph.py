"""Multi-hop lineage traversal -- the part per-entity metadata tests can't do.

A Metadata Test asks "does *this* table have an owner?". Everything in this
module exists to ask a different shape of question: "starting at this column,
does *any* path through the graph end somewhere it shouldn't, and did it pass
through anything that would make that acceptable?"

Design notes:

* Breadth-first, so the path reported for a violation is the shortest one --
  the most legible evidence, not the first one a DFS stumbled into.
* Cycle-safe per path (a node may appear in two different paths, never twice in
  one), with a global node budget so a dense graph cannot hang a scan.
* When a column has no column-level lineage, the walk falls back to its parent
  dataset's table-level lineage and records a note. Sample datapacks vary in how
  deep column lineage is populated; a table-level path still proves the flow,
  and the report says which granularity proved it.
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Sequence

from . import urns
from .catalog import Catalog
from .models import Entity, Hop, LineagePath

TABLE_FALLBACK_NOTE = "column lineage unavailable at this hop; followed table-level lineage"


@dataclass
class WalkStats:
    paths_walked: int = 0
    nodes_expanded: int = 0
    fallbacks: int = 0
    truncated: bool = False


@dataclass
class LineageWalker:
    """Enumerates lineage paths out of a starting entity."""

    catalog: Catalog
    max_hops: int = 5
    max_paths: int = 400
    node_budget: int = 3000
    stats: WalkStats = field(default_factory=WalkStats)
    _entity_cache: Dict[str, Entity] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------ util

    def resolve(self, urn: str) -> Entity:
        """Entity metadata for a URN, cached across policies in one scan."""
        cached = self._entity_cache.get(urn)
        if cached is not None:
            return cached
        entity = self.catalog.get_entity(urn) or Entity(urn=urn)
        self._entity_cache[urn] = entity
        return entity

    def prime(self, entities: Sequence[Entity]) -> None:
        for e in entities:
            self._entity_cache.setdefault(e.urn, e)

    def _hops_out(self, urn: str, direction: str) -> List[Hop]:
        """Neighbours of ``urn``, falling back to table level for bare columns."""
        hops = self.catalog.neighbors(urn, direction)
        if hops or not urns.is_field(urn):
            return hops

        parent = urns.dataset_of_field(urn)
        if not parent:
            return []
        parent_hops = self.catalog.neighbors(parent, direction)
        if not parent_hops:
            return []
        self.stats.fallbacks += 1
        # Re-anchor the parent's edges onto the column we are actually walking,
        # so the path stays continuous from the column the policy selected.
        return [
            Hop(
                source=urn,
                target=h.target,
                transform=h.transform,
                query=h.query,
                via=h.via,
                level="table",
            )
            for h in parent_hops
        ]

    # ------------------------------------------------------------------ walk

    def iter_paths(self, start: Entity, direction: str = "downstream") -> Iterator[LineagePath]:
        """Yield every path out of ``start``, shortest first.

        Each yielded path is a complete candidate: a caller testing "does this
        reach a Dashboard" checks ``path.sink`` and stops at the first match,
        which is therefore the shortest such path.
        """
        queue: deque[LineagePath] = deque([LineagePath(nodes=[start], hops=[])])
        emitted = 0

        while queue:
            path = queue.popleft()
            if path.length >= self.max_hops:
                continue
            if self.stats.nodes_expanded >= self.node_budget:
                self.stats.truncated = True
                return

            tail = path.nodes[-1]
            self.stats.nodes_expanded += 1
            seen = set(path.urn_chain)

            for hop in self._hops_out(tail.urn, direction):
                nxt_urn = hop.target if direction == "downstream" else hop.source
                if nxt_urn in seen:
                    continue
                notes = list(path.notes)
                if hop.level == "table" and TABLE_FALLBACK_NOTE not in notes:
                    notes.append(TABLE_FALLBACK_NOTE)
                extended = LineagePath(
                    nodes=path.nodes + [self.resolve(nxt_urn)],
                    hops=path.hops + [hop],
                    notes=notes,
                )
                self.stats.paths_walked += 1
                emitted += 1
                yield extended
                if emitted >= self.max_paths:
                    self.stats.truncated = True
                    return
                queue.append(extended)

    def find_path(
        self,
        start: Entity,
        matches: "PathMatcher",
        direction: str = "downstream",
    ) -> Optional[LineagePath]:
        """Shortest unmitigated path satisfying ``matches``, or None."""
        for path in self.iter_paths(start, direction):
            if matches.sink_matches(path.sink) and not matches.mitigation(path):
                return path
        return None

    def first_mitigated(
        self,
        start: Entity,
        matches: "PathMatcher",
        direction: str = "downstream",
    ) -> Optional[str]:
        """Why a reaching path was *not* reported -- kept for the scan notes."""
        for path in self.iter_paths(start, direction):
            if matches.sink_matches(path.sink):
                reason = matches.mitigation(path)
                if reason:
                    return reason
        return None


@dataclass
class PathMatcher:
    """Decides which sinks are interesting and which paths are excused."""

    sink_types: Sequence[str] = ()
    sink_tags: Sequence[str] = ()
    without_step: Sequence[str] = ()
    without_tag: Sequence[str] = ()

    def sink_matches(self, node: Entity) -> bool:
        if self.sink_types and any(node.type_matches(t) for t in self.sink_types):
            return True
        if self.sink_tags and any(node.has_tag(t) for t in self.sink_tags):
            return True
        return False

    def mitigation(self, path: LineagePath) -> Optional[str]:
        """A human-readable reason the path is acceptable, or None.

        Intermediate nodes are ``nodes[1:-1]`` -- the subject itself cannot
        launder its own data, and the sink is the thing we are objecting to.
        Hop transforms and SQL are checked across every hop, because a masking
        step often lives in the transform rather than in a node name.
        """
        for pattern in self.without_step:
            rx = re.compile(pattern, re.IGNORECASE)
            for node in path.nodes[1:-1]:
                haystack = " ".join(
                    filter(None, [node.name, urns.qualified_name(node.urn), node.sub_type])
                )
                if rx.search(haystack):
                    return f"passes through masking step '{node.short_name}'"
            for hop in path.hops:
                blob = " ".join(filter(None, [hop.transform, hop.query, hop.via or ""]))
                if blob and rx.search(blob):
                    label = hop.transform or urns.short_name(hop.via or hop.target)
                    return f"transform '{label}' matches '{pattern}'"

        for tag in self.without_tag:
            for node in path.nodes[1:-1]:
                if node.has_tag(tag):
                    return f"intermediate '{node.short_name}' is tagged {urns.tag_name(tag)}"
        return None
