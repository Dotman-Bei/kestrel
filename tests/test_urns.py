"""URN parsing. Nested URNs are the thing naive splitting gets wrong."""

from policy_sentinel import urns

DATASET = "urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.raw.patients,PROD)"
FIELD = f"urn:li:schemaField:({DATASET},ssn)"
DASHBOARD = "urn:li:dashboard:(looker,patient_overview)"


def test_entity_type():
    assert urns.entity_type(DATASET) == "dataset"
    assert urns.entity_type(FIELD) == "schemaField"
    assert urns.entity_type(DASHBOARD) == "dashboard"
    assert urns.entity_type("not-a-urn") == ""


def test_nested_split_does_not_break_on_inner_commas():
    parts = urns.urn_parts(DATASET)
    assert parts == ["urn:li:dataPlatform:snowflake", "healthcare.raw.patients", "PROD"]

    field_parts = urns.urn_parts(FIELD)
    assert field_parts == [DATASET, "ssn"]


def test_field_helpers():
    assert urns.is_field(FIELD)
    assert not urns.is_field(DATASET)
    assert urns.dataset_of_field(FIELD) == DATASET
    assert urns.field_path(FIELD) == "ssn"
    assert urns.make_field_urn(DATASET, "ssn") == FIELD


def test_platform_and_names():
    assert urns.platform_of(DATASET) == "snowflake"
    assert urns.platform_of(FIELD) == "snowflake"
    assert urns.platform_of(DASHBOARD) == "looker"
    assert urns.dataset_name(DATASET) == "healthcare.raw.patients"
    assert urns.dataset_name(FIELD) == "healthcare.raw.patients"


def test_display_names():
    assert urns.short_name(FIELD) == "patients.ssn"
    assert urns.short_name(DATASET) == "patients"
    assert urns.short_name(DASHBOARD) == "patient_overview"
    assert urns.qualified_name(FIELD) == "healthcare.raw.patients.ssn"
    assert urns.qualified_name(DATASET) == "healthcare.raw.patients"


def test_tag_helpers():
    assert urns.tag_urn("PII") == "urn:li:tag:PII"
    assert urns.tag_urn("urn:li:tag:PII") == "urn:li:tag:PII"
    assert urns.tag_name("urn:li:tag:PII") == "PII"
    assert urns.tag_name("PII") == "PII"
