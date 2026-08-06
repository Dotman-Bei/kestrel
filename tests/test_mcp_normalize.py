"""Normalising MCP responses.

The server's envelope shape varies across versions, so the client harvests
entities structurally rather than assuming one layout. These cases are the
shapes DataHub actually emits.
"""

from policy_sentinel.mcp_client import harvest_entities, normalize_entity

DATASET = "urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.marts.patient_360,PROD)"


def test_flat_entity():
    entity = normalize_entity(
        {
            "urn": DATASET,
            "type": "DATASET",
            "name": "patient_360",
            "tags": ["urn:li:tag:Certified"],
            "owners": ["urn:li:corpuser:dana.okoro"],
        }
    )
    assert entity.type == "dataset"
    assert entity.tags == ["Certified"]
    assert entity.owners == ["urn:li:corpuser:dana.okoro"]
    assert entity.platform == "snowflake"


def test_graphql_shaped_entity():
    """The nested aspect shape DataHub's GraphQL layer returns."""
    entity = normalize_entity(
        {
            "urn": DATASET,
            "entityType": "dataset",
            "properties": {"name": "patient_360", "description": "certified view"},
            "platform": {"name": "snowflake"},
            "subTypes": {"typeNames": ["Table"]},
            "globalTags": {"tags": [{"tag": {"urn": "urn:li:tag:Certified"}}]},
            "ownership": {"owners": [{"owner": {"urn": "urn:li:corpuser:dana.okoro"}}]},
            "domain": {"domain": {"urn": "urn:li:domain:clinical"}},
        }
    )
    assert entity.sub_type == "Table"
    assert entity.tags == ["Certified"]
    assert entity.owners == ["urn:li:corpuser:dana.okoro"]
    assert entity.domain == "urn:li:domain:clinical"
    assert entity.description == "certified view"


def test_non_entities_are_skipped():
    assert normalize_entity({"name": "no urn here"}) is None
    assert normalize_entity({"urn": "not-a-datahub-urn"}) is None


def test_harvest_walks_arbitrary_nesting():
    payload = {
        "searchResults": [
            {"entity": {"urn": DATASET, "tags": ["urn:li:tag:Certified"]}},
            {"entity": {"urn": "urn:li:dashboard:(looker,patient_overview)"}},
        ],
        "extra": {"deep": [{"urn": "urn:li:chart:(looker,claims_by_age)"}]},
    }
    found = {e.urn for e in harvest_entities(payload)}
    assert len(found) == 3
    assert DATASET in found


def test_harvest_prefers_the_richest_mention():
    """The same URN often appears twice: once bare, once with metadata."""
    payload = [
        {"urn": DATASET},
        {"urn": DATASET, "tags": ["urn:li:tag:Certified"], "owners": ["urn:li:corpuser:x"]},
    ]
    entities = harvest_entities(payload)
    assert len(entities) == 1
    assert entities[0].tags == ["Certified"]


def test_schema_field_type_is_normalised():
    field = f"urn:li:schemaField:({DATASET},ssn)"
    entity = normalize_entity({"urn": field, "type": "SCHEMAFIELD"})
    assert entity.type == "schemaField"
    assert entity.is_column
    assert entity.name == "healthcare.marts.patient_360.ssn"
