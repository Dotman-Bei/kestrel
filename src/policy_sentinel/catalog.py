"""The catalog interface every engine reads and writes through.

Two implementations satisfy it:

* :class:`policy_sentinel.mcp_client.McpCatalog` -- the real thing, driving
  ``mcp-server-datahub`` over stdio against a live DataHub.
* :class:`policy_sentinel.fixture_client.FixtureCatalog` -- the same surface over
  a local JSON graph, so the engines, the tests and the demo report can run with
  no instance up.

Engines only ever see this interface, which is why the deterministic core has no
network code in it at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Iterable, List, Optional, Sequence

from .models import Entity, Hop

if TYPE_CHECKING:  # pragma: no cover
    from .policy import Subject


class CatalogError(RuntimeError):
    """A read or write against the catalog failed."""


class Catalog:
    """Abstract read/write surface over a metadata graph."""

    #: ``live`` or ``offline`` -- surfaced in the report so nobody mistakes a
    #: fixture run for a real one.
    mode: str = "unknown"
    #: Set False when mutation tools are unavailable (``TOOLS_IS_MUTATION_ENABLED``
    #: unset on the server); the write-back layer degrades to dry-run.
    writes_enabled: bool = False
    base_url: Optional[str] = None

    # ---------------------------------------------------------------- reads

    def search(
        self,
        query: str,
        entity_types: Optional[Sequence[str]] = None,
        limit: int = 200,
    ) -> List[Entity]:
        raise NotImplementedError

    def get_entity(self, urn: str) -> Optional[Entity]:
        return self.get_entities([urn]).get(urn)

    def get_entities(self, urns: Sequence[str]) -> Dict[str, Entity]:
        raise NotImplementedError

    def neighbors(self, urn: str, direction: str = "downstream") -> List[Hop]:
        """One hop out from ``urn``. The graph walker calls this repeatedly."""
        raise NotImplementedError

    def list_schema_fields(self, dataset_urn: str) -> List[Entity]:
        raise NotImplementedError

    def get_dataset_queries(self, urn: str, limit: int = 3) -> List[str]:
        """Real SQL referencing the asset -- the evidence in a violation doc."""
        return []

    # ------------------------------------------------------------- resolution

    def find_subjects(self, subject: "Subject") -> List[Entity]:
        """Resolve a policy's ``subject`` block to concrete entities.

        Column-level rules take the two-step route: search for datasets that
        carry the tag on themselves *or* on any field, then open each one and
        filter its columns. Columns are not top-level search hits, so there is
        no single-query shortcut here.
        """
        if subject.is_column_level:
            datasets = self.search(
                subject.to_dataset_query(), entity_types=["dataset"], limit=subject.limit
            )
            fields: List[Entity] = []
            for dataset in datasets:
                for column in self.list_schema_fields(dataset.urn):
                    if subject.matches(column):
                        fields.append(column)
                    if len(fields) >= subject.limit:
                        return fields
            return fields

        hits = self.search(
            subject.to_query(), entity_types=[subject.entity_type], limit=subject.limit
        )
        return [e for e in hits if subject.matches(e)][: subject.limit]

    # --------------------------------------------------------------- writes

    def add_tags(self, urn: str, tags: Sequence[str]) -> None:
        raise NotImplementedError

    def remove_tags(self, urn: str, tags: Sequence[str]) -> None:
        raise NotImplementedError

    def add_structured_properties(self, urn: str, properties: Dict[str, object]) -> None:
        raise NotImplementedError

    def save_document(
        self,
        title: str,
        content: str,
        related_urns: Optional[Sequence[str]] = None,
        doc_id: Optional[str] = None,
    ) -> Optional[str]:
        raise NotImplementedError

    # ------------------------------------------------------------ lifecycle

    def close(self) -> None:
        return None

    def __enter__(self) -> "Catalog":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def dedupe_entities(entities: Iterable[Entity]) -> List[Entity]:
    seen: Dict[str, Entity] = {}
    for e in entities:
        if e.urn not in seen:
            seen[e.urn] = e
    return list(seen.values())
