"""Lineage traversal -- the behaviour per-entity tests cannot reproduce."""

import pytest

from policy_sentinel.fixture_client import FixtureCatalog
from policy_sentinel.graph import LineageWalker, PathMatcher
from policy_sentinel.models import Entity

SSN = (
    "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "healthcare.raw.patients,PROD),ssn)"
)
EMAIL = (
    "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "healthcare.raw.patients,PROD),email)"
)
DOB = (
    "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:postgres,"
    "healthcare.raw.patients,PROD),dob)"
)
PATIENT_360 = "urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.marts.patient_360,PROD)"
DASHBOARD = "urn:li:dashboard:(looker,patient_overview)"


@pytest.fixture
def catalog() -> FixtureCatalog:
    return FixtureCatalog.load("healthcare")


@pytest.fixture
def walker(catalog: FixtureCatalog) -> LineageWalker:
    return LineageWalker(catalog=catalog, max_hops=6)


def test_finds_the_multi_hop_path_to_a_dashboard(walker, catalog):
    matcher = PathMatcher(sink_types=["Dashboard", "Chart"])
    path = walker.find_path(catalog.entities[SSN], matcher)

    assert path is not None
    assert path.sink.urn == DASHBOARD
    assert path.length == 4, path.render()
    assert path.urn_chain[0] == SSN


def test_shortest_path_wins(walker, catalog):
    """BFS, so the reported evidence is the most legible path, not the first one."""
    matcher = PathMatcher(sink_types=["Dashboard", "Chart"])
    path = walker.find_path(catalog.entities[SSN], matcher)
    longer = [
        p
        for p in walker.iter_paths(catalog.entities[SSN])
        if matcher.sink_matches(p.sink)
    ]
    assert all(path.length <= p.length for p in longer)


def test_masking_step_suppresses_the_path(walker, catalog):
    """The email column reaches a dashboard too -- but it is hashed on the way."""
    unguarded = PathMatcher(sink_types=["Dashboard", "Chart"])
    assert walker.find_path(catalog.entities[EMAIL], unguarded) is not None

    guarded = PathMatcher(
        sink_types=["Dashboard", "Chart"],
        without_step="mask|hash|sha2",
    )
    assert walker.find_path(catalog.entities[EMAIL], guarded) is None
    assert "masking step" in (walker.first_mitigated(catalog.entities[EMAIL], guarded) or "")


def test_column_with_no_downstream_reaches_nothing(walker, catalog):
    matcher = PathMatcher(sink_types=["Dashboard", "Chart"])
    assert walker.find_path(catalog.entities[DOB], matcher) is None


def test_table_level_fallback_is_marked(walker, catalog):
    """Column lineage runs out before the dashboard; the walk says so."""
    matcher = PathMatcher(sink_types=["Dashboard", "Chart"])
    path = walker.find_path(catalog.entities[SSN], matcher)
    assert path.hops[-1].level == "table"
    assert path.hops[0].level == "column"
    assert any("table-level" in note for note in path.notes)
    assert walker.stats.fallbacks > 0


def test_upstream_traversal_finds_the_stale_source(walker, catalog):
    matcher = PathMatcher(sink_tags=["Stale", "Deprecated"])
    path = walker.find_path(catalog.entities[PATIENT_360], matcher, direction="upstream")
    assert path is not None
    assert path.length == 2
    assert "lab_results" in path.sink.urn


def test_traversal_is_cycle_safe(catalog):
    a = Entity(urn="urn:li:dataset:(urn:li:dataPlatform:x,a,PROD)")
    b = Entity(urn="urn:li:dataset:(urn:li:dataPlatform:x,b,PROD)")
    catalog.entities[a.urn] = a
    catalog.entities[b.urn] = b
    from policy_sentinel.models import Hop

    catalog.out_edges.setdefault(a.urn, []).append(Hop(a.urn, b.urn, level="table"))
    catalog.out_edges.setdefault(b.urn, []).append(Hop(b.urn, a.urn, level="table"))

    walker = LineageWalker(catalog=catalog, max_hops=10, max_paths=50)
    paths = list(walker.iter_paths(a))
    assert len(paths) == 1  # a -> b, and no further: a is already in the path
    assert all(len(set(p.urn_chain)) == len(p.urn_chain) for p in paths)


def test_path_budget_stops_a_runaway_walk(catalog):
    walker = LineageWalker(catalog=catalog, max_hops=6, max_paths=3)
    paths = list(walker.iter_paths(catalog.entities[SSN]))
    assert len(paths) <= 3
    assert walker.stats.truncated
