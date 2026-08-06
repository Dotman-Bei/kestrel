"""A small parser for the subset of DataHub ``/q`` syntax Kestrel emits.

DataHub itself evaluates these strings server-side; this parser exists so the
offline fixture catalog evaluates *the same query string* the live run sends,
rather than a hand-waved approximation of it. That matters for the agentic
engine, which composes raw queries of its own.

Supported: ``field:value``, quoted values, ``AND`` / ``OR`` / ``NOT``,
parentheses, trailing ``*`` wildcards, and bare terms (matched against the
entity name).
"""

from __future__ import annotations

import re
from typing import Callable, List, Optional

from . import urns
from .models import Entity

Predicate = Callable[[Entity], bool]

_TOKEN_RE = re.compile(
    r"""\s*(?:
        (?P<lparen>\()
      | (?P<rparen>\))
      | (?P<op>\bAND\b|\bOR\b|\bNOT\b|&&|\|\||!)
      | (?P<field>[A-Za-z_][A-Za-z0-9_.]*)\s*:\s*(?P<value>"[^"]*"|'[^']*'|[^\s()]+)
      | (?P<term>"[^"]*"|'[^']*'|[^\s()]+)
    )""",
    re.VERBOSE | re.IGNORECASE,
)

#: DataHub field name -> the Entity attribute it reads.
FIELD_ALIASES = {
    "tag": "tags",
    "tags": "tags",
    "globaltags": "tags",
    "term": "terms",
    "terms": "terms",
    "glossaryterm": "terms",
    "glossaryterms": "terms",
    "owner": "owners",
    "owners": "owners",
    "platform": "platform",
    "domain": "domain",
    "domains": "domain",
    "type": "type",
    "entitytype": "type",
    "typenames": "sub_type",
    "subtype": "sub_type",
    "name": "name",
    "urn": "urn",
    "description": "description",
    "fieldpath": "name",
}


class QueryError(ValueError):
    """The query string could not be parsed."""


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _tokenize(text: str) -> List[tuple]:
    tokens: List[tuple] = []
    pos = 0
    while pos < len(text):
        if text[pos].isspace():
            pos += 1
            continue
        m = _TOKEN_RE.match(text, pos)
        if not m or m.end() == pos:
            raise QueryError(f"cannot parse query at position {pos}: {text[pos:pos + 20]!r}")
        pos = m.end()
        if m.group("lparen"):
            tokens.append(("lparen", "("))
        elif m.group("rparen"):
            tokens.append(("rparen", ")"))
        elif m.group("op"):
            op = m.group("op").upper()
            tokens.append(("op", {"&&": "AND", "||": "OR", "!": "NOT"}.get(op, op)))
        elif m.group("field"):
            tokens.append(("pair", (m.group("field").lower(), _unquote(m.group("value")))))
        else:
            tokens.append(("term", _unquote(m.group("term"))))
    return tokens


def _values_for(entity: Entity, attr: str) -> List[str]:
    raw = getattr(entity, attr, None)
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [urns.tag_name(str(v)) for v in raw]
    return [str(raw)]


def _match_pair(field: str, wanted: str) -> Predicate:
    attr = FIELD_ALIASES.get(field)
    wanted_l = wanted.lower().rstrip("*")
    prefix = wanted.endswith("*")

    def predicate(entity: Entity) -> bool:
        if attr is None:
            # Unknown field: fall back to the entity's custom properties, which
            # is how aggregate index fields like `fieldTags` resolve offline.
            value = None
            for key, candidate in entity.properties.items():
                if key.lower() == field:
                    value = candidate
                    break
            if value is None:
                haystack = []
            elif isinstance(value, (list, tuple, set)):
                haystack = [urns.tag_name(str(v)) for v in value]
            else:
                haystack = [str(value)]
        else:
            haystack = _values_for(entity, attr)
        for value in haystack:
            v = value.lower()
            if prefix and v.startswith(wanted_l):
                return True
            if v == wanted_l:
                return True
            # Names and URNs are matched loosely -- "patients" should find
            # "healthcare.raw.patients", the way the DataHub search box does.
            if attr in {"name", "urn", "description"} and wanted_l in v:
                return True
        return False

    return predicate


def _match_term(text: str) -> Predicate:
    if text == "*":
        return lambda entity: True
    needle = text.lower().rstrip("*")

    def predicate(entity: Entity) -> bool:
        return needle in entity.name.lower() or needle in entity.urn.lower()

    return predicate


class _Parser:
    def __init__(self, tokens: List[tuple]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Optional[tuple]:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def parse(self) -> Predicate:
        pred = self.parse_or()
        if self.peek() is not None:
            raise QueryError("unbalanced parentheses in query")
        return pred

    def parse_or(self) -> Predicate:
        left = self.parse_and()
        while True:
            tok = self.peek()
            if tok and tok[0] == "op" and tok[1] == "OR":
                self.pos += 1
                right = self.parse_and()
                left = (lambda a, b: lambda e: a(e) or b(e))(left, right)
            else:
                return left

    def parse_and(self) -> Predicate:
        left = self.parse_unary()
        while True:
            tok = self.peek()
            if tok is None or tok[0] == "rparen":
                return left
            if tok[0] == "op" and tok[1] == "OR":
                return left
            if tok[0] == "op" and tok[1] == "AND":
                self.pos += 1
            # Adjacency without an operator means AND, as in the DataHub UI.
            right = self.parse_unary()
            left = (lambda a, b: lambda e: a(e) and b(e))(left, right)

    def parse_unary(self) -> Predicate:
        tok = self.peek()
        if tok is None:
            raise QueryError("unexpected end of query")
        if tok[0] == "op" and tok[1] == "NOT":
            self.pos += 1
            inner = self.parse_unary()
            return lambda e: not inner(e)
        if tok[0] == "lparen":
            self.pos += 1
            inner = self.parse_or()
            closing = self.peek()
            if not closing or closing[0] != "rparen":
                raise QueryError("missing closing parenthesis")
            self.pos += 1
            return inner
        if tok[0] == "pair":
            self.pos += 1
            return _match_pair(*tok[1])
        if tok[0] == "term":
            self.pos += 1
            return _match_term(tok[1])
        raise QueryError(f"unexpected token {tok[1]!r}")


def compile_query(text: str) -> Predicate:
    """Compile a ``/q`` string into a predicate over :class:`Entity`."""
    stripped = (text or "").strip()
    if not stripped or stripped == "*":
        return lambda entity: True
    tokens = _tokenize(stripped)
    if not tokens:
        return lambda entity: True
    return _Parser(tokens).parse()
