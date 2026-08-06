"""An offline catalog backed by a JSON graph.

Why this exists: the deterministic engine, the tests, the example outputs and the
web report all need a graph that behaves like DataHub without a DataHub. This
implements the same :class:`~policy_sentinel.catalog.Catalog` surface over
``fixtures/*.json``, evaluates the *same* ``/q`` query strings the live client
sends, and records every write in a journal so ``examples/before-after/`` can be
generated without mutating anyone's instance.

It is a development and demo aid, never a substitute for a real run: the mode is
stamped ``offline`` on every report it produces.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import urns
from .catalog import Catalog, CatalogError
from .models import Entity, Hop
from .query import compile_query

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures"


@dataclass
class WriteRecord:
    op: str
    target: str
    payload: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {"op": self.op, "target": self.target, "payload": self.payload}


@dataclass
class FixtureCatalog(Catalog):
    """A DataHub-shaped graph loaded from JSON."""

    data: Dict[str, Any] = field(default_factory=dict)
    mode: str = "offline"
    writes_enabled: bool = True
    base_url: Optional[str] = None

    entities: Dict[str, Entity] = field(default_factory=dict, init=False)
    out_edges: Dict[str, List[Hop]] = field(default_factory=dict, init=False)
    in_edges: Dict[str, List[Hop]] = field(default_factory=dict, init=False)
    fields_by_dataset: Dict[str, List[str]] = field(default_factory=dict, init=False)
    queries: Dict[str, List[str]] = field(default_factory=dict, init=False)
    journal: List[WriteRecord] = field(default_factory=list, init=False)
    documents: List[Dict[str, Any]] = field(default_factory=list, init=False)

    # ------------------------------------------------------------- loading

    def __post_init__(self) -> None:
        self.base_url = self.base_url or self.data.get("baseUrl") or "http://localhost:9002"
        aliases: Dict[str, str] = {}

        for raw in self.data.get("entities", []):
            urn = raw["urn"]
            aliases[raw.get("alias", urn)] = urn
            entity = Entity(
                urn=urn,
                sub_type=raw.get("subType"),
                description=raw.get("description"),
                tags=list(raw.get("tags", [])),
                terms=list(raw.get("terms", [])),
                owners=list(raw.get("owners", [])),
                domain=raw.get("domain"),
                properties=dict(raw.get("properties", {})),
            )
            self.entities[urn] = entity

            field_tags: List[str] = []
            for col in raw.get("fields", []):
                col_urn = urns.make_field_urn(urn, col["path"])
                col_tags = list(col.get("tags", []))
                field_tags.extend(col_tags)
                self.entities[col_urn] = Entity(
                    urn=col_urn,
                    sub_type=col.get("type"),
                    description=col.get("description"),
                    tags=col_tags,
                    terms=list(col.get("terms", [])),
                    owners=list(entity.owners),
                    domain=entity.domain,
                )
                self.fields_by_dataset.setdefault(urn, []).append(col_urn)
                aliases[f"{raw.get('alias', urn)}:{col['path']}"] = col_urn

            if field_tags:
                # Mirrors DataHub's `fieldTags` index field, so a column-level
                # subject query resolves the same way it does against a live GMS.
                entity.properties["fieldTags"] = sorted(set(field_tags))

        for raw in self.data.get("edges", []):
            source = aliases.get(raw["source"], raw["source"])
            target = aliases.get(raw["target"], raw["target"])
            for endpoint in (source, target):
                if endpoint not in self.entities:
                    raise CatalogError(
                        f"fixture edge references unknown entity {endpoint!r}; "
                        "check the alias spelling"
                    )
            hop = Hop(
                source=source,
                target=target,
                transform=raw.get("transform"),
                query=raw.get("query"),
                via=aliases.get(raw.get("via", ""), raw.get("via")),
                level="column" if urns.is_field(source) or urns.is_field(target) else "table",
            )
            self.out_edges.setdefault(source, []).append(hop)
            self.in_edges.setdefault(target, []).append(hop)

        for key, sql in (self.data.get("queries") or {}).items():
            self.queries[aliases.get(key, key)] = list(sql)

    @classmethod
    def load(cls, path: str | Path) -> "FixtureCatalog":
        p = Path(path)
        if not p.exists() and not p.suffix:
            p = FIXTURE_DIR / f"{path}.json"
        if not p.exists():
            available = ", ".join(sorted(f.stem for f in FIXTURE_DIR.glob("*.json"))) or "none"
            raise CatalogError(f"fixture not found: {path} (available: {available})")
        return cls(data=json.loads(p.read_text(encoding="utf-8")))

    # --------------------------------------------------------------- reads

    def search(
        self,
        query: str,
        entity_types: Optional[Sequence[str]] = None,
        limit: int = 200,
    ) -> List[Entity]:
        predicate = compile_query(query)
        wanted = {t.lower() for t in (entity_types or [])}
        hits: List[Entity] = []
        for entity in self.entities.values():
            if entity.is_column and "schemafield" not in wanted:
                continue  # columns are reached via list_schema_fields, as in DataHub
            if wanted and not any(entity.type_matches(t) for t in wanted):
                continue
            if predicate(entity):
                hits.append(entity)
            if len(hits) >= limit:
                break
        return hits

    def get_entities(self, urns_: Sequence[str]) -> Dict[str, Entity]:
        return {u: self.entities[u] for u in urns_ if u in self.entities}

    def neighbors(self, urn: str, direction: str = "downstream") -> List[Hop]:
        table = self.out_edges if direction == "downstream" else self.in_edges
        return list(table.get(urn, []))

    def list_schema_fields(self, dataset_urn: str) -> List[Entity]:
        return [self.entities[u] for u in self.fields_by_dataset.get(dataset_urn, [])]

    def get_dataset_queries(self, urn: str, limit: int = 3) -> List[str]:
        found = self.queries.get(urn)
        if not found and urns.is_field(urn):
            parent = urns.dataset_of_field(urn)
            found = self.queries.get(parent or "", [])
        return list(found or [])[:limit]

    # -------------------------------------------------------------- writes

    def add_tags(self, urn: str, tags: Sequence[str]) -> None:
        entity = self.entities.get(urn)
        if entity is None:
            raise CatalogError(f"cannot tag unknown entity {urn}")
        for tag in tags:
            name = urns.tag_name(tag)
            if not entity.has_tag(name):
                entity.tags.append(name)
        self.journal.append(WriteRecord("add_tags", urn, {"tags": list(tags)}))

    def remove_tags(self, urn: str, tags: Sequence[str]) -> None:
        entity = self.entities.get(urn)
        if entity is None:
            raise CatalogError(f"cannot untag unknown entity {urn}")
        drop = {urns.tag_name(t).lower() for t in tags}
        entity.tags = [t for t in entity.tags if urns.tag_name(t).lower() not in drop]
        self.journal.append(WriteRecord("remove_tags", urn, {"tags": list(tags)}))

    def add_structured_properties(self, urn: str, properties: Dict[str, Any]) -> None:
        entity = self.entities.get(urn)
        if entity is None:
            raise CatalogError(f"cannot annotate unknown entity {urn}")
        entity.properties.update(properties)
        self.journal.append(WriteRecord("add_structured_properties", urn, dict(properties)))

    def save_document(
        self,
        title: str,
        content: str,
        related_urns: Optional[Sequence[str]] = None,
        doc_id: Optional[str] = None,
    ) -> Optional[str]:
        doc_urn = f"urn:li:document:{doc_id or str(len(self.documents) + 1)}"
        self.documents.append(
            {
                "urn": doc_urn,
                "title": title,
                "content": content,
                "related": list(related_urns or []),
            }
        )
        self.journal.append(
            WriteRecord("save_document", doc_urn, {"title": title, "related": list(related_urns or [])})
        )
        return doc_urn

    # ------------------------------------------------------------ snapshots

    def snapshot(self, urn: str) -> Dict[str, Any]:
        """Entity state, for the before/after example artifacts."""
        entity = self.entities.get(urn)
        if entity is None:
            return {}
        data = entity.to_dict()
        data["properties"] = {
            k: v for k, v in entity.properties.items() if k != "fieldTags"
        }
        return data

    def dump_writes(self) -> List[Dict[str, Any]]:
        return [r.to_dict() for r in self.journal]
