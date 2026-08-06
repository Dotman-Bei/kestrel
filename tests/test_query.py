"""The /q subset parser. It evaluates the same strings the live client sends."""

import pytest

from policy_sentinel.models import Entity
from policy_sentinel.query import QueryError, compile_query

DATASET = "urn:li:dataset:(urn:li:dataPlatform:snowflake,healthcare.marts.patient_360,PROD)"


def entity(**kwargs) -> Entity:
    base = {"urn": DATASET, "tags": [], "terms": [], "owners": []}
    base.update(kwargs)
    return Entity(**base)


def test_match_all():
    assert compile_query("*")(entity())
    assert compile_query("")(entity())


def test_tag_match_is_case_insensitive():
    e = entity(tags=["Certified", "Production"])
    assert compile_query("tags:certified")(e)
    assert compile_query("tags:CERTIFIED")(e)
    assert not compile_query("tags:Deprecated")(e)


def test_and_or_not():
    e = entity(tags=["Certified"], platform="snowflake")
    assert compile_query("tags:Certified AND platform:snowflake")(e)
    assert not compile_query("tags:Certified AND platform:postgres")(e)
    assert compile_query("(tags:Deprecated OR tags:Certified)")(e)
    assert compile_query("NOT tags:Deprecated")(e)
    assert not compile_query("NOT tags:Certified")(e)


def test_adjacency_means_and():
    e = entity(tags=["Certified"], platform="snowflake")
    assert compile_query("tags:Certified platform:snowflake")(e)
    assert not compile_query("tags:Certified platform:postgres")(e)


def test_tag_urns_are_matched_by_name():
    e = entity(tags=["urn:li:tag:PII"])
    assert compile_query("tags:PII")(e)


def test_colon_in_tag_value():
    e = entity(tags=["Quality:Failed"])
    assert compile_query("tags:Quality:Failed")(e)


def test_field_tags_resolve_through_properties():
    """`fieldTags` is a real DataHub index field; offline it lives in properties."""
    e = entity(properties={"fieldTags": ["PII", "Sensitive"]})
    assert compile_query("fieldTags:PII")(e)
    assert compile_query("(tags:PII OR fieldTags:PII)")(e)
    assert not compile_query("fieldTags:Masked")(e)


def test_name_matching_is_substring():
    assert compile_query("patient_360")(entity())
    assert compile_query("name:patient_360")(entity())
    assert not compile_query("nonexistent_table")(entity())


def test_quoted_values():
    e = entity(sub_type="Materialized View")
    assert compile_query('typeNames:"Materialized View"')(e)


def test_unbalanced_parens_raise():
    with pytest.raises(QueryError):
        compile_query("(tags:PII")
