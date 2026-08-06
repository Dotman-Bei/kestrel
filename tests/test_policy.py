"""Policy loading and validation. A bad policy must fail loudly, by name."""

import pytest
import yaml

from policy_sentinel.models import Entity
from policy_sentinel.policy import Policy, PolicyError, load_policies

VALID = {
    "id": "pii-reaches-bi",
    "severity": "high",
    "description": "PII must not reach BI.",
    "subject": {"entity_type": "column", "has_any_tag": ["PII", "Sensitive"]},
    "condition": {
        "lineage_reaches_type": ["Dashboard", "Chart"],
        "max_hops": 6,
        "without_step": "mask|hash",
    },
}


def test_valid_policy_round_trip():
    policy = Policy.from_dict(dict(VALID))
    assert policy.id == "pii-reaches-bi"
    assert policy.subject.is_column_level
    assert policy.condition.kind == "lineage_reaches_type"
    assert policy.condition.max_hops == 6
    assert policy.condition.without_step == ["mask|hash"]
    assert "must not reach a Dashboard/Chart within 6 hops" in policy.summary()


def test_yaml_round_trip_survives_reload():
    """A compiled policy must be re-loadable -- the agent saves rules this way."""
    policy = Policy.from_dict(dict(VALID))
    dumped = {
        "id": policy.id,
        "severity": policy.severity,
        "description": policy.description,
        "subject": policy.subject.to_yaml_dict(),
        "condition": policy.condition.to_yaml_dict(),
    }
    reloaded = Policy.from_dict(yaml.safe_load(yaml.safe_dump(dumped)))
    assert reloaded.summary() == policy.summary()
    assert reloaded.condition.max_hops == policy.condition.max_hops
    assert reloaded.subject.has_any_tag == policy.subject.has_any_tag


def test_upstream_condition_defaults_to_upstream_direction():
    policy = Policy.from_dict(
        {
            "id": "stale",
            "subject": {"entity_type": "dataset", "has_tag": "Certified"},
            "condition": {"upstream_has_tag": ["Stale"]},
        }
    )
    assert policy.condition.direction == "upstream"
    assert policy.condition.to_yaml_dict() == {"upstream_has_tag": "Stale"}


@pytest.mark.parametrize(
    "mutation, fragment",
    [
        ({"id": "Not Kebab"}, "kebab-case"),
        ({"severity": "catastrophic"}, "severity"),
        ({"condition": {}}, "exactly one of"),
        ({"condition": {"missing_owner": True, "lineage_reaches_type": "Dashboard"}}, "exactly one of"),
        ({"subject": {"has_tags": "PII"}}, "unknown subject key"),
        ({"condition": {"missing_owner": True, "hops": 3}}, "unknown condition key"),
        ({"on_violation": ["tag", "email"]}, "unknown on_violation"),
    ],
)
def test_invalid_policies_are_rejected(mutation, fragment):
    raw = dict(VALID)
    raw.update(mutation)
    with pytest.raises(PolicyError) as excinfo:
        Policy.from_dict(raw)
    assert fragment in str(excinfo.value)


def test_missing_id_is_rejected():
    raw = {k: v for k, v in VALID.items() if k != "id"}
    with pytest.raises(PolicyError):
        Policy.from_dict(raw)


def test_column_subject_query_widens_to_field_tags():
    """Columns are not search hits, so a column rule must find their datasets."""
    policy = Policy.from_dict(dict(VALID))
    query = policy.subject.to_dataset_query()
    assert "fieldTags:PII" in query
    assert "tags:PII" in query


def test_subject_matches_filters_structurally():
    policy = Policy.from_dict(dict(VALID))
    field = "urn:li:schemaField:(urn:li:dataset:(urn:li:dataPlatform:s,a.b.c,PROD),ssn)"
    assert policy.subject.matches(Entity(urn=field, tags=["PII"]))
    assert not policy.subject.matches(Entity(urn=field, tags=["Masked"]))
    # right tags, wrong entity type
    assert not policy.subject.matches(
        Entity(urn="urn:li:dataset:(urn:li:dataPlatform:s,a.b.c,PROD)", tags=["PII"])
    )


def test_shipped_policies_all_load():
    policies = load_policies("policies")
    ids = {p.id for p in policies}
    assert {"pii-reaches-bi", "certified-without-owner", "stale-upstream-feeds-live"} <= ids
    for policy in policies:
        assert policy.description, f"{policy.id} has no description"
        assert policy.summary()


def test_only_filter_rejects_unknown_id():
    with pytest.raises(PolicyError):
        load_policies("policies", only=["does-not-exist"])
