from __future__ import annotations

from uuid import uuid4

from app.agents.decision_agent import DecisionAgentOutput
from app.schemas.mail_decision import MailClassification, MailImportance, MailSummary, MailUrgency
from app.services.postgres_email_analysis_worker import PostgresEmailAnalysisWorker


def _decision_output() -> DecisionAgentOutput:
    return DecisionAgentOutput(
        summary=MailSummary(
            one_line_summary="견적 요청",
            requested_actions=["견적서 작성"],
            business_refs=["QT-100"],
            confidence=0.91,
        ),
        classification=MailClassification(
            business_area="sales",
            primary_type="quotation_request",
            candidate_scores={"quotation_request": 0.91},
            confidence=0.91,
        ),
        urgency=MailUrgency(level="normal", confidence=0.8, reasons=[]),
        importance=MailImportance(level="normal", confidence=0.8, reasons=[]),
        requested_actions=["견적서 작성"],
    )


def test_mail_decision_job_runs_actual_mail_decision_path():
    class Worker(PostgresEmailAnalysisWorker):
        def __init__(self):
            super().__init__("postgresql://example")
            self.ran_for: list[str] = []
            self.success_ids: list[str] = []

        def _run_mail_decision(self, email_uid: str) -> DecisionAgentOutput:
            self.ran_for.append(email_uid)
            return _decision_output()

        def _mark_job_success(self, conn, job_id: str) -> None:
            self.success_ids.append(job_id)

    email_uid = str(uuid4())
    job_id = str(uuid4())
    worker = Worker()

    result = worker._process_job(
        object(),
        {
            "id": job_id,
            "source_id": email_uid,
            "metadata": {"analysis_type": "mail_decision"},
        },
    )

    assert worker.ran_for == [email_uid]
    assert worker.success_ids == [job_id]
    assert result["status"] == "success"
    assert result["source"] == "mail_decision"
    assert result["category"] == "문의"
