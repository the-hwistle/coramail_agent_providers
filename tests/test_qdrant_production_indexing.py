from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.repositories.postgres_routing_repository import PostgresRoutingRepository
from app.retrieval.qdrant_client import QdrantConfig, QdrantSimilarCaseRetriever
from app.retrieval.qdrant_indexing import (
    QdrantCaseIndexClient,
    ProductionSimilarCaseIndexer,
    build_production_similar_case_point,
)
from app.schemas.retrieval import RetrievalQuery, RetrievalScope, RetrieverType


class FakeGateway:
    def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]


class RecordingRetriever(QdrantSimilarCaseRetriever):
    def __init__(self):
        super().__init__(FakeGateway(), QdrantConfig(base_url="http://qdrant.invalid", collection="cases"))

    def _post(self, path, payload):
        self.payload = payload
        return {"result": []}


class FakeQdrantCaseClient(QdrantCaseIndexClient):
    def __init__(self):
        super().__init__(base_url="http://qdrant.invalid", collection="cases")
        self.upserts = []
        self.ensure_sizes = []

    def ensure_collection(self, vector_size):
        self.ensure_sizes.append(vector_size)

    def upsert_point(self, point, vector):
        self.upserts.append((point, vector))


class FakeVerificationClient(QdrantCaseIndexClient):
    def __init__(self):
        super().__init__(base_url="http://qdrant.invalid", collection="cases")
        self.count_filters = []

    def _count(self, filter_payload):
        self.count_filters.append(filter_payload)
        return len(self.count_filters)


class FakeIndexer(ProductionSimilarCaseIndexer):
    def __init__(self, rows):
        self.rows = {UUID(str(row["email_message_id"])): row for row in rows}
        self.qdrant_client = FakeQdrantCaseClient()
        super().__init__(
            database_url="",
            qdrant_client=self.qdrant_client,
            embedder=lambda texts: [[0.1, 0.2, 0.3] for _ in texts],
            embedding_model="test-embed",
        )
        self.saved = []

    def _load_email_case(self, email_message_id):
        return self.rows.get(email_message_id)

    def _save_index_record(self, point, embedding_dimension):
        self.saved.append((point, embedding_dimension))


def _row(**overrides):
    now = datetime(2026, 8, 14, tzinfo=timezone.utc)
    values = {
        "email_message_id": uuid4(),
        "email_account_id": UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        "provider": "gmail",
        "subject": "Pump quotation request",
        "body_text": "Please quote pump parts.",
        "snippet": "Please quote pump parts.",
        "sender_domain": "customer.example",
        "source_updated_at": now,
        "assignee_user_id": UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        "assignment_status": "assigned",
        "assignment_source": "user",
        "assigned_at": now,
        "fixed_at": now,
        "forwarded_at": None,
        "completed_at": None,
        "assignment_updated_at": now,
        "business_type": "quotation_request",
        "decision_summary": "Customer requests pump quotation.",
        "facts_text": '{"request_types":["quotation_request"]}',
    }
    values.update(overrides)
    return values


def _production_scope(account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")):
    return RetrievalScope(
        provider="gmail",
        dataset_type="production",
        email_account_id=account_id,
        allow_synthetic=False,
        allow_evaluation=False,
    )


def _mandatory_values(scope):
    retriever = RecordingRetriever()
    query = RetrievalQuery(
        purpose="similar_confirmed_cases",
        retriever_type=RetrieverType.SIMILAR_CASE,
        query_text="pump quotation",
    )
    filter_payload = retriever.build_effective_filter(query, scope)
    return {item["key"]: item["match"]["value"] for item in filter_payload["must"]}


def _matches_scope(payload, scope):
    mandatory = _mandatory_values(scope)
    return all(payload.get(key) == value for key, value in mandatory.items())


def test_production_gmail_indexing_payload_contains_required_provenance():
    point = build_production_similar_case_point(_row())
    payload = point.payload

    assert payload["provider"] == "gmail"
    assert payload["dataset_type"] == "production"
    assert payload["synthetic"] is False
    assert payload["evaluation"] is False
    assert payload["email_account_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert payload["assignment_confirmed"] is True
    assert payload["historical_assignee_user_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def test_production_point_matches_runtime_production_scope():
    point = build_production_similar_case_point(_row())

    assert _matches_scope(point.payload, _production_scope()) is True


def test_legacy_synthetic_evaluation_and_other_account_points_do_not_match_production_scope():
    scope = _production_scope()
    production = build_production_similar_case_point(_row()).payload
    legacy = {"assignment_confirmed": True}
    synthetic = {**production, "provider": "synthetic", "synthetic": True, "dataset_type": "demo"}
    evaluation = {**production, "provider": "synthetic", "synthetic": True, "dataset_type": "evaluation", "evaluation": True}
    account_b = {**production, "email_account_id": "cccccccc-cccc-cccc-cccc-cccccccccccc"}

    assert _matches_scope(legacy, scope) is False
    assert _matches_scope(synthetic, scope) is False
    assert _matches_scope(evaluation, scope) is False
    assert _matches_scope(account_b, scope) is False


def test_assignment_confirmed_false_point_is_excluded_from_similar_case_scope():
    point = build_production_similar_case_point(
        _row(assignee_user_id=None, assignment_status="review_required", business_type="")
    )

    assert point.payload["assignment_confirmed"] is False
    assert "historical_assignee_user_id" not in point.payload
    assert _matches_scope(point.payload, _production_scope()) is False


def test_assignment_confirmation_update_makes_point_enter_retrieval_scope():
    email_id = uuid4()
    indexer = FakeIndexer(
        [
            _row(
                email_message_id=email_id,
                assignee_user_id=None,
                assignment_status="review_required",
                business_type="",
            )
        ]
    )

    first = indexer.index_email(email_id)
    indexer.rows[email_id] = _row(email_message_id=email_id, assignment_status="assigned")
    second = indexer.index_email(email_id)

    assert first.point_id == second.point_id
    assert first.payload["assignment_confirmed"] is False
    assert second.payload["assignment_confirmed"] is True
    assert _matches_scope(second.payload, _production_scope()) is True


def test_reassignment_overwrites_stale_assignee_provenance_on_same_point():
    email_id = uuid4()
    replacement_user = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
    indexer = FakeIndexer([_row(email_message_id=email_id)])

    first = indexer.index_email(email_id)
    indexer.rows[email_id] = _row(email_message_id=email_id, assignee_user_id=replacement_user)
    second = indexer.index_email(email_id)

    assert first.point_id == second.point_id
    assert first.payload["historical_assignee_user_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert second.payload["historical_assignee_user_id"] == str(replacement_user)
    assert indexer.qdrant_client.upserts[-1][0].payload["historical_assignee_user_id"] == str(replacement_user)


def test_reindex_result_points_have_required_provenance_fields():
    rows = [_row(email_message_id=uuid4()), _row(email_message_id=uuid4(), assignment_status="forwarded")]
    indexer = FakeIndexer(rows)

    indexed = [indexer.index_email(UUID(str(row["email_message_id"]))) for row in rows]

    assert len(indexer.qdrant_client.upserts) == 2
    for point in indexed:
        assert {"provider", "dataset_type", "synthetic", "evaluation", "assignment_confirmed"}.issubset(
            point.payload
        )


def test_verification_counts_include_required_provenance_checks():
    client = FakeVerificationClient()

    counts = client.verification_counts()

    assert "missing_provider" in counts
    assert "production_invalid_synthetic" in counts
    assert "production_missing_email_account_id" in counts
    assert any({"is_empty": {"key": "provider"}} in item.get("must", []) for item in client.count_filters)


def test_routing_repository_assignment_index_sync_uses_optional_indexer():
    class Recorder:
        def __init__(self):
            self.email_ids = []

        def index_email(self, email_message_id):
            self.email_ids.append(email_message_id)

    recorder = Recorder()
    repository = PostgresRoutingRepository("", assignment_indexer=recorder)
    email_id = uuid4()

    repository.sync_assignment_index(email_id)

    assert recorder.email_ids == [email_id]
