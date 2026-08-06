"""End-to-end: policies in, violations out, write-back applied."""

import json

import pytest

from policy_sentinel.engine_templates import TemplateEngine
from policy_sentinel.fixture_client import FixtureCatalog
from policy_sentinel.models import ScanReport, utc_now
from policy_sentinel.policy import Policy, load_policies
from policy_sentinel.render import incident_markdown, report_markdown
from policy_sentinel.writeback import WriteBackConfig, WriteBackWriter

DASHBOARD = "urn:li:dashboard:(looker,patient_overview)"
ENCOUNTERS = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.marts.patient_encounters,PROD)"
)


@pytest.fixture
def catalog() -> FixtureCatalog:
    return FixtureCatalog.load("healthcare")


@pytest.fixture
def policies():
    return {p.id: p for p in load_policies("policies")}


def evaluate(catalog, policy):
    return TemplateEngine(catalog).evaluate(policy)


def test_pii_reaches_bi_finds_the_headline_violation(catalog, policies):
    result = evaluate(catalog, policies["pii-reaches-bi"])

    assert result.error is None
    assert result.subjects_scanned == 6, "the fixture has six tagged columns"
    ssn = [v for v in result.violations if v.subject.urn.endswith(",ssn)")]
    assert len(ssn) == 1

    violation = ssn[0]
    assert violation.sink.urn == DASHBOARD
    assert violation.path.length == 4
    assert "reaches Dashboard/Chart 'patient_overview'" in violation.message
    assert violation.severity == "high"
    assert violation.owners == ["urn:li:corpuser:dana.okoro"]
    assert any("hop 1" in line for line in violation.evidence)


def test_masked_column_is_not_reported(catalog, policies):
    result = evaluate(catalog, policies["pii-reaches-bi"])
    assert not [v for v in result.violations if v.subject.urn.endswith(",email)")]
    assert any("path suppressed" in note for note in result.notes)


def test_certification_rule_discriminates(catalog, policies):
    """patient_encounters is unowned; patient_360 is owned. Only one fires."""
    result = evaluate(catalog, policies["certified-without-owner"])
    assert result.subjects_scanned == 3
    assert [v.subject.urn for v in result.violations] == [ENCOUNTERS]


def test_stale_upstream_rule(catalog, policies):
    result = evaluate(catalog, policies["stale-upstream-feeds-live"])
    assert len(result.violations) == 1
    violation = result.violations[0]
    assert "patient_360" in violation.subject.urn
    assert "lab_results" in violation.sink.urn
    assert violation.path.length == 2


def test_findings_are_stable_across_runs(catalog, policies):
    """Re-running a scan must not create new finding ids, or write-back duplicates."""
    first = evaluate(catalog, policies["pii-reaches-bi"])
    second = evaluate(FixtureCatalog.load("healthcare"), policies["pii-reaches-bi"])
    assert [v.id for v in first.violations] == [v.id for v in second.violations]


def test_a_broken_policy_does_not_sink_the_scan(catalog):
    broken = Policy.from_dict(
        {
            "id": "broken",
            "subject": {"entity_type": "dataset", "search": "tags:(("},
            "condition": {"missing_owner": True},
        }
    )
    result = evaluate(catalog, broken)
    assert result.error is not None
    assert not result.violations


def test_writeback_applies_all_three_layers(tmp_path, catalog, policies):
    policy = policies["pii-reaches-bi"]
    result = evaluate(catalog, policy)
    writer = WriteBackWriter(
        catalog=catalog,
        run_id="test-run",
        config=WriteBackConfig(enabled=True, dry_run=False, out_dir=tmp_path),
    )
    violation = result.violations[0]

    before = catalog.snapshot(violation.subject.urn)
    writes = writer.apply(violation, policy)
    after = catalog.snapshot(violation.subject.urn)

    kinds = {w.kind for w in writes}
    assert {"tag", "structured_property", "document"} <= kinds
    assert all(w.applied for w in writes if w.kind in {"tag", "structured_property", "document"})

    assert "policy-violation" not in before.get("tags", [])
    assert "policy-violation" in after["tags"]
    assert "urn:li:structuredProperty:io.kestrel.policy_violation" in after["properties"]

    # The exposure point is tagged too, so the finding is discoverable from the
    # dashboard as well as from the column.
    assert "policy-violation" in catalog.snapshot(violation.sink.urn)["tags"]

    payload = json.loads(after["properties"]["urn:li:structuredProperty:io.kestrel.policy_violation"])
    assert payload["policy_id"] == "pii-reaches-bi"
    assert payload["sink_urn"] == DASHBOARD
    assert payload["hops"] == 4

    saved = catalog.documents[0]
    assert violation.subject.urn in saved["related"]
    assert violation.sink.urn in saved["related"], "the doc links both ends of the path"
    assert violation.path.render(" -> ") in saved["content"]
    assert (tmp_path / "documents" / f"{violation.id}.md").exists()


def test_dry_run_writes_nothing_to_the_catalog(tmp_path, catalog, policies):
    policy = policies["pii-reaches-bi"]
    result = evaluate(catalog, policy)
    writer = WriteBackWriter(
        catalog=catalog,
        run_id="test-run",
        config=WriteBackConfig(enabled=True, dry_run=True, out_dir=tmp_path),
    )
    violation = result.violations[0]
    writes = writer.apply(violation, policy)

    assert all(w.dry_run and not w.applied for w in writes)
    assert "policy-violation" not in catalog.snapshot(violation.subject.urn)["tags"]
    assert not catalog.documents
    # The document is still mirrored to disk, so a dry run is reviewable.
    assert (tmp_path / "documents" / f"{violation.id}.md").exists()


def test_actions_are_drafted_not_sent(tmp_path, catalog, policies):
    policy = policies["stale-upstream-feeds-live"]
    result = evaluate(catalog, policy)
    writer = WriteBackWriter(
        catalog=catalog,
        run_id="test-run",
        config=WriteBackConfig(enabled=True, dry_run=False, out_dir=tmp_path),
    )
    writes = writer.apply(result.violations[0], policy)
    pr = next(w for w in writes if w.kind == "pr")
    assert pr.dry_run and not pr.applied
    assert "gh pr create" in pr.payload["command"]
    assert (tmp_path / "actions").exists()


def test_incident_document_carries_the_evidence(catalog, policies):
    policy = policies["pii-reaches-bi"]
    result = evaluate(catalog, policy)
    violation = next(v for v in result.violations if v.subject.urn.endswith(",ssn)"))
    doc = incident_markdown(violation, policy, "run-1", "http://localhost:9002")

    assert "# Policy violation: `pii-reaches-bi`" in doc
    assert "## The path" in doc
    assert "| # | From | To | Level | Transform |" in doc
    assert "```sql" in doc, "the real SQL behind the hops is the evidence"
    assert "patient_overview" in doc
    assert "## Suggested fix" in doc
    assert "localhost:9002/dataset/" in doc


def test_scan_report_serialises_and_exits_nonzero(catalog, policies):
    report = ScanReport(run_id="r", started_at=utc_now(), mode="offline")
    for policy in policies.values():
        report.results.append(evaluate(catalog, policy))

    assert report.exit_code == 1
    data = report.to_dict()
    assert data["summary"]["violations"] == len(report.violations) == 6
    assert data["summary"]["bySeverity"]["high"] == 4
    assert json.loads(json.dumps(data))  # must be JSON-clean for the web report

    markdown = report_markdown(report, policies)
    assert "# Kestrel scan report" in markdown
    assert "pii-reaches-bi" in markdown


def test_clean_catalog_exits_zero(policies):
    empty = FixtureCatalog(data={"entities": [], "edges": []})
    report = ScanReport(run_id="r", started_at=utc_now(), mode="offline")
    for policy in policies.values():
        report.results.append(TemplateEngine(empty).evaluate(policy))
    assert report.violations == []
    assert report.exit_code == 0
