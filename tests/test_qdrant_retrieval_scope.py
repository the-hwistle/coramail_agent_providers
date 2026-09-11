from __future__ import annotations

from uuid import UUID

import pytest

from app.evaluation.synthetic_dataset import SyntheticDatasetConfig, SyntheticEvaluationDatasetGenerator
from app.retrieval.qdrant_client import QdrantConfig, QdrantRetrievalError, QdrantSimilarCaseRetriever
from app.schemas.retrieval import RetrievalQuery, RetrievalScope, RetrieverType


class FakeGateway:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class RecordingQdrant(QdrantSimilarCaseRetriever):
    def __init__(self):
        super().__init__(FakeGateway(), QdrantConfig(base_url="http://qdrant.invalid", collection="cases"))
        self.last_payload = None

    def _post(self, path, payload):
        self.last_payload = payload
        return {"result": []}


def _query(filters=None):
    return RetrievalQuery(
        purpose="similar_confirmed_cases",
        retriever_type=RetrieverType.SIMILAR_CASE,
        query_text="pump order",
        filters=filters or {"confirmed_only": True},
        limit=5,
    )


def _scope(**overrides):
    values = {
        "purpose": "assignment_routing",
        "provider": "gmail",
        "dataset_type": "production",
        "email_account_id": UUID("11111111-1111-1111-1111-111111111111"),
        "allow_synthetic": False,
        "allow_evaluation": False,
    }
    values.update(overrides)
    return RetrievalScope(**values)


def _must_map(filter_payload):
    result = {}
    for condition in filter_payload["must"]:
        result.setdefault(condition["key"], []).append(condition["match"]["value"])
    return result


def test_gmail_production_routing_requires_gmail_production_scope():
    qdrant = RecordingQdrant()

    qdrant.search(_query(), _scope())

    must = _must_map(qdrant.last_payload["filter"])
    assert must["provider"] == ["gmail"]
    assert must["dataset_type"] == ["production"]
    assert must["synthetic"] == [False]
    assert must["evaluation"] == [False]
    assert must["email_account_id"] == ["11111111-1111-1111-1111-111111111111"]


@pytest.mark.parametrize(
    ("payload_key", "safe_value"),
    [
        ("synthetic", False),
        ("dataset_type", "production"),
        ("evaluation", False),
        ("provider", "gmail"),
    ],
)
def test_gmail_production_scope_excludes_synthetic_demo_evaluation_and_other_providers(payload_key, safe_value):
    qdrant = RecordingQdrant()

    qdrant.search(_query(), _scope())

    must = _must_map(qdrant.last_payload["filter"])
    assert safe_value in must[payload_key]


def test_legacy_points_without_dataset_metadata_are_not_treated_as_production():
    qdrant = RecordingQdrant()

    qdrant.search(_query(filters={}), _scope())

    must = _must_map(qdrant.last_payload["filter"])
    assert "provider" in must
    assert "dataset_type" in must
    assert "synthetic" in must
    assert "evaluation" in must


def test_planner_can_omit_dataset_filter_but_runtime_scope_still_applies():
    qdrant = RecordingQdrant()

    qdrant.search(_query(filters={"confirmed_only": True}), _scope())

    must = _must_map(qdrant.last_payload["filter"])
    assert must["dataset_type"] == ["production"]


def test_conflicting_planner_dataset_filter_cannot_remove_mandatory_scope():
    qdrant = RecordingQdrant()
    query = _query(
        filters={
            "confirmed_only": True,
            "qdrant_filter": {"must": [{"key": "dataset_type", "match": {"value": "evaluation"}}]},
        }
    )

    qdrant.search(query, _scope())

    must = _must_map(qdrant.last_payload["filter"])
    assert must["dataset_type"] == ["evaluation", "production"]


def test_assignment_confirmed_false_filter_conflicts_instead_of_overriding_mandatory_true():
    qdrant = RecordingQdrant()
    query = _query(
        filters={
            "qdrant_filter": {"must": [{"key": "assignment_confirmed", "match": {"value": False}}]},
        }
    )

    qdrant.search(query, _scope())

    must = _must_map(qdrant.last_payload["filter"])
    assert must["assignment_confirmed"] == [False, True]


def test_query_specific_filter_is_preserved_with_mandatory_scope():
    qdrant = RecordingQdrant()
    query = _query(
        filters={
            "qdrant_filter": {"must": [{"key": "customer_name", "match": {"value": "ACME"}}]},
        }
    )

    qdrant.search(query, _scope())

    must = _must_map(qdrant.last_payload["filter"])
    assert must["customer_name"] == ["ACME"]
    assert must["provider"] == ["gmail"]


def test_demo_context_requires_demo_synthetic_non_evaluation_scope():
    qdrant = RecordingQdrant()

    qdrant.search(
        _query(),
        _scope(provider="synthetic", dataset_type="demo", email_account_id=None, allow_synthetic=True),
    )

    must = _must_map(qdrant.last_payload["filter"])
    assert must["provider"] == ["synthetic"]
    assert must["dataset_type"] == ["demo"]
    assert must["synthetic"] == [True]
    assert must["evaluation"] == [False]


def test_evaluation_scope_requires_designated_evaluation_dataset():
    qdrant = RecordingQdrant()

    qdrant.search(
        _query(),
        _scope(
            purpose="evaluation",
            provider="synthetic",
            dataset_type="evaluation",
            email_account_id=None,
            dataset_version="synthetic-mail-decision-v2-clean",
            allow_synthetic=True,
            allow_evaluation=True,
        ),
    )

    must = _must_map(qdrant.last_payload["filter"])
    assert must["provider"] == ["synthetic"]
    assert must["dataset_type"] == ["evaluation"]
    assert must["dataset_version"] == ["synthetic-mail-decision-v2-clean"]
    assert must["evaluation"] == [True]


def test_qdrant_search_fails_closed_without_scope():
    qdrant = RecordingQdrant()

    with pytest.raises(QdrantRetrievalError):
        qdrant.search(_query())


def test_synthetic_evaluation_cases_carry_provider_and_dataset_provenance():
    dataset = SyntheticEvaluationDatasetGenerator(
        SyntheticDatasetConfig(
            dataset_version="synthetic-mail-decision-v2-clean",
            clean_retrieval_cases=True,
            email_count=4,
            ground_truth_count=2,
            attachment_count=0,
        )
    ).generate()

    payload = dataset["qdrant_cases"][0]["payload"]
    assert payload["provider"] == "synthetic"
    assert payload["dataset_type"] == "evaluation"
    assert payload["evaluation"] is True
    assert payload["synthetic"] is True
