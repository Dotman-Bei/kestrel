"""The live catalog: DataHub via the official MCP server.

Runs ``uvx mcp-server-datahub`` (configurable) as a stdio subprocess and speaks
MCP to it. Reads use ``search`` / ``get_lineage`` / ``get_entities`` /
``list_schema_fields`` / ``get_dataset_queries``; writes use ``add_tags`` /
``add_structured_properties`` / ``save_document``, which the server only exposes
when it was started with ``TOOLS_IS_MUTATION_ENABLED=true``.

Two deliberate robustness choices:

1. **Arguments are bound from the tool's advertised input schema**, not
   hardcoded. Tool parameter names differ across server versions (``max_hops``
   vs ``num_hops``, ``urn`` vs ``entity_urn``); we read ``inputSchema`` at
   connect time and pick the name the server actually declares. When nothing
   matches, the error names the keys the server *does* accept instead of failing
   with an opaque validation error.
2. **Responses are harvested structurally.** Rather than assuming one envelope
   shape, we walk the returned JSON for objects carrying a ``urn`` and normalise
   the metadata keys we understand.

``update_description`` is deliberately unused: it is Cloud-only and hidden on
OSS, so the entire write-back design stands on tags, structured properties and
documents.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import tempfile
import textwrap
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import urns
from .catalog import Catalog, CatalogError
from .models import Entity, Hop

DEFAULT_COMMAND = "uvx mcp-server-datahub"
DEFAULT_TIMEOUT = 120.0

READ_TOOLS = (
    "search",
    "get_lineage",
    "get_lineage_paths",
    "get_entities",
    "list_schema_fields",
    "get_dataset_queries",
)
def _schema_properties(schema: Dict[str, Any]) -> Dict[str, Any]:
    """The parameter properties a tool advertises, through one level of indirection.

    Pydantic-generated JSON Schema often puts the real properties behind a
    ``$ref`` into ``$defs``, or splits them across ``allOf``/``anyOf``, leaving
    nothing at the top level. Reading ``properties`` directly then yields {} and
    every later bind fails with "this tool accepts no parameters", which is both
    wrong and hard to trace back to here.
    """
    if not isinstance(schema, dict):
        return {}

    props = schema.get("properties")
    if isinstance(props, dict) and props:
        return props

    defs = schema.get("$defs") or schema.get("definitions") or {}
    ref = schema.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        node = schema
        for part in ref.lstrip("#/").split("/"):
            node = node.get(part) if isinstance(node, dict) else None
            if node is None:
                break
        if isinstance(node, dict):
            found = _schema_properties(node)
            if found:
                return found

    for key in ("allOf", "anyOf", "oneOf"):
        for member in schema.get(key) or []:
            if isinstance(member, dict):
                found = _schema_properties(member)
                if found:
                    return found

    if isinstance(defs, dict) and len(defs) == 1:
        only = next(iter(defs.values()))
        if isinstance(only, dict):
            return _schema_properties(only)

    return {}


WRITE_TOOLS = ("add_tags", "remove_tags", "add_structured_properties", "save_document")


# --------------------------------------------------------------------- bridge


class _AsyncBridge:
    """Owns one asyncio loop on a background thread.

    The MCP SDK is async; the engines are sync and stay that way on purpose --
    policy evaluation reads far better as straight-line code.
    """

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="kestrel-mcp", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def run(self, coro: Any, timeout: float = DEFAULT_TIMEOUT) -> Any:
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result(timeout)

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)


# ------------------------------------------------------------------ normalise


def _iter_dicts(payload: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(payload, dict):
        yield payload
        for value in payload.values():
            yield from _iter_dicts(value)
    elif isinstance(payload, list):
        for item in payload:
            yield from _iter_dicts(item)


def _first(mapping: Dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _urn_list(value: Any, *inner_keys: str) -> List[str]:
    """Pull URNs out of the several shapes DataHub uses for tag/owner lists."""
    out: List[str] = []
    if value is None:
        return out
    if isinstance(value, dict):
        value = _first(value, "tags", "terms", "owners", "elements") or []
    for item in value if isinstance(value, list) else [value]:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            direct = _first(item, "urn", *inner_keys)
            if isinstance(direct, str):
                out.append(direct)
            elif isinstance(direct, dict):
                nested = _first(direct, "urn", "name")
                if isinstance(nested, str):
                    out.append(nested)
            else:
                name = _first(item, "name")
                if isinstance(name, str):
                    out.append(name)
    return out


def normalize_entity(raw: Dict[str, Any]) -> Optional[Entity]:
    """Best-effort Entity from whatever the server handed back."""
    urn = raw.get("urn")
    if not isinstance(urn, str) or not urn.startswith("urn:li:"):
        return None

    props = raw.get("properties") if isinstance(raw.get("properties"), dict) else {}
    editable = raw.get("editableProperties") if isinstance(raw.get("editableProperties"), dict) else {}

    platform = _first(raw, "platform", "dataPlatform")
    if isinstance(platform, dict):
        platform = _first(platform, "name", "urn")
    if isinstance(platform, str) and platform.startswith("urn:li:dataPlatform:"):
        platform = platform.rsplit(":", 1)[-1]

    sub_type = _first(raw, "subType", "sub_type")
    if sub_type is None:
        sub_types = raw.get("subTypes")
        if isinstance(sub_types, dict):
            names = sub_types.get("typeNames")
            if isinstance(names, list) and names:
                sub_type = str(names[0])
        elif isinstance(sub_types, list) and sub_types:
            sub_type = str(sub_types[0])

    # DataHub wraps the domain association: {"domain": {"domain": {"urn": ...}}}.
    # Unwrap until we reach a string, bounded so a cyclic payload cannot spin.
    domain = raw.get("domain")
    for _ in range(4):
        if not isinstance(domain, dict):
            break
        domain = _first(domain, "urn", "name", "domain")

    entity = Entity(
        urn=urn,
        type=str(_first(raw, "type", "entityType", "entity_type") or urns.entity_type(urn)).lower(),
        name=str(_first(raw, "name", "qualifiedName") or _first(props, "name", "qualifiedName") or ""),
        platform=platform if isinstance(platform, str) else None,
        sub_type=str(sub_type) if sub_type else None,
        description=_first(raw, "description") or _first(props, "description") or _first(editable, "description"),
        tags=[urns.tag_name(t) for t in _urn_list(_first(raw, "tags", "globalTags"), "tag")],
        terms=[urns.tag_name(t) for t in _urn_list(_first(raw, "glossaryTerms", "terms"), "term", "glossaryTerm")],
        owners=_urn_list(_first(raw, "owners", "ownership"), "owner"),
        domain=domain if isinstance(domain, str) else None,
    )
    if entity.type == "schemafield":
        entity.type = "schemaField"
    if not entity.name:
        entity.name = urns.qualified_name(urn)
    return entity


def harvest_entities(payload: Any) -> List[Entity]:
    """Every distinct entity mentioned anywhere in a tool response."""
    found: Dict[str, Entity] = {}
    for candidate in _iter_dicts(payload):
        entity = normalize_entity(candidate)
        if entity is None:
            continue
        existing = found.get(entity.urn)
        # Prefer the richest mention: nested references are often urn-only.
        if existing is None or len(entity.tags) + len(entity.owners) > len(existing.tags) + len(existing.owners):
            found[entity.urn] = entity
    return list(found.values())


# --------------------------------------------------------------------- client


@dataclass
class McpCatalog(Catalog):
    """Catalog implementation over ``mcp-server-datahub``."""

    command: str = ""
    gms_url: str = ""
    gms_token: str = ""
    timeout: float = DEFAULT_TIMEOUT
    extra_env: Dict[str, str] = field(default_factory=dict)
    enable_writes: bool = True

    mode: str = "live"
    writes_enabled: bool = False
    base_url: Optional[str] = None

    _bridge: Optional[_AsyncBridge] = field(default=None, init=False, repr=False)
    _session: Any = field(default=None, init=False, repr=False)
    _stdio_cm: Any = field(default=None, init=False, repr=False)
    _session_cm: Any = field(default=None, init=False, repr=False)
    _errlog: Any = field(default=None, init=False, repr=False)
    _schemas: Dict[str, Dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _entity_cache: Dict[str, Entity] = field(default_factory=dict, init=False, repr=False)
    _lineage_cache: Dict[str, List[Hop]] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.command = self.command or os.environ.get("KESTREL_MCP_COMMAND", DEFAULT_COMMAND)
        self.gms_url = self.gms_url or os.environ.get("DATAHUB_GMS_URL", "http://localhost:8080")
        self.gms_token = self.gms_token or os.environ.get("DATAHUB_GMS_TOKEN", "")
        self.base_url = self.base_url or os.environ.get("DATAHUB_FRONTEND_URL", "http://localhost:9002")

    # ------------------------------------------------------------- connect

    def connect(self) -> "McpCatalog":
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise CatalogError(
                "the 'mcp' package is required for live mode; pip install mcp"
            ) from exc

        parts = shlex.split(self.command)
        if not parts:
            raise CatalogError("empty MCP command")

        env = dict(os.environ)
        env["DATAHUB_GMS_URL"] = self.gms_url
        if self.gms_token:
            env["DATAHUB_GMS_TOKEN"] = self.gms_token
        if self.enable_writes:
            env["TOOLS_IS_MUTATION_ENABLED"] = "true"
        env.update(self.extra_env)

        params = StdioServerParameters(command=parts[0], args=parts[1:], env=env)
        self._bridge = _AsyncBridge()

        # The server logs progress and warnings to stderr. Left alone it prints
        # straight through and buries the report; captured, it becomes the most
        # useful thing we can show when the connection fails.
        self._errlog = tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace")

        async def _open() -> Any:
            self._stdio_cm = stdio_client(params, errlog=self._errlog)
            read, write = await self._stdio_cm.__aenter__()
            self._session_cm = ClientSession(read, write)
            session = await self._session_cm.__aenter__()
            await session.initialize()
            listing = await session.list_tools()
            return session, listing

        try:
            session, listing = self._bridge.run(_open(), timeout=self.timeout)
        except Exception as exc:
            server_log = self.server_stderr()
            self.close()
            detail = f"{type(exc).__name__}: {exc}".strip().rstrip(":")
            message = (
                f"could not start the DataHub MCP server with '{self.command}'.\n"
                f"  - is DataHub up at {self.gms_url}?\n"
                f"  - is 'uvx' (or your configured command) on PATH?\n"
                f"  - are DATAHUB_GMS_URL / DATAHUB_GMS_TOKEN set correctly?\n"
                f"  error: {detail}"
            )
            if server_log:
                message += "\n\n  last output from the server:\n" + textwrap.indent(server_log, "    ")
            raise CatalogError(message) from exc

        self._session = session
        for tool in listing.tools:
            # The MCP SDK renamed this attribute from camelCase to snake_case;
            # read both, because getattr with a default silently yields {} on the
            # wrong one -- which looks like "this server advertises no parameters"
            # and fails much later, at bind time, with a misleading message.
            schema = getattr(tool, "input_schema", None)
            if schema is None:
                schema = getattr(tool, "inputSchema", None)
            schema = schema or {}
            self._schemas[tool.name] = schema if isinstance(schema, dict) else {}

        missing_reads = [t for t in ("search", "get_lineage") if t not in self._schemas]
        if missing_reads:
            raise CatalogError(
                f"the MCP server did not expose required read tool(s): {missing_reads}. "
                f"Tools seen: {sorted(self._schemas)}"
            )
        self.writes_enabled = all(t in self._schemas for t in ("add_tags", "save_document"))
        return self

    def server_stderr(self, max_lines: int = 3) -> str:
        """The diagnostic lines the MCP server wrote to stderr.

        Its own logs say whether mutation tools were registered and whether it
        could reach GMS -- far more useful than the transport exception, which
        is often empty. Python traceback frames are stripped: the reader wants
        the error, not the server's call stack.
        """
        if self._errlog is None:
            return ""
        try:
            self._errlog.flush()
            self._errlog.seek(0)
            raw = self._errlog.read().splitlines()
        except (ValueError, OSError):
            return ""

        useful: List[str] = []
        for line in raw:
            text = line.rstrip()
            stripped = text.strip()
            if not stripped:
                continue
            if stripped.startswith(("File \"", "Traceback (most recent")):
                continue
            if set(stripped) <= {"^", "~"}:
                continue
            if text.startswith((" ", "\t")) and not stripped[0].isupper():
                continue  # echoed source lines from the traceback
            useful.append(stripped)
        return "\n".join(useful[-max_lines:])

    def close(self) -> None:
        if self._bridge is None:
            self._close_errlog()
            return

        async def _shut() -> None:
            try:
                if self._session_cm is not None:
                    await self._session_cm.__aexit__(None, None, None)
            finally:
                if self._stdio_cm is not None:
                    await self._stdio_cm.__aexit__(None, None, None)

        try:
            self._bridge.run(_shut(), timeout=15)
        except Exception:
            pass  # the subprocess dies with us; never let teardown mask a result
        finally:
            self._bridge.stop()
            self._bridge = None
            self._session = None
            self._close_errlog()

    def _close_errlog(self) -> None:
        if self._errlog is not None:
            try:
                self._errlog.close()
            except OSError:
                pass
            self._errlog = None

    @property
    def available_tools(self) -> List[str]:
        return sorted(self._schemas)

    # ---------------------------------------------------------- tool calls

    def _schema_keys(self, tool: str) -> List[str]:
        return list(_schema_properties(self._schemas.get(tool) or {}).keys())

    def _bind(self, tool: str, candidates: Sequence[str], value: Any, args: Dict[str, Any]) -> bool:
        """Set ``value`` under whichever candidate name this server declares."""
        keys = self._schema_keys(tool)
        for name in candidates:
            if name in keys:
                args[name] = value
                return True
        return False

    def _require(self, tool: str, candidates: Sequence[str], value: Any, args: Dict[str, Any]) -> None:
        if not self._bind(tool, candidates, value, args):
            raise CatalogError(
                f"tool '{tool}' accepts none of {list(candidates)}; "
                f"its parameters are {self._schema_keys(tool)}. "
                "Your mcp-server-datahub version may be newer than this client -- "
                "please open an issue with that parameter list."
            )

    def call(self, tool: str, args: Dict[str, Any]) -> Any:
        if self._session is None or self._bridge is None:
            raise CatalogError("MCP session is not connected; call connect() first")
        if tool not in self._schemas:
            raise CatalogError(
                f"tool '{tool}' is not available on this server. Available: {self.available_tools}. "
                "Write tools require TOOLS_IS_MUTATION_ENABLED=true."
            )
        result = self._bridge.run(self._session.call_tool(tool, args), timeout=self.timeout)
        if getattr(result, "isError", False):
            raise CatalogError(f"MCP tool '{tool}' failed: {_result_text(result)}")
        return _result_payload(result)

    # --------------------------------------------------------------- reads

    def search(
        self,
        query: str,
        entity_types: Optional[Sequence[str]] = None,
        limit: int = 200,
    ) -> List[Entity]:
        args: Dict[str, Any] = {}
        self._require("search", ("query", "q", "keyword", "search_query", "input"), query, args)
        self._bind("search", ("limit", "count", "num_results", "size"), limit, args)
        if entity_types:
            self._bind(
                "search",
                ("entity_types", "entityTypes", "types", "entity_type"),
                [t for t in entity_types],
                args,
            )
        payload = self.call("search", args)
        wanted = {t.lower() for t in (entity_types or [])}
        hits = []
        for entity in harvest_entities(payload):
            if wanted and not any(entity.type_matches(t) for t in wanted):
                continue
            self._entity_cache.setdefault(entity.urn, entity)
            hits.append(entity)
        return hits[:limit]

    def get_entities(self, urns_: Sequence[str]) -> Dict[str, Entity]:
        wanted = [u for u in urns_ if u]
        out: Dict[str, Entity] = {}
        missing: List[str] = []
        for urn in wanted:
            cached = self._entity_cache.get(urn)
            if cached is not None:
                out[urn] = cached
            else:
                missing.append(urn)
        if not missing or "get_entities" not in self._schemas:
            for urn in missing:  # keep the walk going with a bare node
                out[urn] = Entity(urn=urn)
            return out

        for batch in (missing[i : i + 50] for i in range(0, len(missing), 50)):
            args: Dict[str, Any] = {}
            self._require("get_entities", ("urns", "urn", "entity_urns", "ids"), batch, args)
            try:
                payload = self.call("get_entities", args)
            except CatalogError:
                payload = None
            for entity in harvest_entities(payload):
                self._entity_cache[entity.urn] = entity
            for urn in batch:
                out[urn] = self._entity_cache.get(urn) or Entity(urn=urn)
        return out

    def neighbors(self, urn: str, direction: str = "downstream") -> List[Hop]:
        key = f"{direction}:{urn}"
        cached = self._lineage_cache.get(key)
        if cached is not None:
            return cached

        args: Dict[str, Any] = {}
        self._require("get_lineage", ("urn", "entity_urn", "dataset_urn", "id"), urn, args)
        if not self._bind("get_lineage", ("direction",), direction.upper(), args):
            self._bind("get_lineage", ("upstream", "is_upstream"), direction == "upstream", args)
        # One hop at a time: the walker owns depth, so paths stay reconstructable.
        self._bind("get_lineage", ("max_hops", "num_hops", "hops", "degree", "depth"), 1, args)

        try:
            payload = self.call("get_lineage", args)
        except CatalogError:
            self._lineage_cache[key] = []
            return []

        hops: List[Hop] = []
        seen: set[str] = set()
        for entity in harvest_entities(payload):
            if entity.urn == urn or entity.urn in seen:
                continue
            seen.add(entity.urn)
            self._entity_cache.setdefault(entity.urn, entity)
            source, target = (urn, entity.urn) if direction == "downstream" else (entity.urn, urn)
            hops.append(
                Hop(
                    source=source,
                    target=target,
                    level="column" if urns.is_field(urn) and urns.is_field(entity.urn) else "table",
                )
            )
        self._enrich_with_paths(urn, hops, direction)
        self._lineage_cache[key] = hops
        return hops

    def _enrich_with_paths(self, urn: str, hops: List[Hop], direction: str) -> None:
        """Attach the transform/SQL for each hop when the server can supply it.

        ``get_lineage_paths`` returns the intermediate transforms and SQL between
        two assets; that text is what ``without_step`` tests against and what the
        incident document quotes as evidence.
        """
        if "get_lineage_paths" not in self._schemas or not hops:
            return
        for hop in hops[:12]:  # bounded: this is evidence gathering, not traversal
            args: Dict[str, Any] = {}
            ok = self._bind("get_lineage_paths", ("source_urn", "upstream_urn", "from_urn", "source"), hop.source, args)
            ok = self._bind("get_lineage_paths", ("target_urn", "downstream_urn", "to_urn", "target"), hop.target, args) and ok
            if not ok:
                return
            try:
                payload = self.call("get_lineage_paths", args)
            except CatalogError:
                continue
            for node in _iter_dicts(payload):
                sql = _first(node, "query", "sql", "queryText", "statement")
                if isinstance(sql, str) and sql.strip() and not hop.query:
                    hop.query = sql.strip()
                transform = _first(node, "transformOperation", "transform", "operation")
                if isinstance(transform, str) and transform.strip() and not hop.transform:
                    hop.transform = transform.strip()

    def list_schema_fields(self, dataset_urn: str) -> List[Entity]:
        if "list_schema_fields" not in self._schemas:
            return []
        args: Dict[str, Any] = {}
        self._require("list_schema_fields", ("urn", "dataset_urn", "entity_urn"), dataset_urn, args)
        try:
            payload = self.call("list_schema_fields", args)
        except CatalogError:
            return []

        fields: List[Entity] = []
        seen: set[str] = set()
        for raw in _iter_dicts(payload):
            path = _first(raw, "fieldPath", "field_path", "path")
            urn_value = raw.get("urn")
            if isinstance(urn_value, str) and urns.is_field(urn_value):
                field_urn = urn_value
            elif isinstance(path, str) and path:
                field_urn = urns.make_field_urn(dataset_urn, path)
            else:
                continue
            if field_urn in seen:
                continue
            seen.add(field_urn)
            entity = normalize_entity({**raw, "urn": field_urn, "type": "schemaField"})
            if entity is None:
                continue
            entity.name = urns.qualified_name(field_urn)
            self._entity_cache[field_urn] = entity
            fields.append(entity)
        return fields

    def get_dataset_queries(self, urn: str, limit: int = 3) -> List[str]:
        if "get_dataset_queries" not in self._schemas:
            return []
        target = urn if not urns.is_field(urn) else (urns.dataset_of_field(urn) or urn)
        args: Dict[str, Any] = {}
        self._require("get_dataset_queries", ("urn", "dataset_urn", "entity_urn"), target, args)
        self._bind("get_dataset_queries", ("limit", "count", "num_results"), limit, args)
        try:
            payload = self.call("get_dataset_queries", args)
        except CatalogError:
            return []
        out: List[str] = []
        for node in _iter_dicts(payload):
            sql = _first(node, "query", "sql", "statement", "queryText")
            if isinstance(sql, str) and sql.strip() and sql.strip() not in out:
                out.append(sql.strip())
            if len(out) >= limit:
                break
        return out

    # -------------------------------------------------------------- writes

    def add_tags(self, urn: str, tags: Sequence[str]) -> None:
        args: Dict[str, Any] = {}
        self._require("add_tags", ("urn", "entity_urn", "resource_urn"), urn, args)
        self._require("add_tags", ("tags", "tag_urns", "tag_urn", "tag"), [urns.tag_urn(t) for t in tags], args)
        self.call("add_tags", args)

    def remove_tags(self, urn: str, tags: Sequence[str]) -> None:
        args: Dict[str, Any] = {}
        self._require("remove_tags", ("urn", "entity_urn", "resource_urn"), urn, args)
        self._require("remove_tags", ("tags", "tag_urns", "tag_urn", "tag"), [urns.tag_urn(t) for t in tags], args)
        self.call("remove_tags", args)

    def add_structured_properties(self, urn: str, properties: Dict[str, Any]) -> None:
        args: Dict[str, Any] = {}
        self._require("add_structured_properties", ("urn", "entity_urn", "resource_urn"), urn, args)
        self._require(
            "add_structured_properties",
            ("properties", "structured_properties", "structuredProperties", "values"),
            properties,
            args,
        )
        self.call("add_structured_properties", args)

    def save_document(
        self,
        title: str,
        content: str,
        related_urns: Optional[Sequence[str]] = None,
        doc_id: Optional[str] = None,
    ) -> Optional[str]:
        args: Dict[str, Any] = {}
        self._require("save_document", ("title", "name", "heading"), title, args)
        self._require("save_document", ("content", "body", "text", "markdown"), content, args)
        if related_urns:
            self._bind(
                "save_document",
                ("related_urns", "related_entities", "entities", "related_assets", "urns"),
                list(related_urns),
                args,
            )
        if doc_id:
            self._bind("save_document", ("id", "doc_id", "document_id", "slug"), doc_id, args)
        payload = self.call("save_document", args)
        for node in _iter_dicts(payload):
            urn = node.get("urn")
            if isinstance(urn, str) and urn.startswith("urn:li:"):
                return urn
        return None


# ------------------------------------------------------------------ helpers


def _result_text(result: Any) -> str:
    chunks: List[str] = []
    for item in getattr(result, "content", None) or []:
        text = getattr(item, "text", None)
        if isinstance(text, str):
            chunks.append(text)
    return "\n".join(chunks)


def _result_payload(result: Any) -> Any:
    """JSON when the server sent JSON, otherwise the raw text."""
    structured = getattr(result, "structuredContent", None)
    if structured:
        return structured
    text = _result_text(result)
    if not text:
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return text
