"""Kestrel / Policy Sentinel.

Semgrep for your data catalog: governance rules written as code, enforced by an
agent across the whole DataHub lineage graph, with findings written back into
the catalog.

The distinguishing idea: DataHub Metadata Tests and Assertions evaluate one
entity at a time. Kestrel evaluates conditions across *lineage paths* -- "does
any column tagged PII reach a BI dashboard through any multi-hop path, without
passing through a masking step?" -- which per-entity checks structurally cannot
express.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
