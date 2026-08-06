"""Helpers for reading DataHub URNs.

DataHub URNs nest, so naive ``str.split(",")`` breaks on the common case::

    urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.public.patients,PROD)
    urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.public.patients,PROD),ssn)

Everything here is pure string work -- no network, no SDK -- so policy
evaluation stays testable without a running instance.
"""

from __future__ import annotations

from typing import List, Optional

URN_PREFIX = "urn:li:"


def is_urn(value: object) -> bool:
    return isinstance(value, str) and value.startswith(URN_PREFIX)


def entity_type(urn: str) -> str:
    """``urn:li:dataset:(...)`` -> ``dataset``. Empty string if unparseable."""
    if not is_urn(urn):
        return ""
    rest = urn[len(URN_PREFIX) :]
    head, _, _ = rest.partition(":")
    return head


def _inner(urn: str) -> str:
    """The bit inside the outermost parentheses, or the bare key for simple URNs."""
    start = urn.find("(")
    if start == -1:
        # simple form: urn:li:tag:PII
        rest = urn[len(URN_PREFIX) :]
        _, _, key = rest.partition(":")
        return key
    end = urn.rfind(")")
    if end <= start:
        return ""
    return urn[start + 1 : end]


def split_parts(inner: str) -> List[str]:
    """Split on commas that are not inside nested parentheses."""
    parts: List[str] = []
    depth = 0
    buf: List[str] = []
    for ch in inner:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return parts


def urn_parts(urn: str) -> List[str]:
    return split_parts(_inner(urn))


def is_field(urn: str) -> bool:
    return entity_type(urn) == "schemaField"


def dataset_of_field(field_urn: str) -> Optional[str]:
    """Parent dataset URN of a schemaField URN."""
    if not is_field(field_urn):
        return None
    parts = urn_parts(field_urn)
    return parts[0] if parts else None


def field_path(field_urn: str) -> Optional[str]:
    """Column name of a schemaField URN."""
    if not is_field(field_urn):
        return None
    parts = urn_parts(field_urn)
    return parts[1] if len(parts) > 1 else None


def make_field_urn(dataset_urn: str, path: str) -> str:
    return f"urn:li:schemaField:({dataset_urn},{path})"


def platform_of(urn: str) -> Optional[str]:
    """Platform key for a dataset/dashboard/chart URN, e.g. ``snowflake``."""
    kind = entity_type(urn)
    if kind == "schemaField":
        parent = dataset_of_field(urn)
        return platform_of(parent) if parent else None
    parts = urn_parts(urn)
    if not parts:
        return None
    head = parts[0]
    if head.startswith("urn:li:dataPlatform:"):
        return head.rsplit(":", 1)[-1]
    # dashboards/charts carry a bare platform key: urn:li:dashboard:(looker,x)
    if kind in {"dashboard", "chart", "dataFlow", "dataJob"} and not head.startswith(URN_PREFIX):
        return head
    return None


def dataset_name(urn: str) -> Optional[str]:
    """The table identifier, e.g. ``healthcare.public.patients``."""
    kind = entity_type(urn)
    if kind == "schemaField":
        parent = dataset_of_field(urn)
        return dataset_name(parent) if parent else None
    if kind != "dataset":
        return None
    parts = urn_parts(urn)
    return parts[1] if len(parts) > 1 else None


def short_name(urn: str) -> str:
    """A compact, human-facing label for terminal output and reports."""
    if not is_urn(urn):
        return str(urn)
    kind = entity_type(urn)
    if kind == "schemaField":
        parent = dataset_of_field(urn) or ""
        table = (dataset_name(parent) or "").split(".")[-1]
        return f"{table}.{field_path(urn)}" if table else str(field_path(urn))
    if kind == "dataset":
        return (dataset_name(urn) or urn).split(".")[-1]
    if kind in {"corpuser", "corpGroup", "tag", "glossaryTerm", "domain"}:
        return urn.rsplit(":", 1)[-1]
    parts = urn_parts(urn)
    if len(parts) > 1:
        return parts[-1]
    return urn


def qualified_name(urn: str) -> str:
    """Fuller label: keeps the schema path, used in reports and documents."""
    kind = entity_type(urn)
    if kind == "schemaField":
        parent = dataset_of_field(urn) or ""
        return f"{dataset_name(parent) or parent}.{field_path(urn)}"
    if kind == "dataset":
        return dataset_name(urn) or urn
    return short_name(urn)


def tag_urn(name: str) -> str:
    return name if is_urn(name) else f"urn:li:tag:{name}"


def tag_name(urn: str) -> str:
    return urn.rsplit(":", 1)[-1] if is_urn(urn) else urn
