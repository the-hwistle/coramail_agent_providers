from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from app.config import (
    database_url,
    embedding_base_url,
    embedding_model,
    embedding_provider,
    llm_base_url,
    llm_max_concurrency,
    llm_max_output_tokens,
    llm_provider,
    qdrant_case_collection,
    qdrant_url,
    text_llm_base_url,
    text_llm_provider,
    text_model,
    vision_llm_base_url,
    vision_llm_provider,
    vision_model,
)
from app.document_processing.parsers import AttachmentParserDispatcher
from app.document_processing.text_analyzer import TextAttachmentAnalyzer
from app.llm.gateway import LocalLLMConfig, LocalLLMGateway
from app.repositories.gmail_account_repository import GmailAccountRepository
from app.repositories.postgres_assignee_admin_repository import PostgresAssigneeAdminRepository
from app.repositories.postgres_attachment_analysis_repository import PostgresAttachmentAnalysisRepository
from app.repositories.postgres_gmail_sync_repository import PostgresGmailSyncRepository
from app.repositories.postgres_job_repository import PostgresJobRepository
from app.repositories.postgres_mail_decision_repository import PostgresMailDecisionRepository
from app.repositories.postgres_mail_read_repository import PostgresMailReadRepository
from app.repositories.postgres_routing_policy_settings_repository import PostgresRoutingPolicySettingsRepository
from app.repositories.postgres_routing_repository import PostgresRoutingRepository
from app.repositories.postgres_user_repository import PostgresUserRepository
from app.repositories.postgres_work_tracking_repository import PostgresWorkTrackingRepository
from app.retrieval.qdrant_indexing import ProductionSimilarCaseIndexer, QdrantCaseIndexClient
from app.services.gmail_mail_service import GmailMailboxService
from app.services.gmail_oauth_service import GmailOAuthService
from app.services.hiworks_mail_service import HiworksMailboxService
from app.services.mail_chat_service import MailChatService, MailChatSessionStore
from app.services.naver_mail_service import NaverMailboxService
from app.services.postgres_email_analysis_worker import PostgresEmailAnalysisWorker
from app.services.postgres_mail_service import PostgresMailboxService


@dataclass(slots=True)
class ServerRuntime:
    gmail_account_repository: GmailAccountRepository
    gmail_oauth_service: GmailOAuthService
    postgres_service: PostgresMailboxService
    gmail_postgres_service: PostgresMailboxService
    naver_postgres_service: PostgresMailboxService
    hiworks_postgres_service: PostgresMailboxService
    postgres_gmail_sync_repository: PostgresGmailSyncRepository
    postgres_naver_sync_repository: PostgresGmailSyncRepository
    postgres_hiworks_sync_repository: PostgresGmailSyncRepository
    postgres_job_repository: PostgresJobRepository
    postgres_mail_decision_repository: PostgresMailDecisionRepository
    postgres_email_analysis_worker: PostgresEmailAnalysisWorker
    postgres_assignee_admin_repository: PostgresAssigneeAdminRepository
    postgres_user_repository: PostgresUserRepository
    postgres_work_tracking_repository: PostgresWorkTrackingRepository
    postgres_mail_read_repository: PostgresMailReadRepository
    postgres_routing_repository: PostgresRoutingRepository
    postgres_routing_policy_settings_repository: PostgresRoutingPolicySettingsRepository
    gmail_service: GmailMailboxService
    naver_service: NaverMailboxService
    hiworks_service: HiworksMailboxService
    attachment_parser_dispatcher: AttachmentParserDispatcher
    local_llm_gateway: LocalLLMGateway
    production_case_indexer: ProductionSimilarCaseIndexer | None
    mail_search_embedding_cache: dict[str, list[float]]
    mail_chat_service: MailChatService
    attachment_understanding_analyzer: TextAttachmentAnalyzer
    postgres_attachment_analysis_repository: PostgresAttachmentAnalysisRepository
    attachment_reanalysis_lock: Lock


def build_server_runtime(project_dir: Path) -> ServerRuntime:
    gmail_account_repository = GmailAccountRepository(project_dir)
    postgres_service = PostgresMailboxService(database_url(), project_dir, provider="synthetic")
    gmail_postgres_service = PostgresMailboxService(database_url(), project_dir, provider="gmail")
    naver_postgres_service = PostgresMailboxService(database_url(), project_dir, provider="naver")
    hiworks_postgres_service = PostgresMailboxService(database_url(), project_dir, provider="hiworks")
    postgres_gmail_sync_repository = PostgresGmailSyncRepository(database_url(), project_dir)
    postgres_naver_sync_repository = PostgresGmailSyncRepository(
        database_url(),
        project_dir,
        provider="naver",
        credentials_reference="runtime:naver-app-password",
    )
    postgres_hiworks_sync_repository = PostgresGmailSyncRepository(
        database_url(),
        project_dir,
        provider="hiworks",
        credentials_reference="runtime:hiworks-app-password",
    )
    postgres_job_repository = PostgresJobRepository(database_url())
    postgres_mail_decision_repository = PostgresMailDecisionRepository(database_url())
    postgres_email_analysis_worker = PostgresEmailAnalysisWorker(database_url())
    postgres_assignee_admin_repository = PostgresAssigneeAdminRepository(database_url())
    postgres_user_repository = PostgresUserRepository(database_url())
    postgres_work_tracking_repository = PostgresWorkTrackingRepository(
        database_url(),
        overdue_hours=int(os.getenv("CORAMAIL_WORK_OVERDUE_HOURS", "24")),
    )
    postgres_mail_read_repository = PostgresMailReadRepository(database_url())
    postgres_routing_repository = PostgresRoutingRepository(
        database_url(),
        work_tracking_repository=postgres_work_tracking_repository,
    )
    postgres_routing_policy_settings_repository = PostgresRoutingPolicySettingsRepository(database_url())
    gmail_oauth_service = GmailOAuthService(gmail_account_repository)
    gmail_service = GmailMailboxService(
        project_dir,
        gmail_account_repository,
        postgres_mailbox=gmail_postgres_service if database_url() else None,
        sync_repository=postgres_gmail_sync_repository,
        routing_repository=postgres_routing_repository,
        job_repository=postgres_job_repository,
        analysis_worker=postgres_email_analysis_worker,
        work_tracking_repository=postgres_work_tracking_repository,
    )
    naver_service = NaverMailboxService(
        project_dir,
        postgres_mailbox=naver_postgres_service if database_url() else None,
        sync_repository=postgres_naver_sync_repository,
    )
    hiworks_service = HiworksMailboxService(
        project_dir,
        postgres_mailbox=hiworks_postgres_service if database_url() else None,
        sync_repository=postgres_hiworks_sync_repository,
    )
    attachment_parser_dispatcher = AttachmentParserDispatcher(project_dir)
    local_llm_gateway = LocalLLMGateway(
        LocalLLMConfig(
            base_url=llm_base_url(),
            text_base_url=text_llm_base_url(),
            vision_base_url=vision_llm_base_url(),
            embedding_base_url=embedding_base_url(),
            text_model=text_model(),
            vision_model=vision_model(),
            embedding_model=embedding_model(),
            provider=llm_provider(),
            text_provider=text_llm_provider(),
            vision_provider=vision_llm_provider(),
            embedding_provider=embedding_provider(),
            text_max_concurrency=llm_max_concurrency("text"),
            vision_max_concurrency=llm_max_concurrency("vision"),
            embedding_max_concurrency=llm_max_concurrency("embedding"),
            max_output_tokens=llm_max_output_tokens(),
        )
    )
    production_case_indexer = (
        ProductionSimilarCaseIndexer(
            database_url=database_url(),
            qdrant_client=QdrantCaseIndexClient(base_url=qdrant_url(), collection=qdrant_case_collection()),
            embedder=local_llm_gateway.embed,
            embedding_model=embedding_model(),
        )
        if database_url()
        else None
    )
    postgres_routing_repository.assignment_indexer = production_case_indexer

    return ServerRuntime(
        gmail_account_repository=gmail_account_repository,
        gmail_oauth_service=gmail_oauth_service,
        postgres_service=postgres_service,
        gmail_postgres_service=gmail_postgres_service,
        naver_postgres_service=naver_postgres_service,
        hiworks_postgres_service=hiworks_postgres_service,
        postgres_gmail_sync_repository=postgres_gmail_sync_repository,
        postgres_naver_sync_repository=postgres_naver_sync_repository,
        postgres_hiworks_sync_repository=postgres_hiworks_sync_repository,
        postgres_job_repository=postgres_job_repository,
        postgres_mail_decision_repository=postgres_mail_decision_repository,
        postgres_email_analysis_worker=postgres_email_analysis_worker,
        postgres_assignee_admin_repository=postgres_assignee_admin_repository,
        postgres_user_repository=postgres_user_repository,
        postgres_work_tracking_repository=postgres_work_tracking_repository,
        postgres_mail_read_repository=postgres_mail_read_repository,
        postgres_routing_repository=postgres_routing_repository,
        postgres_routing_policy_settings_repository=postgres_routing_policy_settings_repository,
        gmail_service=gmail_service,
        naver_service=naver_service,
        hiworks_service=hiworks_service,
        attachment_parser_dispatcher=attachment_parser_dispatcher,
        local_llm_gateway=local_llm_gateway,
        production_case_indexer=production_case_indexer,
        mail_search_embedding_cache={},
        mail_chat_service=MailChatService(MailChatSessionStore()),
        attachment_understanding_analyzer=TextAttachmentAnalyzer(local_llm_gateway),
        postgres_attachment_analysis_repository=PostgresAttachmentAnalysisRepository(database_url()),
        attachment_reanalysis_lock=Lock(),
    )
