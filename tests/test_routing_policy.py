from uuid import uuid4

from app.routing.policy import RoutingPolicy
from app.schemas.mail_decision import MailClassification, MailFacts
from app.schemas.retrieval import RetrievalContext, RetrievalHit, RetrieverType


def _classification(confidence: float = 0.9) -> MailClassification:
    return MailClassification(
        business_area="order",
        primary_type="purchase_order",
        secondary_types=[],
        candidate_scores={"purchase_order": confidence},
        confidence=confidence,
    )


def _retrieval(user_id):
    return RetrievalContext(
        cycles=[],
        selected_hits=[
            RetrievalHit(
                retriever_type=RetrieverType.EXACT,
                source_type="email_message",
                source_id=uuid4(),
                title="confirmed history",
                content="confirmed assignee",
                retrieval_score=1.0,
                metadata={"assignee_user_id": str(user_id)},
            )
        ],
        sufficient=True,
        missing_context=[],
    )


def test_auto_assigns_only_when_threshold_and_margin_pass():
    first, second = uuid4(), uuid4()
    users = [
        {
            "id": first,
            "status": "active",
            "capabilities": [
                {"capability_type": "customer", "capability_value": "Acme"},
                {"capability_type": "product", "capability_value": "Pump"},
                {"capability_type": "business_type", "capability_value": "purchase_order"},
                {"capability_type": "project", "capability_value": "P-100"},
            ],
        },
        {"id": second, "status": "active", "capabilities": []},
    ]
    decision = RoutingPolicy().score(
        users=users,
        facts=MailFacts(customer_name="Acme", product_names=["Pump"], project_numbers=["P-100"]),
        classification=_classification(),
        retrieval=_retrieval(first),
    )
    assert decision.decision == "auto_assign"
    assert decision.selected_user_id == first
    assert decision.candidates[0].total_score >= 0.82


def test_routes_to_review_when_margin_is_too_small():
    first, second = uuid4(), uuid4()
    shared = [
        {"capability_type": "customer", "capability_value": "Acme"},
        {"capability_type": "product", "capability_value": "Pump"},
        {"capability_type": "business_type", "capability_value": "purchase_order"},
    ]
    users = [
        {"id": first, "status": "active", "capabilities": shared},
        {"id": second, "status": "active", "capabilities": shared},
    ]
    decision = RoutingPolicy().score(
        users=users,
        facts=MailFacts(customer_name="Acme", product_names=["Pump"]),
        classification=_classification(),
        retrieval=_retrieval(first),
    )
    assert decision.decision == "review_required"
    assert "candidate_margin_too_small" in decision.review_reasons


def test_routes_to_review_without_required_entity_evidence():
    user_id = uuid4()
    decision = RoutingPolicy().score(
        users=[{"id": user_id, "status": "active", "capabilities": []}],
        facts=MailFacts(),
        classification=_classification(),
        retrieval=_retrieval(user_id),
    )
    assert decision.decision == "review_required"
    assert "required_routing_evidence_missing" in decision.review_reasons


def test_routes_to_review_when_classification_requires_review():
    user_id = uuid4()
    classification = _classification().model_copy(update={"review_required": True})
    decision = RoutingPolicy().score(
        users=[
            {
                "id": user_id,
                "status": "active",
                "capabilities": [
                    {"capability_type": "customer", "capability_value": "Acme"},
                    {"capability_type": "product", "capability_value": "Pump"},
                    {"capability_type": "business_type", "capability_value": "purchase_order"},
                    {"capability_type": "project", "capability_value": "P-100"},
                ],
            }
        ],
        facts=MailFacts(customer_name="Acme", product_names=["Pump"], project_numbers=["P-100"]),
        classification=classification,
        retrieval=RetrievalContext(sufficient=True),
    )

    assert decision.decision == "review_required"
    assert "classification_review_required" in decision.review_reasons
