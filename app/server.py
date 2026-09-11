from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import csv
import time
from collections import Counter, defaultdict
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, quote
from urllib.request import urlopen
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.config import (
    chat_text_model,
    database_url,
    embedding_base_url,
    embedding_model,
    embedding_provider,
    llm_base_url,
    llm_max_concurrency,
    llm_max_output_tokens,
    llm_provider,
    mail_provider,
    qdrant_case_collection,
    qdrant_url,
    text_llm_base_url,
    text_llm_provider,
    text_model,
    vision_llm_base_url,
    vision_llm_provider,
    vision_model,
)
from app.llm.gateway import LLMGatewayError, LocalLLMConfig, LocalLLMGateway
from app.mail_content import NON_CUSTOMER_SUBJECT_LABELS
from app.presentation.attachment_analysis import field_display_label
from app.presentation.summary_text import polish_korean_summary_text
from app.repositories.demo_mail_repository import DemoMailRepository
from app.repositories.postgres_assignee_admin_repository import CATEGORY_BUSINESS_TYPES
from app.schemas.attachment_analysis import AttachmentAnalysisStatus
from app.services.demo_mail_service import DemoMailService
from app.services.gmail_mail_service import GmailMailboxService
from app.services.hiworks_mail_service import HiworksMailboxService
from app.services.address_book_service import address_book_view, attach_sender_contacts, sender_contact_for_email
from app.services.mail_decision_runtime_client import (
    MailDecisionRuntimeClient,
    MailDecisionRuntimeClientConfig,
    MailDecisionRuntimeClientError,
    MailDecisionRuntimeConnectionError,
    MailDecisionRuntimeInvalidResponseError,
    MailDecisionRuntimeNotFoundError,
    MailDecisionRuntimeServerError,
    MailDecisionRuntimeTimeoutError,
    MailDecisionRuntimeValidationError,
)
from app.services.mail_search_service import MailSearchService, normalize_search_query
from app.services.naver_mail_service import NaverMailboxService
from app.services.postgres_mail_service import PostgresMailboxService
from app.web.application import build_web_application
from app.web.auth_session import decode_auth_cookie, encode_auth_cookie
from app.web.env_loader import load_dotenv_file as load_env_file
from app.web.runtime import build_server_runtime


logger = logging.getLogger(__name__)
APP_DIR = Path(__file__).resolve().parent
PROJECT_DIR = APP_DIR.parent
DEFAULT_ENV_PATH = PROJECT_DIR / ".env"
DEMO_DIR = PROJECT_DIR / "data" / "demo"
EVALUATION_DIR = PROJECT_DIR / "data" / "evaluation"
EVALUATION_REPORT_PATH = EVALUATION_DIR / "evaluation_report.json"
EVALUATION_CASES_PATH = EVALUATION_DIR / "evaluation_cases.csv"
EVALUATION_TRACE_PATH = EVALUATION_DIR / "evaluation_trace.jsonl"
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"
DEMO_SCREENSHOT_ACCOUNT_LABEL = "dawon.febsolution@gmail.com"
DEMO_SCREENSHOT_QUOTATION_EMAIL_UID = "0732e633-db61-536e-8ff3-b820826cf9a2"
DEMO_SCREENSHOT_QUOTATION_SUBJECT = "[견적서 송부] 산업용 네트워크 장비 및 전원모듈"
DEMO_SCREENSHOT_QUOTATION_COUNTERPARTY = "다원"
DISPLAY_TIMEZONE = ZoneInfo("Asia/Seoul")
KOREAN_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
BUSINESS_CATEGORY_ORDER = ["발주", "문의", "서비스", "기술", "기타", "미분류"]


def load_dotenv_file(env_path: str | Path | None = None) -> Path:
    return load_env_file(default_path=DEFAULT_ENV_PATH, env_path=env_path)


ACTIVE_ENV_PATH = load_dotenv_file()

from app.api.mail_decision import router as mail_decision_router  # noqa: E402
from app.api.system import build_system_router  # noqa: E402
from app.api.jobs import build_jobs_router  # noqa: E402
from app.api.mail_query import build_mail_query_router  # noqa: E402
from app.api.search import build_search_router  # noqa: E402
from app.api.mail_analysis import build_mail_analysis_router  # noqa: E402
from app.api.manual_routing import build_manual_routing_router  # noqa: E402
from app.api.attachments import build_attachment_router  # noqa: E402
from app.api.demo_noop import build_demo_noop_router  # noqa: E402
from app.ui.dashboard import build_dashboard_ui_router  # noqa: E402
from app.ui.inbox import build_inbox_ui_router, render_inbox  # noqa: E402
from app.ui.address_book import build_address_book_ui_router, render_address_book  # noqa: E402
from app.ui.work import build_work_ui_router  # noqa: E402
from app.ui.work_detail import (  # noqa: E402
    complete_work_item,
    initiate_work_reply,
    render_my_work_email_drawer,
    toggle_work_in_progress,
)
from app.ui.mail_decision_handlers import (  # noqa: E402
    confirm_top_review_candidate,
    create_mail_decision_run,
    latest_mail_decision_run,
    mail_decision_run,
    mail_decision_steps,
    manual_assign_review_email,
)
from app.ui.secondary import (  # noqa: E402
    render_chats,
    render_chats_results,
    render_chat_email_drawer,
    render_evaluation,
    render_evaluation_case,
    render_evaluation_trace,
    render_search,
    render_search_results,
)
from app.ui.settings_handlers import SettingsHandlers  # noqa: E402
from app.ui.mail_actions import MailActionHandlers  # noqa: E402
from app.ui.auth_root import AuthRootHandlers  # noqa: E402
from app.ui.monitoring import build_monitoring_ui_router  # noqa: E402
from app.ui.documents import build_documents_ui_router  # noqa: E402
from app.ui.mail_display import build_mail_display_ui_router  # noqa: E402
from app.web.server_routes import build_server_route_router  # noqa: E402

DISPLAY_MODE_COOKIE_NAME = os.getenv("CORAMAIL_DISPLAY_MODE_COOKIE_NAME", "coramail_display_mode")
GMAIL_OAUTH_STATE_COOKIE_NAME = os.getenv("CORAMAIL_GMAIL_OAUTH_STATE_COOKIE_NAME", "coramail_gmail_oauth_state")
AUTH_ENABLED = os.getenv("CORAMAIL_AUTH_ENABLED", "true").strip().casefold() not in {"0", "false", "off", "no"}
AUTH_USERNAME = os.getenv("CORAMAIL_AUTH_USERNAME", "admin")
AUTH_PASSWORD = os.getenv("CORAMAIL_AUTH_PASSWORD", "coramail")
AUTH_SECRET = os.getenv("CORAMAIL_AUTH_SECRET") or hashlib.sha256(
    f"{AUTH_USERNAME}:{AUTH_PASSWORD}:coramail-auth".encode("utf-8")
).hexdigest()
AUTH_COOKIE_NAME = os.getenv("CORAMAIL_AUTH_COOKIE_NAME", "coramail_session")
AUTH_SESSION_SECONDS = int(os.getenv("CORAMAIL_AUTH_SESSION_SECONDS", str(8 * 60 * 60)))
AUTH_COOKIE_SECURE = os.getenv("CORAMAIL_AUTH_COOKIE_SECURE", "false").strip().casefold() in {
    "1",
    "true",
    "on",
    "yes",
}
_display_demo_mode: ContextVar[bool | None] = ContextVar("coramail_display_demo_mode", default=None)
_runtime = build_server_runtime(PROJECT_DIR)
_gmail_account_repository = _runtime.gmail_account_repository
_gmail_oauth_service = _runtime.gmail_oauth_service
_postgres_service = _runtime.postgres_service
_gmail_postgres_service = _runtime.gmail_postgres_service
_naver_postgres_service = _runtime.naver_postgres_service
_hiworks_postgres_service = _runtime.hiworks_postgres_service
_postgres_gmail_sync_repository = _runtime.postgres_gmail_sync_repository
_postgres_naver_sync_repository = _runtime.postgres_naver_sync_repository
_postgres_hiworks_sync_repository = _runtime.postgres_hiworks_sync_repository
_postgres_job_repository = _runtime.postgres_job_repository
_postgres_mail_decision_repository = _runtime.postgres_mail_decision_repository
_postgres_email_analysis_worker = _runtime.postgres_email_analysis_worker
_postgres_assignee_admin_repository = _runtime.postgres_assignee_admin_repository
_postgres_user_repository = _runtime.postgres_user_repository
_postgres_work_tracking_repository = _runtime.postgres_work_tracking_repository
_postgres_mail_read_repository = _runtime.postgres_mail_read_repository
_postgres_routing_repository = _runtime.postgres_routing_repository
_postgres_routing_policy_settings_repository = _runtime.postgres_routing_policy_settings_repository
_gmail_service = _runtime.gmail_service
_naver_service = _runtime.naver_service
_hiworks_service = _runtime.hiworks_service
_attachment_parser_dispatcher = _runtime.attachment_parser_dispatcher
_local_llm_gateway = _runtime.local_llm_gateway
_production_case_indexer = _runtime.production_case_indexer
_mail_search_embedding_cache = _runtime.mail_search_embedding_cache
_mail_chat_service = _runtime.mail_chat_service
_attachment_understanding_analyzer = _runtime.attachment_understanding_analyzer
_postgres_attachment_analysis_repository = _runtime.postgres_attachment_analysis_repository
_attachment_reanalysis_lock = _runtime.attachment_reanalysis_lock


app, templates = build_web_application(
    static_dir=STATIC_DIR,
    templates_dir=TEMPLATES_DIR,
    routers=[mail_decision_router],
)


def current_asset_version() -> str:
    paths = [APP_DIR / "server.py"]
    paths.extend(STATIC_DIR.rglob("*.css"))
    paths.extend(TEMPLATES_DIR.rglob("*.html"))
    existing_paths = [path for path in paths if path.exists()]
    if not existing_paths:
        return "0"
    return str(max(path.stat().st_mtime_ns for path in existing_paths))


def auth_cookie_value(username: str, now: float | None = None) -> str:
    return encode_auth_cookie(
        username,
        secret=AUTH_SECRET,
        session_seconds=AUTH_SESSION_SECONDS,
        now=now,
    )


def auth_cookie_username(cookie_value: str | None, now: float | None = None) -> str | None:
    return decode_auth_cookie(cookie_value, secret=AUTH_SECRET, now=now)


def is_authenticated(request: Request) -> bool:
    if not AUTH_ENABLED:
        return True
    return auth_cookie_username(request.cookies.get(AUTH_COOKIE_NAME)) is not None


def authenticate_login(username: str, password: str) -> dict[str, Any] | None:
    user = _postgres_user_repository.authenticate(username, password)
    if user:
        return {
            "username": str(user.get("username") or user.get("email") or username),
            "user_id": str(user.get("id") or ""),
            "name": str(user.get("name") or username),
            "role": str(user.get("role") or "employee"),
            "email": str(user.get("email") or ""),
        }
    if hmac.compare_digest(username, AUTH_USERNAME) and hmac.compare_digest(password, AUTH_PASSWORD):
        return {
            "username": AUTH_USERNAME,
            "user_id": "",
            "name": AUTH_USERNAME,
            "role": "admin",
            "email": "",
        }
    return None


def login_response(request: Request, error: str = "", next_path: str = "/") -> HTMLResponse:
    safe_next_path = next_path if next_path.startswith("/") and not next_path.startswith("//") else "/"
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "asset_version": current_asset_version(),
            "error": error,
            "next_path": safe_next_path,
        },
        status_code=401 if error else 200,
    )


def auth_required_response(request: Request) -> Response:
    login_path = f"/login?next={quote(request.url.path)}"
    if request.headers.get("HX-Request"):
        return Response(status_code=401, headers={"HX-Redirect": login_path})
    return RedirectResponse(login_path, status_code=303)


def current_authenticated_user(request: Request | None) -> dict[str, str]:
    username = current_request_username(request)
    user = _postgres_user_repository.user_by_login(username)
    if user:
        return {
            "username": str(user.get("username") or user.get("email") or username),
            "user_id": str(user.get("id") or ""),
            "name": str(user.get("name") or username),
            "role": str(user.get("role") or "employee"),
            "email": str(user.get("email") or ""),
        }
    role = "admin" if username == AUTH_USERNAME else "employee"
    return {"username": username, "user_id": "", "name": username, "role": role, "email": ""}


def current_authenticated_user_id(request: Request | None) -> UUID | None:
    user_id = current_authenticated_user(request).get("user_id") or ""
    try:
        return UUID(user_id) if user_id else None
    except ValueError:
        return None


def _mark_mail_read_for_current_user(request: Request, email: dict[str, object]) -> dict[str, Any] | None:
    try:
        actor_user_id = current_authenticated_user_id(request)
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("mail read state user lookup failed: %s", exc)
        return None
    if actor_user_id is None or not database_url():
        return None
    try:
        email_message_id = UUID(str(email.get("email_uid") or ""))
    except ValueError:
        return None
    result: dict[str, Any] = {}
    try:
        read_result = _postgres_mail_read_repository.mark_read(
            email_message_id=email_message_id,
            user_id=actor_user_id,
        )
        result.update(read_result or {})
    except Exception as exc:
        logger.warning("mail read state update failed: %s: %s", type(exc).__name__, exc)
    try:
        before_status = str(email.get("work_status") or "")
        work_item = _postgres_work_tracking_repository.acknowledge_if_assignee(
            email_message_id=email_message_id,
            actor_user_id=actor_user_id,
        )
        after_status = str((work_item or {}).get("status") or "")
        if after_status and after_status != before_status:
            result["work_status_changed"] = True
            result["work_status"] = after_status
    except Exception as exc:
        logger.warning("work acknowledgement update failed: %s: %s", type(exc).__name__, exc)
    return result or None


def _gmail_thread_url(provider_thread_id: str) -> str:
    thread_id = provider_thread_id.strip()
    if not thread_id:
        return ""
    return f"https://mail.google.com/mail/u/0/#inbox/{quote(thread_id)}"


def path_requires_auth(path: str) -> bool:
    if not AUTH_ENABLED:
        return False
    if path in {"/login", "/logout", "/auth/gmail/callback", "/api/health", "/api/client-version"}:
        return False
    return path == "/" or path.startswith("/ui/") or path.startswith("/api/")


def default_demo_mode() -> bool:
    value = os.getenv("CORAMAIL_DEMO_MODE", os.getenv("CORAMAIL_DEMO_ONLY", "true"))
    return value.strip().casefold() not in {"0", "false", "off", "no"}


def request_demo_mode(request: Request) -> bool:
    cookie_value = str(request.cookies.get(DISPLAY_MODE_COOKIE_NAME) or "").strip().casefold()
    if cookie_value in {"demo", "1", "true", "on", "yes"}:
        return True
    if cookie_value in {"gmail", "real", "actual", "0", "false", "off", "no"}:
        return False
    return default_demo_mode()


def demo_mode_enabled() -> bool:
    value = _display_demo_mode.get()
    return default_demo_mode() if value is None else bool(value)


def demo_service() -> DemoMailService:
    return DemoMailService(DemoMailRepository(DEMO_DIR))


def postgres_demo_source_enabled() -> bool:
    value = os.getenv("CORAMAIL_DEMO_SOURCE", "").strip().casefold()
    if value:
        return value == "postgres"
    return bool(database_url())


def postgres_jobs_enabled() -> bool:
    return bool(database_url())


def active_mail_provider() -> str:
    return mail_provider()


def active_provider_label() -> str:
    return {
        "gmail": "Gmail",
        "naver": "Naver",
        "hiworks": "하이웍스",
    }.get(active_mail_provider(), "Gmail")


def active_provider_service() -> GmailMailboxService | NaverMailboxService | HiworksMailboxService:
    provider = active_mail_provider()
    if provider == "naver":
        return _naver_service
    if provider == "hiworks":
        return _hiworks_service
    return _gmail_service


def active_mail_status() -> dict[str, Any]:
    return active_provider_service().status()


def active_mail_public_status() -> dict[str, Any]:
    provider = active_mail_provider()
    if provider == "gmail":
        return _gmail_account_repository.public_status()
    return active_provider_service().public_status()


def active_mail_settings_panel_url() -> str:
    provider = active_mail_provider()
    if provider == "naver":
        return "/ui/settings/naver-sync"
    if provider == "hiworks":
        return "/ui/settings/hiworks-sync"
    return "/ui/settings/gmail-sync"


def mail_service() -> DemoMailService | GmailMailboxService | NaverMailboxService | HiworksMailboxService | PostgresMailboxService:
    if demo_mode_enabled():
        if postgres_demo_source_enabled() and database_url():
            return _postgres_service
        return demo_service()
    return active_provider_service()


def mail_search_service() -> MailSearchService:
    return MailSearchService(
        mail_service(),
        _local_llm_gateway,
        embedding_cache=_mail_search_embedding_cache,
        answer_model=chat_text_model(),
    )


def _mail_store_fallback_error(exc: Exception) -> bool:
    return type(exc).__name__ in {
        "OperationalError",
        "ConnectionError",
        "ConnectionRefusedError",
        "TimeoutError",
    }


def mail_rows(
    q: str = "",
    category: str = "",
    limit: int | None = None,
) -> list[dict[str, Any]]:
    try:
        return attach_sender_contacts(mail_service().list_emails(q=q, category=category, limit=limit))
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("mail store unavailable; falling back to demo fixtures: %s", exc)
        return attach_sender_contacts(demo_service().list_emails(q=q, category=category, limit=limit))


def rows_with_current_user_read_state(
    request: Request | None,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    try:
        actor_user_id = current_authenticated_user_id(request)
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("mail read state user lookup unavailable: %s", exc)
        return rows
    if actor_user_id is None or not database_url() or not rows:
        return rows
    email_ids: list[UUID] = []
    for row in rows:
        try:
            email_ids.append(UUID(str(row.get("email_uid") or "")))
        except ValueError:
            continue
    if not email_ids:
        return rows
    try:
        read_states = _postgres_mail_read_repository.read_states_for_user(
            email_message_ids=email_ids,
            user_id=actor_user_id,
        )
    except Exception as exc:
        logger.warning("mail read state lookup failed: %s: %s", type(exc).__name__, exc)
        return rows
    if not read_states:
        return rows
    return [
        dict(row) | {"current_user_read_at": read_states.get(str(row.get("email_uid") or ""), "")}
        for row in rows
    ]


def filter_dashboard_mail_rows(rows: list[dict[str, Any]], dashboard_mail_filter: str = "") -> list[dict[str, Any]]:
    active_filters = {item for item in dashboard_mail_filter.split(",") if item}
    if not active_filters:
        return rows
    reference_date = _dashboard_reference_date(rows)
    attention_filters = {
        item.removeprefix("attention:")
        for item in active_filters
        if item.startswith("attention:")
    }
    filtered_rows = rows
    if "today" in active_filters:
        filtered_rows = _dashboard_rows_on_day(filtered_rows, reference_date)
    if "urgent" in active_filters:
        filtered_rows = [row for row in filtered_rows if _is_priority_high_row(row)]
    if attention_filters:
        filtered_rows = [row for row in filtered_rows if _attention_quadrant_for_row(row) in attention_filters]
    return filtered_rows


def _service_email_detail_by_ref(service: Any, email_ref: str) -> dict[str, object] | None:
    if hasattr(service, "email_detail_by_uid"):
        email = service.email_detail_by_uid(email_ref)
        if email is not None:
            return email
    if email_ref.isdecimal():
        return service.email_detail(int(email_ref))
    return None


@app.middleware("http")
async def set_display_mode_context(request: Request, call_next) -> Response:
    token = _display_demo_mode.set(request_demo_mode(request))
    try:
        return await call_next(request)
    finally:
        _display_demo_mode.reset(token)


@app.middleware("http")
async def require_ui_auth(request: Request, call_next) -> Response:
    if path_requires_auth(request.url.path) and not is_authenticated(request):
        logger.info("auth_required path=%s", request.url.path)
        return auth_required_response(request)
    return await call_next(request)


def format_mail_table_time(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return value or "-"
    parsed = _display_datetime(parsed)
    if parsed.date() == datetime.now(DISPLAY_TIMEZONE).date():
        meridiem = "오전" if parsed.hour < 12 else "오후"
        hour = parsed.hour % 12 or 12
        return f"{meridiem} {hour}:{parsed.minute:02d}"
    return f"{parsed.month}월 {parsed.day}일"


def format_mail_detail_time(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return value or "-"
    parsed = _display_datetime(parsed)
    meridiem = "오전" if parsed.hour < 12 else "오후"
    hour = parsed.hour % 12 or 12
    return f"{parsed.year}. {parsed.month}. {parsed.day}. {meridiem} {hour}:{parsed.minute:02d}"


def format_mail_datetime(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return value or "-"
    parsed = _display_datetime(parsed)
    weekday = KOREAN_WEEKDAYS[parsed.weekday()]
    meridiem = "오전" if parsed.hour < 12 else "오후"
    hour = parsed.hour % 12 or 12
    return f"{parsed.year}년 {parsed.month}월 {parsed.day}일 ({weekday}) {meridiem} {hour}:{parsed.minute:02d}"


def format_mail_date_key(value: str) -> str:
    parsed = _parse_datetime(value)
    if parsed is None:
        return ""
    return _display_datetime(parsed).date().isoformat()


def category_class(label: str) -> str:
    mapping = {
        "문의": "category-chip--inquiry",
        "발주": "category-chip--order",
        "서비스": "category-chip--service",
        "기술": "category-chip--technical",
        "기타": "category-chip--general",
        "견적 수신": "blue",
        "사양 확인": "violet",
        "사양 재확인": "red",
        "미분류": "category-chip--unclassified",
    }
    return mapping.get(label, "category-chip--default")


def category_filter_visual(label: str) -> dict[str, str]:
    visuals = {
        "__all__": {"bg": "#F3F5F7", "color": "#000000", "border": "#00000040", "dot": "#000000"},
        "문의": {"bg": "#E4F8F1", "color": "#0F9D6F", "border": "#0F9D6F40", "dot": "#0F9D6F"},
        "발주": {"bg": "#EEEDFF", "color": "#5B5CE2", "border": "#5B5CE240", "dot": "#5B5CE2"},
        "서비스": {"bg": "#FFF0EA", "color": "#F26A3D", "border": "#F26A3D40", "dot": "#F26A3D"},
        "기술": {"bg": "#EAF3FE", "color": "#2E86DE", "border": "#2E86DE40", "dot": "#2E86DE"},
        "기타": {"bg": "#F3F5F7", "color": "#667085", "border": "#66708540", "dot": "#667085"},
        "견적 수신": {"bg": "#E4F8F1", "color": "#0F9D6F", "border": "#0F9D6F40", "dot": "#0F9D6F"},
        "사양 확인": {"bg": "#EAF3FE", "color": "#2E86DE", "border": "#2E86DE40", "dot": "#2E86DE"},
        "사양 재확인": {"bg": "#FFF0EA", "color": "#F26A3D", "border": "#F26A3D40", "dot": "#F26A3D"},
        "미분류": {"bg": "#FFF4DF", "color": "#C9831A", "border": "#C9831A40", "dot": "#C9831A"},
    }
    return visuals.get(label, visuals["미분류"])


def category_chart_palette(categories: list[str]) -> list[str]:
    fallback = ["#5B5CE2", "#0F9D6F", "#F26A3D", "#2E86DE", "#667085", "#C9831A"]
    color_by_category = {
        "문의": "#0F9D6F",
        "발주": "#5B5CE2",
        "서비스": "#F26A3D",
        "기술": "#2E86DE",
        "기타": "#667085",
        "견적 수신": "#0F9D6F",
        "사양 확인": "#2E86DE",
        "사양 재확인": "#F26A3D",
        "미분류": "#C9831A",
    }
    return [color_by_category.get(category, fallback[index % len(fallback)]) for index, category in enumerate(categories)]


def mail_category(classification: dict[str, object] | None) -> str:
    if not classification:
        return "미분류"
    return str(classification.get("business_label") or classification.get("mail_category") or "미분류")


ROUTING_REVIEW_REQUIRED_LABEL = "검토 필요"
LEGACY_ROUTING_REVIEW_REQUIRED_LABEL = "담당자 검토 필요"
UNASSIGNED_ROUTING_LABEL = "미할당"
UNROUTED_LABELS = {"", UNASSIGNED_ROUTING_LABEL, ROUTING_REVIEW_REQUIRED_LABEL, LEGACY_ROUTING_REVIEW_REQUIRED_LABEL}


def route_label(labels: list[object] | None) -> str:
    values = [str(label) for label in labels or [] if str(label).strip()]
    return ", ".join(values) if values else UNASSIGNED_ROUTING_LABEL


def receiver_chip_class(routing_display: object, category_label: object = "") -> str:
    display = str(routing_display or "").strip()
    if display == UNASSIGNED_ROUTING_LABEL or not display:
        return "category-chip--unclassified"
    return category_class(str(category_label or "미분류"))


def receiver_display_text(value: object) -> str:
    display = str(value or "").strip()
    if display in {ROUTING_REVIEW_REQUIRED_LABEL, LEGACY_ROUTING_REVIEW_REQUIRED_LABEL}:
        return UNASSIGNED_ROUTING_LABEL
    return display or UNASSIGNED_ROUTING_LABEL


def routing_label_text(value: object) -> str:
    return str(value or "")


def json_pretty(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def metric_fraction(metric: object) -> str:
    if not isinstance(metric, dict):
        return "0 / 0 (0.0%)"
    numerator = float(metric.get("numerator") or 0)
    denominator = float(metric.get("denominator") or 0)
    value = float(metric.get("value") or 0)
    return f"{_compact_number(numerator)} / {_compact_number(denominator)} ({value * 100:.1f}%)"


def _compact_number(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:.4f}".rstrip("0").rstrip(".")


def display_sender_name(email: dict[str, object] | None) -> str:
    if not email:
        return ""
    return str(email.get("sender_name") or email.get("from") or email.get("sender_address") or "")


def display_sender_address(email: dict[str, object] | None) -> str:
    if not email:
        return ""
    return str(email.get("sender_address") or email.get("from") or "")


def _parse_datetime(value: str) -> datetime | None:
    text = str(value or "")
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None


def _display_datetime(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(DISPLAY_TIMEZONE)
    return value.replace(tzinfo=DISPLAY_TIMEZONE)


templates.env.globals.update(
    category_chart_palette=category_chart_palette,
    category_filter_visual=category_filter_visual,
    display_sender_address=display_sender_address,
    display_sender_name=display_sender_name,
    format_mail_table_time=format_mail_table_time,
    format_mail_detail_time=format_mail_detail_time,
    format_mail_datetime=format_mail_datetime,
    format_mail_date_key=format_mail_date_key,
    category_class=category_class,
    mail_category=mail_category,
    route_label=route_label,
    receiver_chip_class=receiver_chip_class,
    receiver_display_text=receiver_display_text,
    routing_label_text=routing_label_text,
    polish_summary=polish_korean_summary_text,
)
templates.env.filters["json_pretty"] = json_pretty
templates.env.filters["metric_fraction"] = metric_fraction
templates.env.filters["attachment_field_label"] = field_display_label

WORK_STATUS_FILTER_OPTIONS = [
    {"value": "assigned", "label": "미확인"},
    {"value": "acknowledged", "label": "확인함"},
    {"value": "in_progress", "label": "진행중"},
    {"value": "responded", "label": "회신함"},
    {"value": "completed", "label": "완료"},
]


def ui_globals(request: Request | None = None) -> dict[str, object]:
    service = mail_service()
    provider = active_mail_provider()
    provider_label = active_provider_label()
    mail_status = active_mail_status()
    auth_user = current_authenticated_user(request)
    username = current_request_username(request)
    return {
        "asset_version": current_asset_version(),
        "demo_mode": demo_mode_enabled(),
        "mail_provider": provider,
        "mail_provider_label": provider_label,
        "mail_settings_panel_url": active_mail_settings_panel_url(),
        "display_mode": "demo" if demo_mode_enabled() else provider,
        "display_mode_label": "Demo" if demo_mode_enabled() else provider_label,
        "display_mode_next_label": provider_label if demo_mode_enabled() else "Demo",
        "gmail_connected_account": DEMO_SCREENSHOT_ACCOUNT_LABEL if demo_mode_enabled() else mail_status["account"],
        "current_user": auth_user["name"] or auth_user["username"],
        "current_user_id": auth_user["user_id"],
        "current_user_role": auth_user["role"],
        "current_user_can_view_all_assignees": user_can_view_all_assignees(username),
        "category_order": service.category_order(),
        "work_status_filter_options": WORK_STATUS_FILTER_OPTIONS,
        "polish_summary": polish_korean_summary_text,
    }


def current_request_username(request: Request | None) -> str:
    if request is None:
        return AUTH_USERNAME
    return auth_cookie_username(request.cookies.get(AUTH_COOKIE_NAME)) or AUTH_USERNAME


def _normalized_identity(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def _assignee_identifier(row: dict[str, object]) -> str:
    return str(
        row.get("assignee_email")
        or row.get("assignee_name")
        or row.get("routing_display")
        or row.get("assignee_user_id")
        or ""
    ).strip()


def _assignee_display_name(row: dict[str, object]) -> str:
    return receiver_display_text(
        row.get("assignee_name")
        or row.get("routing_display")
        or row.get("routing_target_label")
        or UNASSIGNED_ROUTING_LABEL
    )


def _assignee_login_matches(row: dict[str, object], username: str) -> bool:
    login = _normalized_identity(username)
    if not login:
        return False
    return login in {
        _normalized_identity(row.get("assignee_user_id")),
        _normalized_identity(row.get("assignee_email")),
        _normalized_identity(row.get("assignee_name")),
        _normalized_identity(row.get("routing_display")),
    }


def _admin_usernames() -> set[str]:
    return {
        _normalized_identity(value)
        for value in os.getenv("CORAMAIL_ADMIN_USERNAMES", "admin").split(",")
        if value.strip()
    }


def user_can_view_all_assignees(username: str) -> bool:
    return _normalized_identity(username) in _admin_usernames()


def _assignee_access_map() -> dict[str, list[str]]:
    raw = os.getenv("CORAMAIL_ASSIGNEE_ACCESS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("CORAMAIL_ASSIGNEE_ACCESS_JSON is not valid JSON")
        return {}
    if not isinstance(parsed, dict):
        return {}
    access: dict[str, list[str]] = {}
    for username, values in parsed.items():
        if isinstance(values, str):
            items = [values]
        elif isinstance(values, list):
            items = [str(value) for value in values]
        else:
            continue
        access[_normalized_identity(username)] = [_normalized_identity(value) for value in items if str(value).strip()]
    return access


def allowed_assignee_identities(username: str, rows: list[dict[str, object]]) -> set[str] | None:
    if user_can_view_all_assignees(username):
        return None
    login = _normalized_identity(username)
    configured = set(_assignee_access_map().get(login, []))
    if "*" in configured:
        return None
    allowed = {login, *configured}
    for row in rows:
        if _assignee_login_matches(row, username):
            allowed.update(
                {
                    _normalized_identity(row.get("assignee_user_id")),
                    _normalized_identity(row.get("assignee_email")),
                    _normalized_identity(row.get("assignee_name")),
                    _normalized_identity(row.get("routing_display")),
                }
            )
    return {value for value in allowed if value}


def row_allowed_for_assignee_view(row: dict[str, object], allowed: set[str] | None) -> bool:
    if allowed is None:
        return True
    if _is_demo_duplicate_received_row(row):
        return True
    return bool(
        {
            _normalized_identity(row.get("assignee_user_id")),
            _normalized_identity(row.get("assignee_email")),
            _normalized_identity(row.get("assignee_name")),
            _normalized_identity(row.get("routing_display")),
        }.intersection(allowed)
    )


def row_matches_assignee(row: dict[str, object], assignee: str) -> bool:
    requested = _normalized_identity(assignee)
    if not requested:
        return True
    return requested in {
        _normalized_identity(row.get("assignee_user_id")),
        _normalized_identity(row.get("assignee_email")),
        _normalized_identity(row.get("assignee_name")),
        _normalized_identity(row.get("routing_display")),
    }


def visible_work_rows_for_request(
    request: Request | None,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    username = current_request_username(request)
    allowed = allowed_assignee_identities(username, rows)
    visible_rows = [row for row in rows if row_allowed_for_assignee_view(row, allowed)]
    return rows_with_current_user_read_state(request, visible_rows)


def ensure_can_view_work_email(request: Request | None, email: dict[str, object]) -> None:
    username = current_request_username(request)
    if user_can_view_all_assignees(username):
        return
    allowed = allowed_assignee_identities(username, [email])
    if not row_allowed_for_assignee_view(email, allowed):
        raise HTTPException(status_code=403, detail="본인에게 배정된 업무만 확인할 수 있습니다.")


def _is_demo_duplicate_received_row(row: dict[str, object]) -> bool:
    return str(row.get("provider_message_id") or "").startswith("demo-duplicate-latest-")


def status_matches_work_filter(row: dict[str, object], status_filter: str) -> bool:
    status = str(row.get("work_status") or "")
    if not status_filter:
        return True
    if status_filter == "overdue":
        return _is_overdue_work_row(row)
    if status_filter == "completed_today":
        return _is_completed_today_work_row(row)
    return status == status_filter


def is_htmx_request(request: Request) -> bool:
    return request.headers.get("HX-Request", "").strip().casefold() == "true"


def render_view(
    request: Request,
    template_name: str,
    context: dict[str, object],
    *,
    active_view: str,
) -> HTMLResponse:
    if is_htmx_request(request):
        return templates.TemplateResponse(request, template_name, context)
    return templates.TemplateResponse(
        request,
        "shell.html",
        {
            **context,
            "request": request,
            "active_view": active_view,
            "initial_view_template": template_name,
        },
    )


def login_form(request: Request, next: str = "/") -> Response:
    return _auth_root_handlers().login_form(request, next)



async def login_submit(request: Request, next: str = "/") -> Response:
    return await _auth_root_handlers().login_submit(request, next)



def logout_submit() -> RedirectResponse:
    return _auth_root_handlers().logout_submit()



def ui_root(
    request: Request,
    view: str = "dashboard",
    q: str = "",
    category: str = "",
    limit: int = 5,
    email_index: int = 0,
    email_uid: str = "",
    selected_email_uid: str = "",
    assignee: str = "",
    status: str = "",
    session_id: str = "",
    organization: str = "",
) -> HTMLResponse:
    return _auth_root_handlers().root(
        request,
        view=view,
        q=q,
        category=category,
        limit=limit,
        email_index=email_index,
        email_uid=email_uid,
        selected_email_uid=selected_email_uid,
        assignee=assignee,
        status=status,
        session_id=session_id,
        organization=organization,
    )



def ui_my_work_email_drawer(request: Request, email_ref: str) -> HTMLResponse:
    return render_my_work_email_drawer(
        request,
        email_ref,
        email_detail=_email_detail_by_ref,
        ensure_can_view=ensure_can_view_work_email,
        mark_mail_read=_mark_mail_read_for_current_user,
        ui_globals=ui_globals,
        related_emails=related_emails,
        templates=templates,
    )


def ui_work_reply_initiate(request: Request, email_ref: str) -> Response:
    return initiate_work_reply(
        request,
        email_ref,
        email_detail=_email_detail_by_ref,
        authenticated_user_id=current_authenticated_user_id,
        work_tracking_repository=_postgres_work_tracking_repository,
        gmail_thread_url=_gmail_thread_url,
    )


async def ui_work_in_progress_toggle(request: Request, email_ref: str) -> Response:
    form = _urlencoded_form(await request.body())
    active = str(form.get("active") or "").strip().casefold() in {"1", "true", "on", "yes"}
    return toggle_work_in_progress(
        request,
        email_ref,
        active=active,
        email_detail=_email_detail_by_ref,
        authenticated_user_id=current_authenticated_user_id,
        work_tracking_repository=_postgres_work_tracking_repository,
    )


def ui_work_complete(request: Request, email_ref: str) -> Response:
    return complete_work_item(
        request,
        email_ref,
        email_detail=_email_detail_by_ref,
        authenticated_user_id=current_authenticated_user_id,
        work_tracking_repository=_postgres_work_tracking_repository,
    )


def ui_create_mail_decision_run(request: Request, email_ref: str) -> HTMLResponse:
    return create_mail_decision_run(
        request,
        email_ref,
        email_detail=_email_detail_by_ref,
        runtime_client=mail_decision_runtime_client,
        render_panel=render_mail_decision_panel,
        runtime_user_message=mail_decision_runtime_user_message,
        logger=logger,
    )



def ui_latest_mail_decision_run(request: Request, email_ref: str) -> HTMLResponse:
    return latest_mail_decision_run(
        request,
        email_ref,
        email_detail=_email_detail_by_ref,
        runtime_client=mail_decision_runtime_client,
        render_panel=render_mail_decision_panel,
        demo_mode_enabled=demo_mode_enabled,
        database_url=database_url,
        demo_service=demo_service,
        logger=logger,
    )



def ui_mail_decision_run(request: Request, run_id: str) -> HTMLResponse:
    return mail_decision_run(
        request,
        run_id,
        runtime_client=mail_decision_runtime_client,
        render_panel=render_mail_decision_panel,
        runtime_user_message=mail_decision_runtime_user_message,
        logger=logger,
    )



def ui_mail_decision_steps(request: Request, run_id: str) -> HTMLResponse:
    return mail_decision_steps(
        request,
        run_id,
        runtime_client=mail_decision_runtime_client,
        runtime_user_message=mail_decision_runtime_user_message,
        steps_view=mail_decision_steps_view,
        templates=templates,
        logger=logger,
    )



def ui_evaluation(request: Request, report: str = "clean-v2") -> HTMLResponse:
    return render_evaluation(
        request,
        report,
        render_view=render_view,
        ui_globals=ui_globals,
        dashboard_view=evaluation_dashboard_view,
    )



def ui_evaluation_case(request: Request, email_message_id: str, report: str = "clean-v2") -> HTMLResponse:
    return render_evaluation_case(
        request,
        email_message_id,
        report,
        render_view=render_view,
        ui_globals=ui_globals,
        case_view=evaluation_case_view,
    )



def ui_evaluation_case_trace(request: Request, email_message_id: str, report: str = "clean-v2") -> HTMLResponse:
    return render_evaluation_trace(
        request,
        email_message_id,
        report,
        ui_globals=ui_globals,
        case_view=evaluation_case_view,
        templates=templates,
    )



def ui_search(request: Request, q: str = "", limit: int = 5) -> HTMLResponse:
    return render_search(
        request,
        q,
        limit,
        render_view=render_view,
        search_context=search_context,
    )



def ui_search_results(request: Request, q: str = "", limit: int = 5) -> Response:
    return render_search_results(
        request,
        q,
        limit,
        is_htmx_request=is_htmx_request,
        request_demo_mode=request_demo_mode,
        normalize_search_query=normalize_search_query,
        mail_search_service=mail_search_service,
        ui_globals=ui_globals,
        templates=templates,
        logger=logger,
    )



def ui_chats(request: Request, q: str = "", limit: int = 5, session_id: str = "") -> HTMLResponse:
    return render_chats(
        request,
        q,
        limit,
        session_id,
        render_view=render_view,
        chats_context=chats_context,
    )



def ui_chats_results(
    request: Request,
    q: str = "",
    limit: int = 5,
    session_id: str = "",
    chat_history: str = "",
) -> Response:
    return render_chats_results(
        request,
        q,
        limit,
        session_id,
        _parse_chat_history(chat_history),
        is_htmx_request=is_htmx_request,
        request_demo_mode=request_demo_mode,
        normalize_search_query=normalize_search_query,
        mail_chat_service=_mail_chat_service,
        mail_search_service=mail_search_service,
        ui_globals=ui_globals,
        templates=templates,
    )


def ui_chat_email_drawer(request: Request, email_ref: str) -> HTMLResponse:
    return render_chat_email_drawer(
        request,
        email_ref,
        email_detail=_email_detail_by_ref,
        ensure_can_view=ensure_can_view_work_email,
        mark_mail_read=_mark_mail_read_for_current_user,
        ui_globals=ui_globals,
        related_emails=related_emails,
        templates=templates,
    )


def _parse_chat_history(chat_history: str) -> list[dict[str, object]]:
    raw = str(chat_history or "").strip()
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def ui_address_book(request: Request, q: str = "", organization: str = "") -> HTMLResponse:
    return render_address_book(
        request,
        q=q,
        organization=organization,
        address_book_context=address_book_context,
        render_view=render_view,
    )



def _mail_action_handlers() -> MailActionHandlers:
    return MailActionHandlers(
        run_analysis_job=_run_registered_email_analysis_job_by_ref,
        reanalyze_attachments=_reanalyze_email_attachments_guarded,
        request_demo_mode=request_demo_mode,
        gmail_service=_gmail_service,
        render_inbox=render_inbox,
        mail_rows=mail_rows,
        status_matches=status_matches_work_filter,
        resolve_selected_index=_resolve_selected_index,
        inbox_context=inbox_context,
        render_view=render_view,
        email_detail=_email_detail_by_ref,
        start_demo_manual_route_delivery=_start_demo_manual_route_delivery,
        dashboard_context=dashboard_context,
        templates=templates,
        demo_service=demo_service,
        logger=logger,
    )


def _auth_root_handlers() -> AuthRootHandlers:
    return AuthRootHandlers(
        is_authenticated=is_authenticated,
        login_response=login_response,
        parse_form=_urlencoded_form,
        authenticate_login=authenticate_login,
        auth_cookie_value=auth_cookie_value,
        auth_cookie_name=AUTH_COOKIE_NAME,
        auth_session_seconds=AUTH_SESSION_SECONDS,
        auth_cookie_secure=AUTH_COOKIE_SECURE,
        mail_rows=mail_rows,
        status_matches=status_matches_work_filter,
        resolve_selected_index=_resolve_selected_index,
        inbox_context=inbox_context,
        document_types_context=document_types_context,
        address_book_context=address_book_context,
        assignee_work_context=assignee_work_context,
        ops_console_context=ops_console_context,
        search_context=search_context,
        chats_context=chats_context,
        settings_context=settings_context,
        dashboard_context=dashboard_context,
        templates=templates,
    )


def ui_settings(request: Request) -> HTMLResponse:
    return _settings_handlers().settings(request)



def ui_gmail_sync_settings(request: Request) -> HTMLResponse:
    return _settings_handlers().gmail_sync_settings(request)


def ui_naver_sync_settings(request: Request) -> HTMLResponse:
    return render_mail_sync_settings(request)


def ui_hiworks_sync_settings(request: Request) -> HTMLResponse:
    return render_mail_sync_settings(request)


async def ui_save_gmail_client_config(request: Request) -> HTMLResponse:
    return await _settings_handlers().save_gmail_client_config(request)



async def ui_save_gmail_tokens(request: Request) -> HTMLResponse:
    return await _settings_handlers().save_gmail_tokens(request)



def ui_gmail_connect(request: Request) -> RedirectResponse:
    return _settings_handlers().gmail_connect(request)



def gmail_oauth_callback(request: Request, state: str = "", error: str = "") -> RedirectResponse:
    return _settings_handlers().gmail_oauth_callback(request, state=state, error=error)



def ui_gmail_disconnect(request: Request) -> HTMLResponse:
    return _settings_handlers().gmail_disconnect(request)



def ui_gmail_settings_sync(request: Request) -> HTMLResponse:
    return _settings_handlers().gmail_sync(request)


def ui_naver_settings_sync(request: Request) -> HTMLResponse:
    result = _naver_service.sync()
    if result.get("status") == "ok":
        return render_mail_sync_settings(
            request,
            message=(
                f"Naver INBOX {result.get('message_count', 0)}건을 확인했고 "
                f"{result.get('persisted_message_count', 0)}건을 Inbox에 저장했습니다."
            ),
        )
    return render_mail_sync_settings(request, error=str(result.get("message") or "Naver Mail 연동 실패"))


def ui_hiworks_settings_sync(request: Request) -> HTMLResponse:
    result = _hiworks_service.sync()
    if result.get("status") == "ok":
        return render_mail_sync_settings(
            request,
            message=(
                f"하이웍스 받은편지함 {result.get('message_count', 0)}건을 확인했고 "
                f"{result.get('persisted_message_count', 0)}건을 Inbox에 저장했습니다."
            ),
        )
    return render_mail_sync_settings(request, error=str(result.get("message") or "하이웍스 Mail 연동 실패"))


def ui_gmail_settings_sync_outbound(request: Request) -> HTMLResponse:
    return _settings_handlers().gmail_sync_outbound(request)



def ui_receive_latest_duplicate_demo_mail(request: Request) -> RedirectResponse:
    return _settings_handlers().receive_latest_duplicate_demo_mail(request)



def ui_routing_table(request: Request) -> HTMLResponse:
    return _settings_handlers().routing_table(request)



def ui_routing_summary(request: Request) -> HTMLResponse:
    return _settings_handlers().routing_summary(request)



def ui_auto_assignment_policy(request: Request) -> HTMLResponse:
    return _settings_handlers().auto_assignment_policy(request)



def ui_display_mode_toggle(request: Request) -> Response:
    return _settings_handlers().display_mode_toggle(request)



def ui_auto_sync_run() -> Response:
    return _settings_handlers().auto_sync_run()



def auto_sync_status() -> dict[str, object]:
    return _settings_handlers().auto_sync_status()



def ui_email_classification_regenerate(email_ref: str) -> Response:
    return _mail_action_handlers().classification_regenerate(email_ref)



def ui_email_summary_regenerate(email_ref: str) -> Response:
    return _mail_action_handlers().summary_regenerate(email_ref)



def ui_email_attachments_reanalyze(email_ref: str) -> Response:
    return _mail_action_handlers().attachments_reanalyze(email_ref)



def ui_trash_email(request: Request, email_ref: str) -> HTMLResponse:
    return _mail_action_handlers().trash_email(request, email_ref)



def ui_route_email_manual(request: Request, email_ref: str) -> HTMLResponse:
    return _mail_action_handlers().route_email_manual(request, email_ref)



def _start_demo_manual_route_delivery(email_ref: str) -> dict[str, Any]:
    if not database_url():
        raise RuntimeError("수동 라우팅은 PostgreSQL 메일함에서만 사용할 수 있습니다.")
    email = _email_detail_by_ref(email_ref)
    if email is None:
        raise RuntimeError("이메일을 찾을 수 없습니다.")
    email_message_id = UUID(str(email.get("email_uid") or ""))
    assignment = _postgres_routing_repository.current_assignment(email_message_id)
    if not assignment or not assignment.get("assignee_user_id") or not assignment.get("assignee_email"):
        raise RuntimeError("담당자 이메일이 확정되지 않아 수동 라우팅을 시작할 수 없습니다.")
    latest = _postgres_routing_repository.latest_manual_forward_notification(email_message_id)
    if str(latest.get("status") or "") == "pending":
        return {"status": "pending", "notification_id": str(latest.get("id") or "")}

    assignee_user_id = UUID(str(assignment["assignee_user_id"]))
    notification_id = _postgres_routing_repository.create_manual_forward_notification(
        email_message_id=email_message_id,
        recipient_user_id=assignee_user_id,
        title=_gmail_service._manual_forward_subject(email),
        body=_gmail_service._manual_forward_body(email)[:10000],
        idempotency_key=f"demo-manual-route:{email_message_id}:{int(time.time() * 1000000)}",
    )
    _postgres_routing_repository.mark_manual_forward_sent(
        notification_id=notification_id,
        email_message_id=email_message_id,
        assignee_user_id=assignee_user_id,
        provider_message_id=f"demo-manual-route:{notification_id}",
    )
    return {"status": "sent", "notification_id": str(notification_id)}


async def ui_manual_assign_review_email(request: Request, email_ref: str) -> HTMLResponse:
    return await manual_assign_review_email(
        request,
        email_ref,
        parse_form=_urlencoded_form,
        latest_run_for_panel=_latest_mail_decision_run_for_panel,
        manual_assign=_manual_assign_review_email,
        auth_cookie_username=auth_cookie_username,
        auth_cookie_name=AUTH_COOKIE_NAME,
        auth_username=AUTH_USERNAME,
        render_panel=render_mail_decision_panel,
        email_detail=_email_detail_by_ref,
        logger=logger,
    )



def ui_confirm_top_review_candidate(request: Request, email_ref: str) -> Response:
    return confirm_top_review_candidate(
        request,
        email_ref,
        manual_assign_top=_manual_assign_top_review_candidate_email,
        auth_cookie_username=auth_cookie_username,
        auth_cookie_name=AUTH_COOKIE_NAME,
        auth_username=AUTH_USERNAME,
        email_detail=_email_detail_by_ref,
    )



async def ui_settings_create_assignee(request: Request) -> HTMLResponse:
    return await _settings_handlers().create_assignee(request)



async def ui_settings_update_assignee(request: Request, assignee_id: UUID) -> Response:
    return await _settings_handlers().update_assignee(request, assignee_id)



async def ui_settings_toggle_assignee(request: Request, assignee_id: UUID) -> HTMLResponse:
    return await _settings_handlers().toggle_assignee(request, assignee_id)



async def ui_settings_deactivate_assignee(request: Request, assignee_id: UUID) -> HTMLResponse:
    return await _settings_handlers().deactivate_assignee(request, assignee_id)



async def ui_settings_delete_assignee(request: Request, assignee_id: UUID) -> HTMLResponse:
    return await _settings_handlers().delete_assignee(request, assignee_id)



async def ui_settings_routing_reorder(request: Request) -> HTMLResponse:
    return await _settings_handlers().routing_reorder(request)



async def ui_settings_auto_assignment_policy(request: Request) -> HTMLResponse:
    return await _settings_handlers().save_auto_assignment_policy(request)



def ui_state(
    request: Request | None = None,
    view: str = "",
    q: str = "",
    category: str = "",
    status: str = "",
    selected_email_index: int | None = None,
    selected_email_uid: str = "",
) -> dict[str, object]:
    rows = mail_rows(q=q, category=category)
    if view in {"inbox", "dashboard"}:
        rows = [row for row in rows if status_matches_work_filter(row, status.strip())]
    if view == "inbox":
        rows = visible_work_rows_for_request(request, rows)
    resolved_selected_index = _resolve_selected_index(
        rows,
        selected_email_index if selected_email_index is not None else 0,
        selected_email_uid,
    )
    resolved_selected_uid = (
        str(rows[resolved_selected_index].get("email_uid") or "") if resolved_selected_index is not None else ""
    )
    service_version = _gmail_service.version() if not demo_mode_enabled() else "demo"
    rows_digest = _ui_state_digest("mail_rows", _mail_rows_state_payload(rows))
    digest = f"{current_asset_version()}:{service_version}:{rows_digest}"
    detail_digest = _selected_email_detail_digest(
        rows,
        selected_email_index=resolved_selected_index,
        selected_email_uid=resolved_selected_uid,
    )
    monitoring_rows_digest = digest
    document_sections_digest = digest
    if view == "monitoring":
        monitoring_rows = ops_console_context(request, q=q, category=category, status=status).get("ops_rows", [])
        monitoring_rows_digest = (
            f"{current_asset_version()}:{service_version}:monitoring:"
            f"{_ui_state_digest('monitoring_rows', monitoring_rows)}"
        )
    if view == "documents":
        try:
            sections = mail_service().document_type_sections(q=q)
        except Exception as exc:
            if not _mail_store_fallback_error(exc):
                raise
            logger.warning("mail store unavailable; falling back to demo document ui-state: %s", exc)
            sections = demo_service().document_type_sections(q=q)
        document_sections_digest = (
            f"{digest}:documents:"
            f"{len(sections)}:"
            f"{sum(int(section.get('email_count') or 0) for section in sections)}:"
            f"{sum(int(section.get('attachment_count') or 0) for section in sections)}"
        )
    return {
        "asset_version": current_asset_version(),
        "selected_email_index": resolved_selected_index,
        "selected_email_uid": resolved_selected_uid,
        "versions": {
            "mail_rows": digest,
            "detail": detail_digest,
            "email_detail": detail_digest,
            "dashboard": digest,
            "routing_table": digest,
            "monitoring_rows": monitoring_rows_digest,
            "document_sections": document_sections_digest,
        },
    }


def _selected_email_detail_digest(
    rows: list[dict[str, Any]],
    *,
    selected_email_index: int | None,
    selected_email_uid: str,
) -> str:
    selected_uid = selected_email_uid.strip()
    if not selected_uid and selected_email_index is not None and 0 <= selected_email_index < len(rows):
        selected_uid = str(rows[selected_email_index].get("email_uid") or "")
    if not selected_uid:
        return _ui_state_digest("email_detail", {"selected": None})
    detail = _email_detail_by_ref(selected_uid) or {}
    return _ui_state_digest("email_detail", _email_detail_state_payload(detail))


def _mail_rows_state_payload(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    keys = [
        "email_uid",
        "processing_status",
        "category",
        "classification",
        "summary",
        "routing_display",
        "routing_status",
        "routing_forwarded_at",
        "work_status",
        "mail_decision_status",
        "mail_decision_started_at",
        "mail_decision_completed_at",
    ]
    return [{key: _ui_state_value(row.get(key)) for key in keys} for row in rows]


def _email_detail_state_payload(email: dict[str, object]) -> dict[str, object]:
    keys = [
        "email_uid",
        "processing_status",
        "category",
        "classification",
        "summary",
        "routing_display",
        "routing_status",
        "routing_forwarded_at",
        "work_status",
        "mail_decision_status",
        "mail_decision_started_at",
        "mail_decision_completed_at",
        "assignee_name",
        "assignee_email",
    ]
    return {key: _ui_state_value(email.get(key)) for key in keys}


def _ui_state_digest(label: str, payload: object) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return f"{label}:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]}"


def _ui_state_value(value: object) -> object:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def demo_email_attachment(email_index: int, attachment_index: int, download: bool = False) -> FileResponse:
    return _mail_action_handlers().demo_attachment(email_index, attachment_index, download)



def health() -> dict[str, object]:
    rows = mail_rows()
    readiness = local_ai_readiness()
    provider = active_mail_provider()
    display_mode = "demo" if demo_mode_enabled() else provider
    mail_status = dict(active_mail_status())
    if display_mode == provider and database_url():
        mail_status["session_message_count"] = mail_status.get("message_count", 0)
        mail_status["message_count"] = len(rows)
        mail_status["persisted_message_count"] = len(rows)
        mail_status["displayed_message_count"] = len(rows)
    return {
        "status": "ok" if readiness["ready"] else "degraded",
        "demo_mode": demo_mode_enabled(),
        "display_mode": display_mode,
        "mail_provider": provider,
        "mail_row_count": len(rows),
        "display_mail_count": len(rows),
        "demo_email_count": len(rows),
        provider: mail_status,
        "mail_decision_runtime": {
            "api_mounted": True,
            "runtime_url": os.getenv("CORAMAIL_MAIL_DECISION_RUNTIME_URL", "self").strip() or "self",
        },
        "local_ai": readiness,
    }


app.include_router(
    build_system_router(
        asset_version=current_asset_version,
        ui_state=ui_state,
        health=health,
    )
)


def local_ai_readiness() -> dict[str, object]:
    db = _database_readiness()
    llm = _llm_readiness()
    qdrant = _qdrant_readiness()
    ready = bool(db["ready"] and llm["ready"] and qdrant["ready"])
    return {
        "ready": ready,
        "database": db,
        "llm": llm,
        "qdrant": qdrant,
    }


def _database_readiness() -> dict[str, object]:
    db_url = database_url()
    if not db_url:
        return {"ready": False, "error": "database URL is not configured"}
    try:
        import psycopg

        with psycopg.connect(db_url, connect_timeout=2) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return {"ready": True, "url_configured": True}
    except Exception as exc:
        return {"ready": False, "url_configured": True, "error": str(exc)}


def _llm_readiness() -> dict[str, object]:
    config = LocalLLMConfig(
        base_url=llm_base_url(),
        text_base_url=text_llm_base_url(),
        vision_base_url=vision_llm_base_url(),
        embedding_base_url=embedding_base_url(),
        text_model=text_model(),
        vision_model=vision_model(),
        embedding_model=embedding_model(),
        timeout_seconds=5.0,
        provider=llm_provider(),
        text_provider=text_llm_provider(),
        vision_provider=vision_llm_provider(),
        embedding_provider=embedding_provider(),
        text_max_concurrency=llm_max_concurrency("text"),
        vision_max_concurrency=llm_max_concurrency("vision"),
        embedding_max_concurrency=llm_max_concurrency("embedding"),
        max_output_tokens=llm_max_output_tokens(),
    )
    try:
        payload = LocalLLMGateway(config).healthcheck()
    except LLMGatewayError as exc:
        return {"ready": False, "base_url": config.base_url, "provider": config.provider, "error": str(exc)}
    model_rows = payload.get("data")
    model_id_key = "id"
    if config.provider == "gemini":
        model_rows = payload.get("models")
        model_id_key = "name"
    if not isinstance(model_rows, list):
        model_rows = []
    models = sorted(
        str(row.get(model_id_key) or "").removeprefix("models/") for row in model_rows if isinstance(row, dict)
    )
    required = {
        "text_model": config.text_model,
        "chat_text_model": chat_text_model(),
        "vision_model": config.vision_model,
        "embedding_model": config.embedding_model,
    }
    if config.provider == "gemini":
        required = {key: value.removeprefix("models/") for key, value in required.items()}
    missing = {key: value for key, value in required.items() if value not in models}
    return {
        "ready": not missing,
        "base_url": config.base_url,
        "provider": config.provider,
        "required": required,
        "missing": missing,
        "installed_count": len(models),
    }


def _qdrant_readiness() -> dict[str, object]:
    collection = qdrant_case_collection()
    try:
        with urlopen(f"{qdrant_url().rstrip('/')}/collections/{quote(collection, safe='')}", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"ready": payload.get("status") == "ok", "url": qdrant_url(), "collection": collection}
    except Exception as exc:
        return {"ready": False, "url": qdrant_url(), "collection": collection, "error": str(exc)}


def _resolve_selected_index(rows: list[dict[str, object]], email_index: int, email_uid: str) -> int | None:
    if not rows:
        return None
    if email_uid:
        for index, row in enumerate(rows):
            if row.get("email_uid") == email_uid:
                return index
    if 0 <= email_index < len(rows):
        return email_index
    return 0


def _email_detail_by_ref(email_ref: str) -> dict[str, object] | None:
    resolved = _persistent_email_detail_by_ref(email_ref)
    if resolved is not None:
        return _attach_sender_contact_to_email(resolved[0])
    service = mail_service()
    try:
        return _attach_sender_contact_to_email(_service_email_detail_by_ref(service, email_ref))
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("mail detail store unavailable; falling back to demo fixtures: %s", exc)
        return _attach_sender_contact_to_email(_service_email_detail_by_ref(demo_service(), email_ref))


def _attach_sender_contact_to_email(email: dict[str, object] | None) -> dict[str, object] | None:
    if email is None:
        return None
    if isinstance(email.get("sender_contact"), dict):
        return email
    try:
        rows = mail_rows()
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("sender contact lookup unavailable; falling back to email fields: %s", exc)
        rows = []
    return {**email, "sender_contact": sender_contact_for_email(email, rows)}


def _manual_assign_review_email(
    *,
    email_ref: str,
    assignee_user_id: UUID,
    actor_label: str,
) -> dict[str, Any]:
    if not database_url():
        raise ValueError("PostgreSQL 메일 저장소가 설정되어야 수동 배정할 수 있습니다.")
    email = _email_detail_by_ref(email_ref)
    if email is None:
        raise ValueError("이메일을 찾을 수 없습니다.")
    return _postgres_routing_repository.assign_review_required_mail(
        email_message_id=UUID(str(email["email_uid"])),
        assignee_user_id=assignee_user_id,
        actor_label=actor_label,
    )


def _manual_assign_top_review_candidate_email(
    *,
    email_ref: str,
    actor_label: str,
) -> dict[str, Any]:
    if not database_url():
        raise ValueError("PostgreSQL 메일 저장소가 설정되어야 검토 확정할 수 있습니다.")
    email = _email_detail_by_ref(email_ref)
    if email is None:
        raise ValueError("이메일을 찾을 수 없습니다.")
    email_message_id = UUID(str(email["email_uid"]))
    assignee_user_id = _postgres_routing_repository.top_review_candidate_user_id(email_message_id)
    if assignee_user_id is None:
        raise ValueError("확정할 담당자 후보가 없습니다.")
    return _postgres_routing_repository.assign_review_required_mail(
        email_message_id=email_message_id,
        assignee_user_id=assignee_user_id,
        actor_label=actor_label,
        reason=f"Monitoring review confirmation by {actor_label}.",
    )


def _latest_mail_decision_run_for_panel(request: Request, email_ref: str) -> dict[str, object] | None:
    email = _email_detail_by_ref(email_ref)
    if email is None:
        return None
    if database_url():
        try:
            email_message_id = _postgres_mail_decision_repository.resolve_email_message_id(str(email["email_uid"]))
            if email_message_id is None:
                return None
            state = _postgres_mail_decision_repository.get_latest_run_for_email(email_message_id)
            return None if state is None else state.model_dump(mode="json")
        except Exception as exc:
            logger.warning("Mail Decision local latest lookup for panel failed: %s: %s", type(exc).__name__, exc)
            if not os.getenv("CORAMAIL_MAIL_DECISION_RUNTIME_URL", "").strip():
                return None
    try:
        return mail_decision_runtime_client(request).get_latest_run_for_email(str(email["email_uid"]))
    except MailDecisionRuntimeClientError as exc:
        logger.warning("Mail Decision UI latest lookup for panel failed: %s: %s", type(exc).__name__, exc)
        return None


def _persistent_email_detail_by_ref(email_ref: str) -> tuple[dict[str, object], PostgresMailboxService] | None:
    if _looks_like_uuid(email_ref):
        for persistent_service in (_gmail_postgres_service, _postgres_service):
            try:
                email = persistent_service.email_detail_by_uid(email_ref)
            except Exception as exc:
                if not _mail_store_fallback_error(exc):
                    raise
                logger.warning("persistent mail detail lookup unavailable: %s", exc)
                continue
            if email is not None:
                return email, persistent_service
    return None


def _attachment_path_by_ref(
    email_ref: str,
    attachment_index: int,
    *,
    include_inline: bool = False,
) -> tuple[Path, str, str] | None:
    if _looks_like_uuid(email_ref):
        for persistent_service in (_gmail_postgres_service, _postgres_service):
            resolved = persistent_service.attachment_path_by_uid(
                email_ref,
                attachment_index,
                include_inline=include_inline,
            )
            if resolved is not None:
                return resolved
    service = mail_service()
    if hasattr(service, "attachment_path_by_uid"):
        try:
            resolved = service.attachment_path_by_uid(email_ref, attachment_index, include_inline=include_inline)
        except TypeError:
            resolved = service.attachment_path_by_uid(email_ref, attachment_index)
        if resolved is not None:
            return resolved
    if email_ref.isdecimal() and hasattr(service, "attachment_path"):
        return service.attachment_path(int(email_ref), attachment_index)
    return None


def _looks_like_uuid(value: str) -> bool:
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def _register_email_analysis_job_by_ref(
    email_ref: str, analysis_type: str
) -> tuple[dict[str, object], dict[str, object]] | None:
    if not postgres_jobs_enabled():
        return None
    email = _email_detail_by_ref(email_ref)
    if email is None:
        return None
    job = _postgres_job_repository.create_email_analysis_job(
        str(email["email_uid"]),
        analysis_type,
        requested_by="ui",
    )
    return email, job


def _run_registered_email_analysis_job_by_ref(email_ref: str, analysis_type: str) -> dict[str, Any] | None:
    registered = _register_email_analysis_job_by_ref(email_ref, analysis_type)
    if registered is None:
        return None
    email, job = registered
    worker_result = _postgres_email_analysis_worker.run_one(str(job["id"]))
    processed_jobs = worker_result.get("processed_jobs")
    processed_job = processed_jobs[0] if isinstance(processed_jobs, list) and processed_jobs else {}
    refreshed_job = _postgres_job_repository.job_by_id(str(job["id"])) or job
    return {
        "email": email,
        "job": refreshed_job,
        "worker_result": worker_result,
        "status": processed_job.get("status") or refreshed_job.get("status") or job.get("status"),
    }


def _require_processed_email_analysis_job(email_ref: str, analysis_type: str) -> dict[str, Any]:
    processed = _run_registered_email_analysis_job_by_ref(email_ref, analysis_type)
    if processed is None:
        if _email_detail_by_ref(email_ref) is None:
            raise HTTPException(status_code=404, detail="이메일을 찾을 수 없습니다.")
        raise HTTPException(status_code=503, detail="PostgreSQL 작업 저장소가 설정되지 않았습니다.")
    return processed


def _reanalyze_email_attachments_by_ref(email_ref: str) -> dict[str, Any] | None:
    if not postgres_jobs_enabled():
        return None
    resolved = _persistent_email_detail_by_ref(email_ref)
    if resolved is None:
        return None
    email, persistent_service = resolved
    attachments = persistent_service.repository.attachments_for_message(str(email["email_uid"]))
    results: list[dict[str, object]] = []
    for attachment in attachments:
        result = _attachment_parser_dispatcher.analyze(attachment)
        if result.extracted_text.strip() and (result.document_html.strip() or not result.fields):
            try:
                result = _attachment_understanding_analyzer.enrich(result)
            except LLMGatewayError as exc:
                result.warnings.append("document_understanding_gateway_failed")
                result.error_message = str(exc)
                result.status = AttachmentAnalysisStatus.PARTIAL_SUCCESS
        _postgres_attachment_analysis_repository.save(result)
        results.append(
            {
                "attachment_uid": str(result.attachment_id),
                "filename": result.filename,
                "status": result.status.value,
                "warning_count": len(result.warnings),
                "error_message": result.error_message or "",
            }
        )
    return {
        "status": "ok",
        "email": email,
        "email_uid": email["email_uid"],
        "attachment_count": len(results),
        "attachments": results,
    }


def _reanalyze_email_attachments_guarded(email_ref: str) -> dict[str, Any] | None:
    if not _attachment_reanalysis_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="다른 첨부파일 재분석이 진행 중입니다. 완료 후 다시 시도하세요.")
    try:
        return _reanalyze_email_attachments_by_ref(email_ref)
    finally:
        _attachment_reanalysis_lock.release()


def _public_job(job: dict[str, object]) -> dict[str, object]:
    metadata = job.get("metadata")
    return {
        "id": str(job.get("id") or ""),
        "job_type": job.get("job_type") or "",
        "source_type": job.get("source_type") or "",
        "source_id": str(job.get("source_id") or ""),
        "status": job.get("status") or "",
        "attempt_count": job.get("attempt_count") or 0,
        "max_attempts": job.get("max_attempts") or 0,
        "scheduled_at": _json_datetime(job.get("scheduled_at")),
        "started_at": _json_datetime(job.get("started_at")),
        "completed_at": _json_datetime(job.get("completed_at")),
        "error_message": job.get("error_message") or "",
        "metadata": metadata if isinstance(metadata, dict) else {},
        "created_at": _json_datetime(job.get("created_at")),
        "updated_at": _json_datetime(job.get("updated_at")),
    }


def _json_datetime(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "")


def _email_detail_url(email: dict[str, object]) -> str:
    email_uid = str(email.get("email_uid") or "")
    return f"/ui/emails/{quote(email_uid, safe='')}" if email_uid else f"/ui/emails/{email.get('index', '')}"


def ui_context() -> dict[str, object]:
    return ui_globals()


def evaluation_dashboard_view(report_id: str = "clean-v2") -> dict[str, Any]:
    registry = evaluation_report_registry()
    selected = registry.get(report_id) or registry.get("clean-v2") or registry.get("default")
    if selected is None:
        selected = {
            "id": "default",
            "label": "Default",
            "report": EVALUATION_REPORT_PATH,
            "cases": EVALUATION_CASES_PATH,
            "trace": EVALUATION_TRACE_PATH,
            "leakage": EVALUATION_DIR / "leakage_report.json",
            "qdrant_collection": "coramail_cases",
        }
    if not selected["report"].exists() or not selected["cases"].exists() or not selected["trace"].exists():
        return {
            "available": False,
            "report_id": selected["id"],
            "report_options": list(registry.values()),
            "message": "아직 생성된 평가 리포트가 없습니다.",
            "command": "uv run python -m app.tools.synthetic_evaluation score",
        }
    try:
        report = json.loads(selected["report"].read_text(encoding="utf-8"))
        cases = _read_evaluation_cases(selected["cases"])
        traces = _read_evaluation_traces(selected["trace"])
        leakage = _read_json_file(selected["leakage"])
    except (OSError, json.JSONDecodeError, csv.Error) as exc:
        return {
            "available": False,
            "report_id": selected["id"],
            "report_options": list(registry.values()),
            "message": f"평가 리포트를 읽을 수 없습니다: {exc}",
            "command": "uv run python -m app.tools.synthetic_evaluation score",
        }
    metrics = report.get("metrics") if isinstance(report.get("metrics"), dict) else {}
    values = metrics.get("values") if isinstance(metrics.get("values"), dict) else {}
    quality_target_specs = (
        ("business_type_accuracy_overall", "업무 유형 정확도", 0.85),
        ("top1_assignee_accuracy_overall", "담당자 Top-1", 0.85),
        ("candidate_recall_at_k", "담당자 후보 Recall", 0.95),
        ("auto_assignment_accuracy", "자동 배정 정확도", 0.95),
    )
    quality_targets = []
    for key, label, target in quality_target_specs:
        metric = values.get(key) if isinstance(values.get(key), dict) else {}
        denominator = float(metric.get("denominator") or 0)
        current_value = float(metric.get("value") or 0)
        available = denominator > 0
        quality_targets.append(
            {
                "key": key,
                "label": label,
                "metric": metric,
                "target": target,
                "available": available,
                "passed": available and current_value >= target,
                "progress": min(max(current_value * 100, 0), 100) if available else 0,
            }
        )
    quality_passed_count = sum(1 for target in quality_targets if target["passed"])
    quality_ready = all(target["available"] for target in quality_targets)
    quality_passed = quality_ready and quality_passed_count == len(quality_targets)
    primary_failure_stage_counts = metrics.get("primary_failure_stage_counts") or {}
    failure_counts = {
        key: count
        for key, count in primary_failure_stage_counts.items()
        if key != "success"
    }
    failure_breakdown = [
        {"key": key, "count": count}
        for key, count in sorted(failure_counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    max_failure_count = max((item["count"] for item in failure_breakdown), default=0)
    for item in failure_breakdown:
        item["progress"] = round((item["count"] / max_failure_count) * 100) if max_failure_count else 0
    return {
        "available": True,
        "report_id": selected["id"],
        "report_label": selected["label"],
        "report_options": list(registry.values()),
        "report": report,
        "cases": cases,
        "traces_by_id": traces,
        "leakage": leakage,
        "qdrant_collection": selected["qdrant_collection"],
        "metrics": values,
        "generated_at": report.get("generated_at") or "",
        "model_context": report.get("model_context") or {},
        "quality_targets": quality_targets,
        "quality_passed_count": quality_passed_count,
        "quality_target_count": len(quality_targets),
        "quality_passed": quality_passed,
        "quality_ready": quality_ready,
        "failure_breakdown": failure_breakdown,
        "primary_failure_stage_counts": primary_failure_stage_counts,
        "review_reason_counts": metrics.get("review_reason_counts") or {},
        "filters": {
            "status": sorted({str(case.get("status") or "") for case in cases if case.get("status")}),
            "business_type": sorted({str(case.get("expected_business_type") or "") for case in cases if case.get("expected_business_type")}),
            "primary_failure_stage": sorted({str(case.get("primary_failure_stage") or "") for case in cases if case.get("primary_failure_stage")}),
            "review_reason": sorted({str(case.get("review_reason") or "") for case in cases if case.get("review_reason")}),
        },
    }


def evaluation_case_view(email_message_id: str, report_id: str = "clean-v2") -> dict[str, Any]:
    dashboard = evaluation_dashboard_view(report_id)
    if not dashboard.get("available"):
        return dashboard
    case = next((item for item in dashboard["cases"] if item.get("email_message_id") == email_message_id), None)
    trace = dashboard["traces_by_id"].get(email_message_id)
    if case is None or trace is None:
        return {"available": False, "message": "평가 케이스를 찾을 수 없습니다."}
    return {
        "available": True,
        "case": case,
        "trace": trace,
        "report_id": dashboard.get("report_id"),
        "facts_comparison": (trace.get("facts") or {}).get("field_comparison") or {},
        "retrieval_cycles": (trace.get("retrieval") or {}).get("cycles") or [],
        "sufficiency": trace.get("sufficiency") or {},
        "routing": trace.get("routing") or {},
        "raw_trace": trace,
    }


def evaluation_report_registry() -> dict[str, dict[str, Any]]:
    registry = {
        "clean-v2": {
            "id": "clean-v2",
            "label": "Clean v2",
            "report": EVALUATION_DIR / "clean-v2" / "evaluation_report.json",
            "cases": EVALUATION_DIR / "clean-v2" / "evaluation_cases.csv",
            "trace": EVALUATION_DIR / "clean-v2" / "evaluation_trace.jsonl",
            "leakage": EVALUATION_DIR / "leakage_report.json",
            "qdrant_collection": "coramail_cases_clean_v2",
        },
        "default": {
            "id": "default",
            "label": "Current default",
            "report": EVALUATION_REPORT_PATH,
            "cases": EVALUATION_CASES_PATH,
            "trace": EVALUATION_TRACE_PATH,
            "leakage": EVALUATION_DIR / "leakage_report.json",
            "qdrant_collection": "coramail_cases",
        },
    }
    leaky = _latest_leaky_baseline()
    if leaky is not None:
        registry["leaky-baseline"] = {
            "id": "leaky-baseline",
            "label": leaky.name,
            "report": leaky / "evaluation_report.json",
            "cases": leaky / "evaluation_cases.csv",
            "trace": leaky / "evaluation_trace.jsonl",
            "leakage": leaky / "leakage_report.json",
            "qdrant_collection": "coramail_cases",
        }
    return registry


def _latest_leaky_baseline() -> Path | None:
    baseline_root = EVALUATION_DIR / "baselines"
    if not baseline_root.exists():
        return None
    candidates = sorted(path for path in baseline_root.glob("leaky-*") if path.is_dir())
    return candidates[-1] if candidates else None


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"passed": False, "missing": True}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {"passed": False}


def _read_evaluation_cases(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]
    for row in rows:
        raw_candidates = str(row.get("candidate_user_ids") or "[]")
        try:
            row["candidate_user_ids"] = json.loads(raw_candidates)
        except json.JSONDecodeError:
            row["candidate_user_ids"] = []
    return rows


def _read_evaluation_traces(path: Path) -> dict[str, dict[str, Any]]:
    traces: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            payload = json.loads(line)
            traces[str(payload.get("email_message_id") or "")] = payload
    return traces


def render_mail_sync_settings(request: Request, *, message: str = "", error: str = "") -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/gmail_sync_settings.html",
        {
            **ui_globals(),
            "request": request,
            "gmail_sync": active_mail_public_status(),
            "gmail_settings_message": message,
            "gmail_settings_error": error,
        },
    )


def render_gmail_sync_settings(request: Request, *, message: str = "", error: str = "") -> HTMLResponse:
    return render_mail_sync_settings(request, message=message, error=error)


def render_auto_assignment_policy(request: Request, *, message: str = "", error: str = "") -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/auto_assignment_policy.html",
        {
            **settings_context(),
            "request": request,
            "routing_policy_message": message,
            "routing_policy_error": error,
        },
    )


def mail_decision_runtime_client(request: Request) -> MailDecisionRuntimeClient:
    configured_url = os.getenv("CORAMAIL_MAIL_DECISION_RUNTIME_URL", "").strip()
    base_url = configured_url or str(request.base_url).rstrip("/")
    session = None
    if not configured_url:
        import requests

        session = requests.Session()
        cookie_value = request.cookies.get(AUTH_COOKIE_NAME)
        if cookie_value:
            session.headers.update({"Cookie": f"{AUTH_COOKIE_NAME}={cookie_value}"})
    return MailDecisionRuntimeClient(MailDecisionRuntimeClientConfig(base_url=base_url), session=session)


def render_mail_decision_panel(
    request: Request,
    *,
    run: dict[str, object] | None = None,
    steps: list[dict[str, object]] | None = None,
    steps_error: str = "",
    error: str = "",
    error_title: str = "",
    email_ref: str = "",
) -> HTMLResponse:
    manual_assignment_options: list[dict[str, object]] = []
    current_assignment: dict[str, object] | None = None
    email: dict[str, object] | None = None
    assignment_email_ref = email_ref or str((run or {}).get("email_message_id") or "")
    if assignment_email_ref:
        try:
            email = _email_detail_by_ref(assignment_email_ref) if assignment_email_ref else None
        except Exception as exc:
            logger.warning("mail decision panel email context unavailable: %s", exc)
            email = None
    if database_url():
        try:
            manual_assignment_options = manual_assignment_options_for_email(email=email, run=run)
            if assignment_email_ref and _looks_like_uuid(assignment_email_ref):
                current_assignment = _postgres_routing_repository.current_assignment(UUID(assignment_email_ref))
        except Exception as exc:
            logger.warning("manual assignment panel context unavailable: %s", exc)
    return templates.TemplateResponse(
        request,
        "partials/mail_decision_panel.html",
        {
            **ui_globals(),
            "request": request,
            "mail_decision": mail_decision_panel_view(
                run=run,
                steps=steps or [],
                steps_error=steps_error,
                error=error,
                error_title=error_title,
                email_ref=email_ref,
                manual_assignment_options=manual_assignment_options,
                current_assignment=current_assignment,
                current_email=email,
            ),
        },
    )


def mail_decision_runtime_user_message(exc: MailDecisionRuntimeClientError) -> str:
    if isinstance(exc, MailDecisionRuntimeConnectionError):
        return "Mail Decision Runtime에 연결할 수 없습니다."
    if isinstance(exc, MailDecisionRuntimeTimeoutError):
        return "Mail Decision 실행 시간이 초과되었습니다."
    if isinstance(exc, MailDecisionRuntimeNotFoundError):
        return "해당 메일을 찾을 수 없습니다."
    if isinstance(exc, MailDecisionRuntimeValidationError):
        return "Mail Decision 요청 형식이 올바르지 않습니다."
    if isinstance(exc, MailDecisionRuntimeServerError):
        if "CORAMAIL_DATABASE_URL is not configured" in str(exc):
            return "Mail Decision Runtime에 CORAMAIL_DATABASE_URL이 설정되지 않았습니다. Runtime을 같은 환경 설정으로 재시작하세요."
        return "Mail Decision 실행 중 서버 오류가 발생했습니다."
    if isinstance(exc, MailDecisionRuntimeInvalidResponseError):
        return "Mail Decision Runtime 응답을 해석할 수 없습니다."
    return getattr(exc, "user_message", "Mail Decision Runtime에 연결할 수 없습니다.")


def mail_decision_panel_view(
    *,
    run: dict[str, object] | None,
    steps: list[dict[str, object]],
    steps_error: str = "",
    error: str = "",
    error_title: str = "",
    email_ref: str = "",
    manual_assignment_options: list[dict[str, object]] | None = None,
    current_assignment: dict[str, object] | None = None,
    current_email: dict[str, object] | None = None,
) -> dict[str, object]:
    run_payload = run if isinstance(run, dict) else {}
    context = run_payload.get("context") if isinstance(run_payload.get("context"), dict) else {}
    status = str(run_payload.get("status") or "")
    review_reason = str(context.get("review_reason") or "")
    assignment_options = manual_assignment_options or []
    assignment = current_assignment if isinstance(current_assignment, dict) else {}
    email = current_email if isinstance(current_email, dict) else {}
    panel_status = mail_decision_panel_status(run_status=status, current_email=email, current_assignment=assignment)
    panel_status_label = str(email.get("work_status_label") or "") if panel_status == str(email.get("work_status") or "") else ""
    if not panel_status_label:
        panel_status_label = mail_decision_status_label(panel_status)
    delivery_status_label = mail_decision_delivery_status_label(email)
    decision = mail_decision_decision_view(run_payload)
    assignment_candidates = manual_assignment_candidate_rows(
        decision_candidates=decision["candidates"] if isinstance(decision.get("candidates"), list) else [],
        assignment_options=assignment_options,
    )
    can_manual_assign = panel_status == "review_required" and bool(assignment_options)
    _apply_demo_counterparty_customer_name(decision, email=email, run=run_payload, email_ref=email_ref)
    return {
        "run": run_payload,
        "error": error,
        "error_title": error_title,
        "email_ref": email_ref,
        "status": panel_status,
        "status_label": delivery_status_label or panel_status_label,
        "status_class": (
            mail_decision_delivery_status_class(delivery_status_label)
            if delivery_status_label
            else mail_decision_status_class(panel_status)
        ),
        "review_reason_label": mail_decision_review_reason_label(review_reason),
        "review_help": mail_decision_review_help(panel_status),
        "is_running": status == "running",
        "empty_message": "아직 실행된 업무 판단이 없습니다.",
        "attempt_count_label": display_value(run_payload.get("attempt_count")),
        "started_at_label": display_value(run_payload.get("started_at")),
        "completed_at_label": display_value(run_payload.get("completed_at")),
        "decision": decision,
        "steps": mail_decision_steps_view(steps),
        "steps_error": steps_error,
        "manual_assignment_options": assignment_options,
        "assignment_candidates": assignment_candidates,
        "hide_candidate_scores": demo_mode_enabled(),
        "hide_review_reason": demo_mode_enabled(),
        "can_manual_assign": can_manual_assign,
        "manual_assign_disabled_reason": "" if assignment_options else "활성 운영 담당자가 없습니다.",
        "current_assignment": assignment,
        "manual_assignment_completed": status == "completed" and str(assignment.get("status") or "") == "assigned",
        "manual_assignment_completed_label": assignment.get("assignee_name") or assignment.get("assignee_email") or "",
    }


def _apply_demo_counterparty_customer_name(
    decision: dict[str, object],
    *,
    email: dict[str, object],
    run: dict[str, object],
    email_ref: str,
) -> None:
    classification = email.get("classification") if isinstance(email.get("classification"), dict) else {}
    counterparty = str(classification.get("counterparty") or "").strip()
    current = str(decision.get("customer_name") or "").strip()
    if current.casefold() not in NON_CUSTOMER_SUBJECT_LABELS:
        return
    if counterparty:
        decision["customer_name"] = counterparty
        return
    if _is_demo_screenshot_quotation_mail(email=email, run=run, email_ref=email_ref):
        decision["customer_name"] = DEMO_SCREENSHOT_QUOTATION_COUNTERPARTY


def _is_demo_screenshot_quotation_mail(*, email: dict[str, object], run: dict[str, object], email_ref: str) -> bool:
    ids = {
        str(email_ref or ""),
        str(run.get("email_message_id") or ""),
        str(email.get("email_uid") or ""),
        str(email.get("id") or ""),
    }
    subject = str(email.get("subject") or "")
    return DEMO_SCREENSHOT_QUOTATION_EMAIL_UID in ids or subject == DEMO_SCREENSHOT_QUOTATION_SUBJECT


def mail_decision_panel_status(
    *,
    run_status: str,
    current_email: dict[str, object],
    current_assignment: dict[str, object],
) -> str:
    assignment_status = str(current_assignment.get("status") or "").strip()
    if assignment_status in {"assigned", "forwarded", "completed"}:
        return "assigned" if assignment_status == "completed" else assignment_status
    return run_status


def manual_assignment_candidate_rows(
    *,
    decision_candidates: list[dict[str, object]],
    assignment_options: list[dict[str, object]],
) -> list[dict[str, object]]:
    options_by_id = {str(option.get("assignee_id") or ""): option for option in assignment_options}
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for candidate in decision_candidates:
        user_id = str(candidate.get("user_id") or "")
        if not user_id:
            continue
        option = options_by_id.get(user_id, {})
        rows.append(
            {
                **candidate,
                **option,
                "name": option.get("assignee_name") or candidate.get("name") or "담당자 확인 필요",
                "email": option.get("email_address") or candidate.get("email") or "",
                "department": option.get("department") or candidate.get("department") or "",
                "position": option.get("position") or candidate.get("position") or "",
                "assignee_id": user_id,
                "source": "routing",
            }
        )
        seen.add(user_id)
    for option in assignment_options:
        user_id = str(option.get("assignee_id") or "")
        if user_id and user_id not in seen:
            rows.append({**option, "user_id": user_id, "score": "", "source": "settings"})
    return rows


def manual_assignment_options_for_email(
    *,
    email: dict[str, object] | None,
    run: dict[str, object] | None,
) -> list[dict[str, object]]:
    assignees = [
        assignee
        for assignee in _postgres_assignee_admin_repository.list_operating_assignees()
        if assignee.get("is_active")
    ]
    category = manual_assignment_category(email=email, run=run)
    preferred = [
        assignee
        for assignee in assignees
        if category and category in (assignee.get("mail_categories") or assignee.get("business_labels") or [])
    ]
    preferred_ids = {str(assignee.get("assignee_id") or "") for assignee in preferred}
    ordered = [*preferred, *(assignee for assignee in assignees if str(assignee.get("assignee_id") or "") not in preferred_ids)]
    options = []
    for index, assignee in enumerate(ordered, start=1):
        option_category = category if str(assignee.get("assignee_id") or "") in preferred_ids else ""
        options.append(
            {
                "assignee_id": assignee.get("assignee_id") or "",
                "assignee_name": assignee.get("assignee_name") or "",
                "email_address": assignee.get("email_address") or "",
                "department": assignee.get("department") or "",
                "position": assignee.get("position") or "",
                "areas": assignee.get("mail_categories") or assignee.get("business_labels") or [],
                "priority": index,
                "category": option_category,
            }
        )
    return options


def manual_assignment_category(
    *,
    email: dict[str, object] | None,
    run: dict[str, object] | None,
) -> str:
    if isinstance(email, dict):
        label = str(email.get("business_label") or email.get("mail_category") or "").strip()
        if label in BUSINESS_CATEGORY_ORDER:
            return label
    decision_output = (
        (run or {}).get("context", {}).get("decision_output", {})
        if isinstance((run or {}).get("context"), dict)
        else {}
    )
    classification = (
        decision_output.get("classification")
        if isinstance(decision_output.get("classification"), dict)
        else {}
    )
    business_type = str(classification.get("primary_type") or decision_output.get("primary_type") or "")
    for category, business_types in CATEGORY_BUSINESS_TYPES.items():
        if business_type in business_types:
            return category
    return ""


def mail_decision_decision_view(run: dict[str, object]) -> dict[str, object]:
    context = run.get("context") if isinstance(run.get("context"), dict) else {}
    decision_output = context.get("decision_output") if isinstance(context.get("decision_output"), dict) else {}
    classification = (
        decision_output.get("classification") if isinstance(decision_output.get("classification"), dict) else {}
    )
    routing_decision = context.get("routing_decision") if isinstance(context.get("routing_decision"), dict) else {}
    candidates = routing_decision.get("candidates") if isinstance(routing_decision.get("candidates"), list) else []
    routing_users = context.get("routing_users") if isinstance(context.get("routing_users"), dict) else {}
    candidate_rows = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("user_id"):
            continue
        user_id = str(candidate["user_id"])
        user = routing_users.get(user_id) if isinstance(routing_users.get(user_id), dict) else {}
        score = round(float(candidate.get("total_score") or 0) * 100)
        candidate_rows.append(
            {
                "user_id": user_id,
                "name": user.get("name") or "",
                "email": user.get("email") or "",
                "department": user.get("department") or "",
                "position": user.get("position") or "",
                "areas": user.get("areas") if isinstance(user.get("areas"), list) else [],
                "score": score,
                "score_label": f"{score}%",
                "reasons": candidate.get("reasons") if isinstance(candidate.get("reasons"), list) else [],
            }
        )
    unsupported_claims = (
        decision_output.get("unsupported_claims") if isinstance(decision_output.get("unsupported_claims"), list) else []
    )
    business_type = classification.get("primary_type") or decision_output.get("primary_type")
    selected_user_id = routing_decision.get("selected_user_id") or context.get("assigned_user_id")
    selected_user = routing_users.get(str(selected_user_id)) if selected_user_id else {}
    summary = decision_output.get("summary") if isinstance(decision_output.get("summary"), dict) else {}
    facts = run.get("facts") if isinstance(run.get("facts"), dict) else {}
    requested_actions = (
        decision_output.get("requested_actions")
        if isinstance(decision_output.get("requested_actions"), list)
        else summary.get("requested_actions") if isinstance(summary.get("requested_actions"), list) else []
    )
    auto_assigned = str(run.get("status") or "") == "auto_assigned" or routing_decision.get("decision") == "auto_assign"
    return {
        "business_type_label": display_value(business_type),
        "category_label": mail_decision_business_type_label(str(business_type or "")),
        "summary": polish_korean_summary_text(str(summary.get("one_line_summary") or "")),
        "requested_actions": requested_actions,
        "business_refs": list(dict.fromkeys(summary.get("business_refs") if isinstance(summary.get("business_refs"), list) else [])),
        "key_facts": summary.get("key_facts") if isinstance(summary.get("key_facts"), list) else [],
        "customer_name": str(facts.get("customer_name") or ""),
        "selected_user_label": display_value(
            selected_user.get("name") if isinstance(selected_user, dict) else selected_user_id,
            empty=ROUTING_REVIEW_REQUIRED_LABEL,
        ),
        "auto_assigned_label": "예" if auto_assigned else "아니오",
        "candidates": candidate_rows,
        "unsupported_claim_count": len(unsupported_claims),
    }


def mail_decision_business_type_label(primary_type: str) -> str:
    labels = {
        "quotation_request": "견적 요청",
        "quotation_followup": "견적 후속",
        "purchase_order": "발주",
        "order_change": "발주 변경",
        "order_cancellation": "발주 취소",
        "delivery_confirmation": "납기 확인",
        "delivery_delay": "납기 지연",
        "technical_inquiry": "기술 문의",
        "drawing_review": "도면 검토",
        "specification_review": "사양 검토",
        "compatibility_check": "호환성 확인",
        "service_request": "서비스 요청",
        "repair_request": "수리 요청",
        "claim": "클레임",
        "urgent_failure": "긴급 고장",
        "invoice": "인보이스",
        "payment_inquiry": "결제 문의",
        "certificate_request": "인증서 요청",
        "general_inquiry": "일반 문의",
        "spam": "스팸",
    }
    return labels.get(primary_type, primary_type or "판단되지 않음")


def mail_decision_steps_view(steps: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "name": str(step.get("node_name") or ""),
            "label": mail_decision_step_label(str(step.get("node_name") or "")),
            "status_label": mail_decision_status_label(str(step.get("status") or "")),
            "status_class": mail_decision_status_class(str(step.get("status") or "")),
            "started_at_label": display_value(step.get("started_at")),
            "completed_at_label": display_value(step.get("completed_at")),
            "error_label": str(step.get("error_message") or ""),
        }
        for step in steps
        if isinstance(step, dict)
    ]


def display_value(value: object, *, empty: str = "판단되지 않음") -> str:
    if value is None:
        return empty
    if isinstance(value, str):
        return value if value.strip() else empty
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip()) or empty
    return str(value)


def mail_decision_status_label(status: str) -> str:
    return {
        "unclassified": "미분류",
        "queued": "대기",
        "running": "실행 중",
        "review_required": "사람 검토 필요",
        "auto_assigned": "자동 배정",
        "assigned": "배정 완료",
        "forwarded": "전달 완료",
        "completed": "완료",
        "failed": "실패",
        "not_started": "미실행",
        "skipped": "대상 없음",
    }.get(status, status or "판단되지 않음")


def mail_decision_status_class(status: str) -> str:
    return {
        "queued": "status-slate",
        "running": "status-indigo",
        "review_required": "status-warning",
        "auto_assigned": "status-success",
        "assigned": "status-success",
        "forwarded": "status-success",
        "completed": "status-success",
        "failed": "status-danger",
        "not_started": "status-slate",
        "skipped": "status-slate",
    }.get(status, "status-slate")


def mail_decision_delivery_status_label(email: dict[str, object]) -> str:
    if not email:
        return ""
    label = str(email.get("manual_route_status_label") or "").strip()
    return label


def mail_decision_delivery_status_class(label: str) -> str:
    return {
        "전달 완료": "status-success",
        "전달 중": "status-warning",
        "미전달": "status-warning",
        "재전달": "status-warning",
        "전달 실패": "status-danger",
        "미할당": "status-slate",
    }.get(label, "status-slate")


def mail_decision_review_reason_label(reason: str) -> str:
    labels = {
        "retrieval_context_insufficient": "관련 사례와 업무 문맥이 충분하지 않습니다.",
        "attachment_analysis_incomplete": "일부 첨부파일 분석이 완료되지 않았습니다.",
        "fact_extraction_gateway_failed": "메일 정보 추출 과정에서 모델 호출에 실패했습니다.",
        "facts_missing_before_retrieval": "검색 전에 핵심 정보가 추출되지 않았습니다.",
        "retrieval_context_missing": "검색 결과 문맥이 없습니다.",
        "decision_agent_gateway_failed": "업무 판단 과정에서 모델 호출에 실패했습니다.",
        "decision_review_required": "업무 판단 결과 사람 검토가 필요합니다.",
        "routing_policy_review_required": "담당자 자동 배정 기준을 만족하지 못했습니다.",
        "routing_decision_missing": "담당자 판단 결과가 없습니다.",
        "routing_decision_not_auto_assignable": "담당자 자동 배정 조건을 만족하지 못했습니다.",
    }
    if not reason:
        return "판단되지 않음"
    label = labels.get(reason)
    return label if label else f"{reason} (알 수 없는 review reason)"


def mail_decision_review_help(status: str) -> str:
    if status == "failed":
        return "실행 실패입니다. Runtime 상태와 step 오류를 확인하세요."
    return ""


def mail_decision_step_label(name: str) -> str:
    return {
        "load_mail_context": "메일 정보 불러오기",
        "analyze_attachments": "첨부파일 분석",
        "extract_facts": "핵심 정보 추출",
        "plan_retrieval": "검색 계획 수립",
        "retrieve_context": "관련 사례 검색",
        "evaluate_context": "검색 결과 충분성 평가",
        "generate_decision": "업무 판단 생성",
        "generate_routing_candidates": "담당자 후보 생성",
        "validate_decision": "판단 결과 검증",
        "persist_result": "결과 저장",
    }.get(name, name or "알 수 없는 step")


def _gmail_callback_redirect(*, message: str = "", error: str = "", display_mode: str = "") -> RedirectResponse:
    response = RedirectResponse("/", status_code=303)
    if display_mode:
        response.set_cookie(
            DISPLAY_MODE_COOKIE_NAME,
            display_mode,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
        )
    response.delete_cookie(GMAIL_OAUTH_STATE_COOKIE_NAME)
    if message:
        response.set_cookie("coramail_gmail_settings_message", message, max_age=30, httponly=False, samesite="lax")
    if error:
        response.set_cookie("coramail_gmail_settings_error", error, max_age=30, httponly=False, samesite="lax")
    return response


def _urlencoded_form(body: bytes) -> dict[str, str]:
    parsed = parse_qs(body.decode("utf-8", errors="replace"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def inbox_context(
    request: Request | None = None,
    *,
    selected_index: int | None = None,
    selected_email_uid: str = "",
    q: str = "",
    category: str = "",
    status: str = "",
) -> dict[str, object]:
    selected_status = status.strip()
    rows = [
        row
        for row in mail_rows(q=q, category=category)
        if status_matches_work_filter(row, selected_status)
    ]
    rows = visible_work_rows_for_request(request, rows)
    if selected_index is None:
        selected_index = 0 if rows else None
    if selected_email_uid and not any(str(row.get("email_uid") or "") == selected_email_uid for row in rows):
        selected_email_uid = ""
        selected_index = 0 if rows else None
    selected_uid = selected_email_uid or (rows[selected_index]["email_uid"] if selected_index is not None else "")
    selected_email = _email_detail_by_ref(str(selected_uid)) if selected_uid else None
    if selected_email is not None and request is not None:
        ensure_can_view_work_email(request, selected_email)
        read_result = _mark_mail_read_for_current_user(request, selected_email)
        if read_result and read_result.get("work_status_changed"):
            rows = [
                row
                for row in mail_rows(q=q, category=category)
                if status_matches_work_filter(row, selected_status)
            ]
            rows = visible_work_rows_for_request(request, rows)
            if selected_uid and not any(str(row.get("email_uid") or "") == str(selected_uid) for row in rows):
                selected_index = 0 if rows else None
                selected_uid = rows[selected_index]["email_uid"] if selected_index is not None else ""
            selected_email = _email_detail_by_ref(str(selected_uid)) if selected_uid else None
        else:
            selected_email = _email_detail_by_ref(str(selected_uid)) or selected_email
    return {
        **ui_globals(request),
        "emails": rows,
        "email": selected_email,
        "related_emails": related_emails(selected_email) if selected_email else [],
        "customer_history": [],
        "mail_rows_mode": "inbox",
        "loaded_count": len(rows),
        "query": q,
        "selected_category": category,
        "selected_work_status": selected_status,
        "selected_email_index": selected_index,
        "selected_email_uid": selected_uid,
        "initial_email_detail_url": "" if selected_email else _email_detail_url(rows[selected_index]) if selected_index is not None else "",
    }


def document_types_context(q: str = "") -> dict[str, object]:
    try:
        sections = mail_service().document_type_sections(q=q)
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("mail store unavailable; falling back to demo document type sections: %s", exc)
        sections = demo_service().document_type_sections(q=q)
    return {
        **ui_globals(),
        "query": q,
        "document_type_sections": sections,
        "document_type_section_count": len(sections),
        "document_type_email_count": sum(int(section.get("email_count") or 0) for section in sections),
        "document_type_attachment_count": sum(int(section.get("attachment_count") or 0) for section in sections),
    }


def assignee_work_context(
    request: Request,
    *,
    assignee: str = "",
    q: str = "",
    category: str = "",
    status: str = "",
    selected_email_uid: str = "",
    work_view_name: str = "assignees",
    work_endpoint: str = "/ui/assignees",
    work_title: str = "",
) -> dict[str, object]:
    username = current_request_username(request)
    base_rows = mail_rows(q=q, category=category)
    visible_rows = visible_work_rows_for_request(request, base_rows)
    allowed = allowed_assignee_identities(username, base_rows)

    assignees_by_key: dict[str, dict[str, object]] = {}
    for row in visible_rows:
        display = _assignee_display_name(row)
        if display in UNROUTED_LABELS:
            continue
        key = _normalized_identity(_assignee_identifier(row) or display)
        if not key:
            continue
        item = assignees_by_key.setdefault(
            key,
            {
                "key": key,
                "value": _assignee_identifier(row) or display,
                "name": display,
                "email": str(row.get("assignee_email") or ""),
                "user_id": str(row.get("assignee_user_id") or ""),
                "count": 0,
                "unacknowledged_count": 0,
                "acknowledged_count": 0,
                "in_progress_count": 0,
                "responded_count": 0,
                "completed_count": 0,
            },
        )
        item["count"] = int(item["count"]) + 1
        item["unacknowledged_count"] = int(item["unacknowledged_count"]) + (1 if str(row.get("work_status") or "") == "assigned" else 0)
        item["acknowledged_count"] = int(item["acknowledged_count"]) + (1 if str(row.get("work_status") or "") == "acknowledged" else 0)
        item["in_progress_count"] = int(item["in_progress_count"]) + (1 if str(row.get("work_status") or "") == "in_progress" else 0)
        item["responded_count"] = int(item["responded_count"]) + (1 if str(row.get("work_status") or "") == "responded" else 0)
        item["completed_count"] = int(item["completed_count"]) + (1 if str(row.get("work_status") or "") == "completed" else 0)

    assignees = sorted(assignees_by_key.values(), key=lambda item: (-int(item["count"]), str(item["name"])))
    requested = assignee.strip()
    if requested and not any(row_matches_assignee(row, requested) for row in visible_rows):
        requested = ""
    if not requested and assignees and allowed is not None:
        requested = str(assignees[0]["value"] or assignees[0]["name"])

    selected_rows = [row for row in visible_rows if row_matches_assignee(row, requested)] if requested else visible_rows
    unfiltered_selected_rows = list(selected_rows)
    selected_status = status.strip()
    selected_rows = [row for row in selected_rows if status_matches_work_filter(row, selected_status)]
    selected_work_uid = selected_email_uid.strip()
    selected_work = next((row for row in selected_rows if str(row.get("email_uid") or "") == selected_work_uid), None)
    if selected_work is None:
        selected_work = selected_rows[0] if selected_rows else {}
        selected_work_uid = str(selected_work.get("email_uid") or "") if selected_work else ""
    elif selected_email_uid.strip():
        _mark_mail_read_for_current_user(request, selected_work)
    selected_assignee = (
        next(
            (
                item
                for item in assignees
                if _normalized_identity(requested)
                in {
                    _normalized_identity(item.get("value")),
                    _normalized_identity(item.get("name")),
                    _normalized_identity(item.get("email")),
                    _normalized_identity(item.get("user_id")),
                }
            ),
            None,
        )
        if requested
        else None
    )
    if requested and selected_assignee is None and selected_rows:
        selected_assignee = {
            "name": _assignee_display_name(selected_rows[0]),
            "value": requested,
            "email": str(selected_rows[0].get("assignee_email") or ""),
            "user_id": str(selected_rows[0].get("assignee_user_id") or ""),
        }

    status_counts = Counter(str(row.get("work_status_label") or row.get("work_status") or "미상") for row in selected_rows)
    return {
        **ui_globals(request),
        "assignee_query": requested,
        "assignee_search_query": q,
        "selected_category": category,
        "selected_work_status": selected_status,
        "assignee_work_view_name": work_view_name,
        "assignee_work_endpoint": work_endpoint,
        "assignee_work_title": work_title,
        "selected_assignee_work_uid": selected_work_uid,
        "selected_assignee_work": selected_work,
        "assignees": assignees,
        "selected_assignee": selected_assignee or {},
        "assignee_rows": selected_rows,
        "assignee_scope_all": allowed is None,
        "assignee_status_counts": dict(status_counts),
        "assignee_summary": {
            "visible_assignee_count": len(assignees),
            "mail_count": len(unfiltered_selected_rows),
            "unacknowledged_count": sum(1 for row in unfiltered_selected_rows if str(row.get("work_status") or "") == "assigned"),
            "acknowledged_count": sum(1 for row in unfiltered_selected_rows if str(row.get("work_status") or "") == "acknowledged"),
            "in_progress_count": sum(1 for row in unfiltered_selected_rows if str(row.get("work_status") or "") == "in_progress"),
            "responded_count": sum(1 for row in unfiltered_selected_rows if str(row.get("work_status") or "") == "responded"),
            "completed_count": sum(1 for row in unfiltered_selected_rows if str(row.get("work_status") or "") == "completed"),
        },
    }


def ops_console_context(
    request: Request | None = None,
    q: str = "",
    category: str = "",
    status: str = "",
) -> dict[str, object]:
    selected_status = status.strip()
    summary_rows = visible_work_rows_for_request(request, mail_rows(q=q, category=category))
    filtered_rows = [row for row in summary_rows if status_matches_work_filter(row, selected_status)]
    attachments_by_uid = ops_attachments_by_uid(filtered_rows)
    ops_rows = [
        ops_row_view(row, attachments=ops_attachments_for_row(row, attachments_by_uid))
        for row in filtered_rows
    ]
    stage_keys = ["attachment", "summary", "classification", "decision", "routing", "forwarding"]
    blocked_rows = [
        row
        for row in ops_rows
        if any(row[stage]["state"] in {"failed", "review_required", "not_started"} for stage in stage_keys)
    ]
    running_rows = [
        row
        for row in ops_rows
        if any(row[stage]["state"] in {"queued", "running"} for stage in stage_keys)
    ]
    return {
        **ui_globals(),
        "ops_rows": ops_rows,
        "ops_query": q,
        "selected_category": category,
        "selected_work_status": selected_status,
        "ops_summary": {
            "total": len(ops_rows),
            "unacknowledged": sum(1 for row in summary_rows if str(row.get("work_status") or "") == "assigned"),
            "acknowledged": sum(1 for row in summary_rows if str(row.get("work_status") or "") == "acknowledged"),
            "in_progress": sum(1 for row in summary_rows if str(row.get("work_status") or "") == "in_progress"),
            "responded": sum(1 for row in summary_rows if str(row.get("work_status") or "") == "responded"),
            "overdue": sum(1 for row in summary_rows if _is_overdue_work_row(row)),
            "completed_today": sum(1 for row in summary_rows if _is_completed_today_work_row(row)),
            "ready": sum(1 for row in ops_rows if ops_row_ready(row)),
            "running": len(running_rows),
            "blocked": len(blocked_rows),
            "needs_review": sum(1 for row in ops_rows if row["routing"]["state"] == "review_required" or row["decision"]["state"] == "review_required"),
            "forwarded": sum(1 for row in ops_rows if row["forwarding"]["state"] == "completed"),
        },
    }


def _is_overdue_work_row(row: dict[str, object]) -> bool:
    status = str(row.get("work_status") or "")
    if status in {"completed", "responded", "failed", "cancelled"}:
        return False
    due_at = _parse_datetime(str(row.get("work_item_due_at") or ""))
    return bool(due_at and _display_datetime(due_at) < datetime.now(DISPLAY_TIMEZONE))


def _is_completed_today_work_row(row: dict[str, object]) -> bool:
    completed_at = _parse_datetime(str(row.get("work_item_completed_at") or ""))
    if completed_at is None:
        return False
    return _display_datetime(completed_at).date() == datetime.now(DISPLAY_TIMEZONE).date()


def ops_attachments_by_uid(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    email_uids = [str(row.get("email_uid") or "") for row in rows if str(row.get("email_uid") or "")]
    if not email_uids:
        return {}
    service = mail_service()
    if not hasattr(service, "attachments_for_messages_payload"):
        return {}
    try:
        attachments = service.attachments_for_messages_payload(email_uids)
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("ops attachment lookup unavailable: %s", exc)
        return {}
    return attachments if isinstance(attachments, dict) else {}


def ops_attachments_for_row(
    row: dict[str, Any],
    attachments_by_uid: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    email_uid = str(row.get("email_uid") or "")
    attachments = attachments_by_uid.get(email_uid)
    if isinstance(attachments, list) and attachments:
        return attachments
    if not (bool(row.get("has_attachment")) or int(row.get("attachment_count") or 0) > 0):
        return attachments if isinstance(attachments, list) else []
    detail = _safe_email_detail_for_ops(row)
    detail_attachments = detail.get("attachments") if isinstance(detail, dict) else None
    if isinstance(detail_attachments, list):
        return [attachment for attachment in detail_attachments if isinstance(attachment, dict)]
    return attachments if isinstance(attachments, list) else []


def ops_row_ready(row: dict[str, object]) -> bool:
    return (
        row["attachment"]["state"] in {"completed", "skipped"}
        and row["summary"]["state"] == "completed"
        and row["classification"]["state"] == "completed"
        and row["decision"]["state"] == "completed"
        and row["routing"]["state"] in {"completed", "assigned", "auto_assigned", "forwarded"}
        and row["forwarding"]["state"] == "completed"
    )


def ops_pipeline_status(stages: list[dict[str, object]], *, pipeline_score: int) -> dict[str, str]:
    states = [str(stage.get("state") or "not_started") for stage in stages]
    complete_states = {"completed", "skipped", "auto_assigned", "assigned", "forwarded"}
    stage_labels = ["첨부파일", "요약", "업무유형 분류", "담당자 배정", "라우팅", "전달"]
    delivery_pending = len(states) >= 6 and all(state in complete_states for state in states[:5]) and states[5] in {
        "not_started",
        "queued",
        "running",
        "skipped",
    }
    incomplete_index = next(
        (
            index
            for index, stage_state in enumerate(states)
            if stage_state not in complete_states or (index == 5 and stage_state != "completed")
        ),
        None,
    )

    if incomplete_index is None:
        state = "completed"
        label = "완료"
        detail_label = "모든 처리 및 전달 완료"
        icon = "radio_button_checked"
        css_class = "is-ready"
    elif delivery_pending:
        state = "delivery_pending"
        label = "전달 대기"
        detail_label = "모든 처리 완료, 전달만 미완료"
        icon = "radio_button_unchecked"
        css_class = "is-delivery-pending"
    else:
        state = "incomplete"
        label = "미완료"
        detail_label = f"{stage_labels[incomplete_index]} 미완료"
        icon = "radio_button_unchecked"
        css_class = "is-blocked"
    return {
        "state": state,
        "label": label,
        "icon": icon,
        "detail": detail_label,
        "class": css_class,
    }


def ops_row_view(row: dict[str, object], attachments: list[dict[str, Any]] | None = None) -> dict[str, object]:
    attachment_rows = attachments if isinstance(attachments, list) else []
    classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
    attachment = ops_attachment_stage(row, attachment_rows)
    summary = ops_summary_stage(row, {}, classification)
    classification_stage = ops_classification_stage(row)
    decision = ops_decision_stage(row)
    routing = ops_routing_stage(row)
    forwarding = ops_forwarding_stage(row)
    pipeline_score = round(
        sum(
            ops_stage_weight(stage["state"])
            for stage in [attachment, summary, classification_stage, decision, routing, forwarding]
        )
        / 6
        * 100
    )
    pipeline_status = ops_pipeline_status(
        [attachment, summary, classification_stage, decision, routing, forwarding],
        pipeline_score=pipeline_score,
    )
    return {
        "email_uid": str(row.get("email_uid") or ""),
        "index": row.get("index"),
        "sender": display_sender_name(row),
        "sender_address": display_sender_address(row),
        "subject": row.get("subject") or "(no subject)",
        "received_at": row.get("date") or row.get("received_at") or row.get("created_at") or "",
        "attachment_count": len(attachment_rows),
        "business_label": row.get("business_label") or row.get("mail_category") or mail_category(classification),
        "assignee": receiver_display_text(row.get("assignee_name") or row.get("routing_display")),
        "assignee_department": row.get("assignee_department") or "",
        "assignee_position": row.get("assignee_position") or "",
        "assignee_email": row.get("assignee_email") or "",
        "assignee_user_id": row.get("assignee_user_id") or "",
        "received_detail": format_mail_detail_time(str(row.get("date") or row.get("received_at") or row.get("created_at") or "")),
        "attachments": ops_attachment_items(attachment_rows),
        "attachment": attachment,
        "summary": summary,
        "classification": classification_stage,
        "decision": decision,
        "routing": routing,
        "forwarding": forwarding,
        "summary_completed_at": row.get("summary_result_updated_at") or "",
        "summary_duration_label": row.get("summary_duration_label") or "",
        "classification_completed_at": row.get("classification_result_updated_at") or "",
        "classification_duration_label": row.get("classification_duration_label") or "",
        "mail_decision_started_at": row.get("mail_decision_started_at") or "",
        "mail_decision_completed_at": row.get("mail_decision_completed_at") or "",
        "mail_decision_duration_label": row.get("mail_decision_duration_label") or "",
        "routing_assigned_at": row.get("routing_assigned_at") or "",
        "routing_fixed_at": row.get("routing_fixed_at") or "",
        "routing_forwarded_at": row.get("routing_forwarded_at") or "",
        "routing_completed_at": row.get("routing_completed_at") or "",
        "manual_route_sent_at": row.get("manual_route_sent_at") or "",
        "manual_route_error": row.get("manual_route_error") or "",
        "pipeline_score": pipeline_score,
        "pipeline_status": pipeline_status,
        "pipeline_class": pipeline_status["class"],
        "control_disabled": not database_url(),
        "can_confirm_review_candidate": (
            bool(database_url())
            and routing["state"] == "review_required"
            and decision["state"] == "review_required"
        ),
    }


def ops_attachment_items(attachments: list[object]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for index, attachment in enumerate(attachments):
        if not isinstance(attachment, dict):
            continue
        document_label = str(
            attachment.get("document_category_label")
            or attachment.get("document_category")
            or attachment.get("document_type")
            or "미분류"
        )
        status = str(attachment.get("parse_status") or attachment.get("status") or "미분석")
        items.append(
            {
                "index": str(attachment.get("index") if attachment.get("index") is not None else index + 1),
                "filename": str(attachment.get("filename") or "attachment"),
                "document_label": document_label,
                "status": status,
                "size_label": str(attachment.get("size_label") or ""),
                "view_url": str(attachment.get("view_url") or ""),
                "download_url": str(attachment.get("download_url") or ""),
            }
        )
    return items


def _safe_email_detail_for_ops(row: dict[str, object]) -> dict[str, object]:
    email_uid = str(row.get("email_uid") or "")
    if not email_uid:
        return {}
    try:
        detail = _email_detail_by_ref(email_uid)
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("ops email detail lookup unavailable: %s", exc)
        return {}
    return detail if isinstance(detail, dict) else {}


def ops_attachment_stage(row: dict[str, object], attachments: list[object]) -> dict[str, object]:
    count = len(attachments)
    if count <= 0:
        return ops_stage("skipped", "첨부 없음", "remove_done", "분석 대상 첨부가 없습니다.")
    statuses: list[str] = []
    labels: list[str] = []
    unresolved_labels = {"", "미분류", "미분석", "unknown", "unanalyzed", "unclassified"}
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        status = str(attachment.get("parse_status") or "").strip().casefold()
        statuses.append(status)
        label = str(attachment.get("document_category_label") or attachment.get("document_type") or "").strip()
        if label:
            labels.append(label)
    if not statuses:
        return ops_stage("not_started", f"{count}개 미분석", "pending", "첨부파일 분석 결과가 없습니다.")
    if any(status in {"failed", "error"} for status in statuses):
        return ops_stage("failed", f"{count}개 중 실패", "error", ", ".join(labels[:2]) or "분석 실패")
    if any(status in {"pending", "queued"} for status in statuses):
        return ops_stage("queued", f"{count}개 대기", "schedule", ", ".join(labels[:2]) or "분석 대기")
    if any(status in {"running", "processing"} for status in statuses):
        return ops_stage("running", f"{count}개 분석중", "progress_activity", ", ".join(labels[:2]) or "분석 중")
    if any(status in {"", "unknown", "downloaded", "received"} for status in statuses) or not labels or any(
        label.strip().casefold() in unresolved_labels for label in labels
    ):
        return ops_stage("not_started", f"{count}개 미분류", "pending", "문서 유형 분류가 완료되지 않았습니다.")
    if not all(status in {"completed", "partial_success", "success"} for status in statuses):
        return ops_stage("not_started", f"{count}개 미분석", "pending", "첨부파일 분석 결과가 없습니다.")
    return ops_stage("completed", f"{count}개 완료", "task_alt", ", ".join(labels[:2]) or "문서 유형 분류 완료")


def ops_summary_stage(
    row: dict[str, object],
    detail: dict[str, object],
    classification: dict[str, object],
) -> dict[str, object]:
    state = str(row.get("summary_state") or "").strip()
    label = str(row.get("summary_state_label") or "").strip()
    if not state:
        if detail.get("executive_summary_sections") or detail.get("summary") or classification.get("summary"):
            state = "completed"
            label = "완료"
        elif str(row.get("summary_result_status") or "") in {"pending", "processing", "failed"}:
            state = {"pending": "queued", "processing": "running", "failed": "failed"}[str(row.get("summary_result_status"))]
        else:
            state = "not_started"
    return ops_stage(
        state,
        label or mail_decision_status_label(state),
        ops_stage_icon(state),
        ops_summary_status_detail(state),
    )


def ops_summary_status_detail(state: str) -> str:
    return {
        "completed": "요약문 생성 완료",
        "queued": "요약문 생성 대기",
        "running": "요약문 생성 중",
        "failed": "요약문 생성 실패",
    }.get(state, "요약문 결과 없음")


def ops_classification_stage(row: dict[str, object]) -> dict[str, object]:
    state = str(row.get("classification_state") or "unclassified")
    normalized = {
        "success": "completed",
        "unclassified": "not_started",
    }.get(state, state)
    label = str(row.get("classification_state_label") or "")
    if normalized == "completed" and label.strip().casefold() == "db":
        label = "완료"
    category = str(row.get("business_label") or row.get("mail_category") or "")
    return ops_stage(normalized, label or mail_decision_status_label(normalized), ops_stage_icon(normalized), category or "분류 결과 없음")


def ops_decision_stage(row: dict[str, object]) -> dict[str, object]:
    status = str(row.get("mail_decision_status") or "").strip()
    if not status:
        return ops_stage("not_started", "미실행", "pending", "Mail Decision Run이 아직 없습니다.")
    if status == "review_required" and _has_confirmed_or_forwarded_routing(row):
        return ops_stage("completed", "완료", "task_alt", "담당자 또는 전달 확정 상태가 유지되었습니다.")
    return ops_stage(status, mail_decision_status_label(status), ops_stage_icon(status), "최신 Mail Decision Run 상태")


def ops_routing_stage(row: dict[str, object]) -> dict[str, object]:
    work_status = str(row.get("work_status") or "")
    routing_status = str(row.get("routing_status") or "")
    assignee = receiver_display_text(row.get("assignee_name") or row.get("routing_display"))
    if assignee and assignee != UNASSIGNED_ROUTING_LABEL:
        return ops_stage("completed", "배정 완료", ops_stage_icon("completed"), assignee)
    if work_status == "review_required" or routing_status == "review_required":
        return ops_stage("review_required", "검토 필요", ops_stage_icon("review_required"), assignee)
    return ops_stage("not_started", "미할당", ops_stage_icon("not_started"), "담당자 후보 또는 확정 담당자가 없습니다.")


def ops_forwarding_stage(row: dict[str, object]) -> dict[str, object]:
    manual_status = str(row.get("manual_route_status") or "")
    if manual_status == "sent" or _is_forwarded_row(row):
        return ops_stage("completed", "전달 완료", ops_stage_icon("completed"), str(row.get("manual_route_status_label") or "전달 완료"))
    if manual_status == "pending":
        return ops_stage("running", "전달 중", ops_stage_icon("running"), "수동 전달 작업 진행 중")
    if manual_status == "failed":
        return ops_stage("failed", "전달 실패", ops_stage_icon("failed"), str(row.get("manual_route_error") or "전달 실패"))
    if str(row.get("assignee_email") or ""):
        return ops_stage("not_started", "미전달", ops_stage_icon("not_started"), str(row.get("assignee_email") or "담당자 이메일 있음"))
    return ops_stage("skipped", "대기", ops_stage_icon("skipped"), "담당자 확정 후 전달할 수 있습니다.")


def ops_stage(state: str, label: str, icon: str, detail: str) -> dict[str, str]:
    normalized = {
        "success": "completed",
        "processing": "running",
        "pending": "queued",
        "unclassified": "not_started",
    }.get(state, state or "not_started")
    return {
        "state": normalized,
        "label": label or mail_decision_status_label(normalized),
        "icon": icon or ops_stage_icon(normalized),
        "detail": detail or "-",
        "class": mail_decision_status_class(normalized),
    }


def ops_stage_icon(state: str) -> str:
    return {
        "completed": "task_alt",
        "skipped": "remove_done",
        "queued": "schedule",
        "running": "progress_activity",
        "review_required": "rate_review",
        "auto_assigned": "assignment_turned_in",
        "assigned": "assignment_turned_in",
        "forwarded": "forward_to_inbox",
        "failed": "error",
        "not_started": "pending",
    }.get(state, "pending")


def ops_stage_weight(state: str) -> float:
    return {
        "completed": 1.0,
        "skipped": 1.0,
        "auto_assigned": 1.0,
        "assigned": 1.0,
        "forwarded": 1.0,
        "review_required": 0.66,
        "running": 0.5,
        "queued": 0.25,
        "not_started": 0.0,
        "failed": 0.0,
    }.get(state, 0.0)


def dashboard_rows_for_request(
    request: Request | None,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    username = current_request_username(request)
    if user_can_view_all_assignees(username):
        return rows_with_current_user_read_state(request, rows)
    return rows_with_current_user_read_state(request, visible_work_rows_for_request(request, rows))


def dashboard_context(request: Request | None = None, *, status: str = "") -> dict[str, object]:
    rows = dashboard_rows_for_request(request, mail_rows())
    selected_status = status.strip()
    email_rows = [row for row in rows if status_matches_work_filter(row, selected_status)]
    summary = dashboard_summary(rows)
    my_work_aging_summary = my_work_aging(rows)
    reference_day = _dashboard_reference_date(rows)
    username = current_request_username(request)
    scoped_to_assignee = request is not None and not user_can_view_all_assignees(username)
    globals_context = ui_globals(request)
    dashboard_scope_label = str(globals_context.get("current_user") or username)
    if demo_mode_enabled():
        today_rows = _dashboard_rows_on_day(rows, reference_day)
        return {
            **globals_context,
            "summary": summary,
            "emails": email_rows,
            "mail_rows_mode": "dashboard",
            "dashboard_reference_day": reference_day.isoformat(),
            "selected_work_status": selected_status,
            "category_distribution": dashboard_summary(today_rows),
            "category_distribution_all": summary,
            "category_timeline": category_timeline(rows),
            "routing_overview": routing_overview(today_rows),
            "routing_overview_all": routing_overview(rows),
            "my_work_aging": my_work_aging_summary,
            "dashboard_scope_toggle_enabled": not scoped_to_assignee,
            "dashboard_work_scope": scoped_to_assignee,
            "dashboard_scope_label": dashboard_scope_label,
        }
    return {
        **globals_context,
        "summary": summary,
        "emails": email_rows,
        "mail_rows_mode": "dashboard",
        "dashboard_reference_day": reference_day.isoformat(),
        "selected_work_status": selected_status,
        "category_timeline": category_timeline(rows),
        "routing_overview": routing_overview(rows),
        "my_work_aging": my_work_aging_summary,
        "dashboard_work_scope": scoped_to_assignee,
        "dashboard_scope_label": dashboard_scope_label,
        "dashboard_scope_toggle_enabled": False,
    }


def dashboard_summary(rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    rows = rows if rows is not None else mail_rows()
    categories = Counter(str(row.get("mail_category") or "미분류") for row in rows)
    attention_counts = Counter(_attention_quadrant_for_row(row) for row in rows)
    today = _dashboard_reference_date(rows)
    today_count = 0
    today_urgent_count = 0
    for row in rows:
        parsed = _parse_datetime(str(row.get("date") or row.get("received_at") or ""))
        if parsed and _display_datetime(parsed).date() == today:
            today_count += 1
            if _is_priority_high_row(row):
                today_urgent_count += 1
    classified_count = sum(1 for row in rows if _is_classified_row(row))
    routed_count = sum(1 for row in rows if _is_routed_row(row))
    forwarded_count = sum(1 for row in rows if _is_forwarded_row(row))
    urgent_count = sum(1 for row in rows if _is_priority_high_row(row))
    assigned_count = sum(1 for row in rows if str(row.get("work_status") or "") == "assigned")
    acknowledged_count = sum(1 for row in rows if str(row.get("work_status") or "") == "acknowledged")
    in_progress_count = sum(1 for row in rows if str(row.get("work_status") or "") == "in_progress")
    responded_count = sum(1 for row in rows if str(row.get("work_status") or "") == "responded")
    completed_count = sum(1 for row in rows if str(row.get("work_status") or "") == "completed")
    return {
        "email_count": len(rows),
        "today_email_count": today_count,
        "urgent_count": urgent_count,
        "today_urgent_count": today_urgent_count,
        "attention_urgent_important_count": attention_counts["urgent_important"],
        "attention_urgent_count": attention_counts["urgent"],
        "attention_important_count": attention_counts["important"],
        "attention_normal_count": attention_counts["normal"],
        "classified_count": classified_count,
        "unclassified_count": len(rows) - classified_count,
        "routed_count": routed_count,
        "unrouted_count": len(rows) - routed_count,
        "forwarded_count": forwarded_count,
        "unforwarded_count": len(rows) - forwarded_count,
        "assigned_work_count": assigned_count,
        "acknowledged_work_count": acknowledged_count,
        "in_progress_work_count": in_progress_count,
        "responded_work_count": responded_count,
        "completed_work_count": completed_count,
        "overdue_work_count": sum(1 for row in rows if _is_overdue_work_row(row)),
        "completed_today_work_count": sum(1 for row in rows if _is_completed_today_work_row(row)),
        "attachment_count": sum(int(row.get("attachment_count") or 0) for row in rows),
        "mail_categories": dict(categories),
        "business_labels": dict(categories),
    }


def _is_priority_high_row(row: dict[str, object]) -> bool:
    urgency = _urgency_for_row(row)
    if urgency in {"high", "normal"}:
        return urgency == "high"
    return _attention_quadrant_for_row(row) in {"urgent_important", "urgent"}


def _urgency_for_row(row: dict[str, object]) -> str:
    classification = row.get("classification")
    classification_payload = classification if isinstance(classification, dict) else {}
    for payload in (row.get("urgency"), classification_payload.get("urgency")):
        if isinstance(payload, dict):
            value = str(payload.get("level") or "").strip()
        else:
            value = str(payload or "").strip()
        if value in {"high", "normal"}:
            return value
    return ""


def _attention_quadrant_for_row(row: dict[str, object]) -> str:
    classification = row.get("classification")
    classification_payload = classification if isinstance(classification, dict) else {}
    attention_quadrant = str(
        row.get("attention_quadrant") or classification_payload.get("attention_quadrant") or ""
    ).strip()
    if attention_quadrant in {"urgent_important", "urgent", "important", "normal"}:
        return attention_quadrant
    return "normal"


def _is_classified_row(row: dict[str, object]) -> bool:
    category = str(row.get("mail_category") or row.get("business_label") or "").strip()
    state = str(row.get("classification_state") or "").strip()
    if not category or category == "미분류":
        return False
    return state in {"completed", "success"} or bool(row.get("classification"))


def _is_routed_row(row: dict[str, object]) -> bool:
    routing_display = str(row.get("routing_display") or "").strip()
    routing_status = str(row.get("routing_status") or "").strip()
    if routing_display in UNROUTED_LABELS:
        return False
    if row.get("assignee_name") or row.get("assignee_email"):
        return True
    if routing_status in {"assigned", "forwarded", "completed"}:
        return True
    return routing_display not in UNROUTED_LABELS


def _has_confirmed_or_forwarded_routing(row: dict[str, object]) -> bool:
    if _is_forwarded_row(row):
        return True
    routing_status = str(row.get("routing_status") or "").strip()
    if routing_status in {"assigned", "completed", "auto_assigned"}:
        return True
    return bool(row.get("assignee_name") or row.get("assignee_email") or row.get("assignee_user_id"))


def _is_forwarded_row(row: dict[str, object]) -> bool:
    return (
        str(row.get("work_status") or "").strip() == "forwarded"
        or str(row.get("work_status_label") or "").strip() == "전달 완료"
        or str(row.get("routing_status") or "").strip() == "forwarded"
        or bool(row.get("routing_forwarded_at"))
        or str(row.get("manual_route_status") or "").strip() == "sent"
        or str(row.get("manual_route_status_label") or "").strip() == "전달 완료"
        or bool(row.get("manual_route_sent_at"))
    )


def category_timeline(rows: list[dict[str, object]], today: date | None = None) -> dict[str, object]:
    categories = mail_service().category_order()
    today = today or _dashboard_reference_date(rows)
    day_labels = [(today - timedelta(days=offset)).strftime("%m-%d") for offset in range(6, -1, -1)]
    visible_labels = set(day_labels)
    by_day: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        parsed = _parse_datetime(str(row.get("date") or row.get("received_at") or ""))
        if parsed is None:
            continue
        label = _display_datetime(parsed).strftime("%m-%d")
        if label not in visible_labels:
            continue
        by_day[label][str(row.get("mail_category") or "미분류")] += 1
    return {
        "labels": day_labels,
        "datasets": {category: [by_day[label].get(category, 0) for label in day_labels] for category in categories},
    }


def _dashboard_reference_date(rows: list[dict[str, object]]) -> date:
    current_day = datetime.now(DISPLAY_TIMEZONE).date()
    if not demo_mode_enabled():
        return current_day
    row_days = [
        _display_datetime(parsed).date()
        for row in rows
        if (parsed := _parse_datetime(str(row.get("date") or row.get("received_at") or ""))) is not None
    ]
    return max(row_days, default=current_day)


def _dashboard_rows_on_day(rows: list[dict[str, object]], target_day: date) -> list[dict[str, object]]:
    selected_rows = []
    for row in rows:
        parsed = _parse_datetime(str(row.get("date") or row.get("received_at") or ""))
        if parsed and _display_datetime(parsed).date() == target_day:
            selected_rows.append(row)
    return selected_rows


def my_work_aging(rows: list[dict[str, object]]) -> dict[str, object]:
    today = datetime.now(DISPLAY_TIMEZONE).date()
    active_rows = [row for row in rows if not _is_terminal_work_row(row)]
    bucket_specs = [
        ("overdue", "기한 초과"),
        ("today", "오늘 수신"),
        ("one_day", "1일 경과"),
        ("two_three_days", "2-3일 경과"),
        ("older", "4일 이상"),
    ]
    counts = {key: 0 for key, _ in bucket_specs}
    for row in active_rows:
        if _is_overdue_work_row(row):
            counts["overdue"] += 1
            continue
        parsed = _parse_datetime(str(row.get("date") or row.get("received_at") or ""))
        received_day = _display_datetime(parsed).date() if parsed else today
        age_days = max(0, (today - received_day).days)
        if age_days == 0:
            counts["today"] += 1
        elif age_days == 1:
            counts["one_day"] += 1
        elif age_days <= 3:
            counts["two_three_days"] += 1
        else:
            counts["older"] += 1
    max_count = max(counts.values(), default=0)
    buckets = [
        {
            "key": key,
            "label": label,
            "count": counts[key],
            "bar_percent": round(counts[key] / max_count * 100) if max_count else 0,
            "bar_display_percent": max(2, round(counts[key] / max_count * 100)) if counts[key] and max_count else 0,
            "share_percent": round(counts[key] / len(active_rows) * 100) if active_rows else 0,
            "share_display_percent": max(3, round(counts[key] / len(active_rows) * 100)) if counts[key] and active_rows else 0,
        }
        for key, label in bucket_specs
    ]
    return {
        "total": len(rows),
        "active_count": len(active_rows),
        "completed_count": sum(1 for row in rows if str(row.get("work_status") or "") == "completed"),
        "completed_today_count": sum(1 for row in rows if _is_completed_today_work_row(row)),
        "overdue_count": counts["overdue"],
        "buckets": buckets,
    }


def _is_terminal_work_row(row: dict[str, object]) -> bool:
    return str(row.get("work_status") or "").strip() in {
        "completed",
        "responded",
        "failed",
        "cancelled",
    }


def routing_overview(rows: list[dict[str, object]]) -> dict[str, object]:
    counts = Counter(_assignee_display_name(row) for row in rows)
    total = len(rows)
    assigned = sum(1 for row in rows if _is_routed_row(row))
    labels = list(counts.keys())
    palette = category_chart_palette(labels)
    assigned_counts = sorted(
        ((label, count) for label, count in counts.items() if label not in UNROUTED_LABELS),
        key=lambda item: (-item[1], item[0]),
    )
    max_assigned_count = max((count for _, count in assigned_counts), default=1)
    return {
        "total": total,
        "loaded_count": assigned,
        "loaded_percent": round(assigned / total * 100) if total else 0,
        "unassigned_count": counts.get(UNASSIGNED_ROUTING_LABEL, 0),
        "unassigned_percent": round(counts.get(UNASSIGNED_ROUTING_LABEL, 0) / total * 100) if total else 0,
        "assignee_labels": labels,
        "assignee_counts": [counts[label] for label in labels],
        "route_palette": palette,
        "workload_assignees": [
            {
                "label": label,
                "count": count,
                "bar_percent": round(count / max_assigned_count * 100),
                "bar_display_percent": max(2, round(count / max_assigned_count * 100)),
            }
            for label, count in assigned_counts
        ],
    }


def search_context(query: str = "", limit: int = 5) -> dict[str, object]:
    normalized_query = normalize_search_query(query)
    result = mail_search_service().search(normalized_query, limit=limit) if normalized_query else None
    return {
        **ui_globals(),
        "query": normalized_query,
        "limit": limit,
        "result": result,
        "error": "",
        "loading": False,
        "answer": str((result or {}).get("answer") or ""),
    }


def chats_context(query: str = "", limit: int = 5, session_id: str = "") -> dict[str, object]:
    context = _mail_chat_service.session_context(session_id)
    normalized_query = normalize_search_query(query)
    if normalized_query:
        context = _mail_chat_service.ask(
            session_id=str(context["session_id"]),
            query=normalized_query,
            search_service=mail_search_service(),
            limit=limit,
        )
    return {
        **ui_globals(),
        "query": normalized_query,
        "limit": limit,
        "loading": False,
        **context,
        "include_session_oob": False,
    }


def address_book_context(q: str = "", organization: str = "") -> dict[str, object]:
    try:
        rows = mail_service().list_emails()
    except Exception as exc:
        if not _mail_store_fallback_error(exc):
            raise
        logger.warning("mail store unavailable; falling back to demo address book: %s", exc)
        rows = demo_service().list_emails()
    return {
        **ui_globals(),
        **address_book_view(rows, query=q, organization=organization),
    }


def settings_context() -> dict[str, object]:
    categories = BUSINESS_CATEGORY_ORDER
    operating_assignees = (
        _postgres_assignee_admin_repository.list_operating_assignees()
        if database_url()
        else []
    )
    synthetic_assignees = (
        _postgres_assignee_admin_repository.list_active_synthetic_assignees()
        if database_url()
        else []
    )
    assignees = [*operating_assignees, *synthetic_assignees]
    route_assignments = []
    for category in categories:
        matched = [
            assignee
            for assignee in operating_assignees
            if category in (assignee.get("mail_categories") or assignee.get("business_labels") or [])
        ]
        matched.sort(
            key=lambda assignee: (
                (assignee.get("category_priorities") or {}).get(category, 100),
                str(assignee.get("assignee_name") or ""),
                str(assignee.get("assignee_id") or ""),
            )
        )
        route_assignments.append(
            {
                "label": category,
                "assignees": matched,
                "active_assignee_count": sum(1 for assignee in matched if assignee.get("is_active")),
            }
        )
    return {
        **ui_globals(),
        "gmail_sync": active_mail_public_status(),
        "gmail_settings_message": "",
        "gmail_settings_error": "",
        "routing_policy": _postgres_routing_policy_settings_repository.get(),
        "routing_policy_message": "",
        "routing_policy_error": "",
        "category_order": categories,
        "assignees": assignees,
        "operating_assignee_count": len(operating_assignees),
        "synthetic_assignee_count": len(synthetic_assignees),
        "demo_duplicate_mail_enabled": demo_mode_enabled() and postgres_demo_source_enabled() and bool(database_url()),
        "route_assignments": route_assignments,
        "routing_table_options": {"mail_categories": categories, "business_labels": categories},
    }


def duplicate_latest_demo_mail_for_review() -> str:
    db_url = database_url()
    if not db_url or not postgres_demo_source_enabled():
        raise HTTPException(status_code=400, detail="PostgreSQL demo source is required.")

    import psycopg
    from psycopg.rows import dict_row

    source_sql = """
        SELECT m.id, m.sent_at
        FROM email_messages m
        JOIN email_accounts account ON account.id = m.email_account_id
        WHERE m.deleted_at IS NULL
          AND account.provider = 'synthetic'
          AND m.provider_message_id NOT LIKE 'demo-duplicate-latest-%'
        ORDER BY m.sent_at DESC, m.created_at DESC
        LIMIT 1
    """
    new_email_uid = str(uuid4())
    provider_message_id = f"demo-duplicate-latest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"
    created_at = datetime.now(timezone.utc)

    with psycopg.connect(db_url, row_factory=dict_row) as conn:
        with conn.transaction():
            with conn.cursor() as cursor:
                cursor.execute(source_sql)
                source = cursor.fetchone()
                if source is None:
                    raise HTTPException(status_code=404, detail="No source demo mail is available.")
                source_email_uid = str(source["id"])
                source_sent_at = source.get("sent_at")
                demo_received_at = (
                    source_sent_at + timedelta(minutes=1)
                    if isinstance(source_sent_at, datetime)
                    else datetime(2026, 8, 12, 0, 25, tzinfo=timezone.utc)
                )

                cursor.execute(
                    """
                    INSERT INTO email_messages (
                        id, email_account_id, provider_message_id, provider_thread_id, rfc_message_id,
                        in_reply_to, "references", sender_name, sender_address, subject, subject_normalized,
                        body_text, body_html, snippet, sent_at, received_at, has_attachment, attachment_count,
                        processing_status, content_hash, created_at, updated_at, deleted_at
                    )
                    SELECT
                        %(new_email_uid)s::uuid,
                        email_account_id,
                        %(provider_message_id)s,
                        %(provider_thread_id)s,
                        %(rfc_message_id)s,
                        in_reply_to,
                        "references",
                        sender_name,
                        sender_address,
                        subject,
                        subject_normalized,
                        body_text,
                        body_html,
                        snippet,
                        %(demo_received_at)s,
                        %(demo_received_at)s,
                        has_attachment,
                        attachment_count,
                        'received',
                        content_hash,
                        %(created_at)s,
                        %(created_at)s,
                        NULL
                    FROM email_messages
                    WHERE id = %(source_email_uid)s::uuid
                    """,
                    {
                        "new_email_uid": new_email_uid,
                        "provider_message_id": provider_message_id,
                        "provider_thread_id": f"thread-{provider_message_id}",
                        "rfc_message_id": f"<{provider_message_id}@coramail.local>",
                        "demo_received_at": demo_received_at,
                        "created_at": created_at,
                        "source_email_uid": source_email_uid,
                    },
                )
                cursor.execute(
                    """
                    INSERT INTO email_recipients (id, email_message_id, recipient_type, name, address, created_at)
                    SELECT gen_random_uuid(), %(new_email_uid)s::uuid, recipient_type, name, address, %(created_at)s
                    FROM email_recipients
                    WHERE email_message_id = %(source_email_uid)s::uuid
                    """,
                    {"new_email_uid": new_email_uid, "created_at": created_at, "source_email_uid": source_email_uid},
                )

                cursor.execute(
                    """
                    SELECT id
                    FROM email_attachments
                    WHERE email_message_id = %(source_email_uid)s::uuid
                    ORDER BY filename, id
                    """,
                    {"source_email_uid": source_email_uid},
                )
                for attachment in cursor.fetchall():
                    new_attachment_id = str(uuid4())
                    cursor.execute(
                        """
                        INSERT INTO email_attachments (
                            id, email_message_id, provider_attachment_id, filename, storage_uri, content_type,
                            file_group, file_size, checksum, is_inline, document_category_id, processing_status,
                            parse_error, created_at, updated_at, deleted_at, content_id, content_disposition
                        )
                        SELECT
                            %(new_attachment_id)s::uuid,
                            %(new_email_uid)s::uuid,
                            provider_attachment_id,
                            filename,
                            storage_uri,
                            content_type,
                            file_group,
                            file_size,
                            checksum,
                            is_inline,
                            document_category_id,
                            CASE WHEN storage_uri = '' THEN processing_status ELSE 'downloaded' END,
                            parse_error,
                            %(created_at)s,
                            %(created_at)s,
                            NULL,
                            content_id,
                            content_disposition
                        FROM email_attachments
                        WHERE id = %(source_attachment_id)s::uuid
                        """,
                        {
                            "new_attachment_id": new_attachment_id,
                            "new_email_uid": new_email_uid,
                            "created_at": created_at,
                            "source_attachment_id": str(attachment["id"]),
                        },
                    )
                cursor.execute(
                    """
                    INSERT INTO processing_jobs (
                        id, job_type, source_type, source_id, status, attempt_count, max_attempts,
                        scheduled_at, started_at, completed_at, error_message, metadata,
                        created_at, updated_at
                    )
                    VALUES (
                        gen_random_uuid(),
                        'email_analysis',
                        'email',
                        %(new_email_uid)s::uuid,
                        'pending',
                        0,
                        3,
                        %(created_at)s,
                        NULL,
                        NULL,
                        NULL,
                        jsonb_build_object(
                            'analysis_type', 'mail_decision',
                            'requested_by', 'demo-receive-latest-duplicate',
                            'request_source', 'coramail_agent',
                            'pipeline_version', 'actual-mail-decision-v1',
                            'duplicate_verification_source_email_uid', %(source_email_uid)s::text
                        ),
                        %(created_at)s,
                        %(created_at)s
                    )
                    """,
                    {"new_email_uid": new_email_uid, "source_email_uid": source_email_uid, "created_at": created_at},
                )
    return new_email_uid


def _start_received_demo_mail_processing(email_uid: str) -> None:
    job_id = _received_demo_mail_decision_job_id(email_uid)
    if job_id is None:
        logger.warning("No pending mail decision job found for received demo mail %s", email_uid)
        return

    def run_worker() -> None:
        try:
            _postgres_email_analysis_worker.run_one(job_id)
        except Exception:
            logger.exception("Failed to process received demo mail %s", email_uid)

    Thread(target=run_worker, name=f"demo-mail-decision-{email_uid}", daemon=True).start()


def _received_demo_mail_decision_job_id(email_uid: str) -> str | None:
    db_url = database_url()
    if not db_url:
        return None

    import psycopg

    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id
                FROM processing_jobs
                WHERE job_type = 'email_analysis'
                  AND source_type = 'email'
                  AND source_id = %(email_uid)s::uuid
                  AND status = 'pending'
                  AND metadata ->> 'analysis_type' = 'mail_decision'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                {"email_uid": email_uid},
            )
            row = cursor.fetchone()
            return str(row[0]) if row is not None else None


def routing_table_response(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "partials/routing_table.html",
        {**settings_context(), "request": request},
    )


def related_emails(email: dict[str, object]) -> list[dict[str, object]]:
    classification = email.get("classification") if isinstance(email.get("classification"), dict) else {}
    refs = {str(ref) for ref in classification.get("business_refs", [])}
    uid = str(email.get("email_uid") or "")
    related = []
    for row in mail_rows():
        row_classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
        if str(row.get("email_uid") or "") == uid:
            continue
        if refs.intersection(str(ref) for ref in row_classification.get("business_refs", [])):
            related.append(row)
    return related[:5]

def _settings_handlers() -> SettingsHandlers:
    return SettingsHandlers(
        render_view=render_view,
        settings_context=settings_context,
        render_gmail_sync_settings=render_gmail_sync_settings,
        parse_form=_urlencoded_form,
        gmail_account_repository=_gmail_account_repository,
        gmail_oauth_service=_gmail_oauth_service,
        gmail_callback_redirect=_gmail_callback_redirect,
        gmail_service=_gmail_service,
        active_mail_provider=active_mail_provider,
        active_provider_label=active_provider_label,
        active_provider_service=active_provider_service,
        active_mail_public_status=active_mail_public_status,
        request_demo_mode=request_demo_mode,
        duplicate_latest_demo_mail=duplicate_latest_demo_mail_for_review,
        start_received_demo_mail_processing=_start_received_demo_mail_processing,
        display_mode_cookie_name=DISPLAY_MODE_COOKIE_NAME,
        gmail_oauth_state_cookie_name=GMAIL_OAUTH_STATE_COOKIE_NAME,
        auth_cookie_secure=AUTH_COOKIE_SECURE,
        templates=templates,
        render_auto_assignment_policy=render_auto_assignment_policy,
        demo_mode_enabled=demo_mode_enabled,
        logger=logger,
        assignee_admin_repository=_postgres_assignee_admin_repository,
        routing_table_response=routing_table_response,
        routing_policy_settings_repository=_postgres_routing_policy_settings_repository,
    )


app.include_router(
    build_server_route_router(
        {
            "auto_sync_status": auto_sync_status,
            "demo_email_attachment": demo_email_attachment,
            "gmail_oauth_callback": gmail_oauth_callback,
            "login_form": login_form,
            "login_submit": login_submit,
            "logout_submit": logout_submit,
            "ui_auto_assignment_policy": ui_auto_assignment_policy,
            "ui_auto_sync_run": ui_auto_sync_run,
            "ui_chats": ui_chats,
            "ui_chat_email_drawer": ui_chat_email_drawer,
            "ui_chats_results": ui_chats_results,
            "ui_confirm_top_review_candidate": ui_confirm_top_review_candidate,
            "ui_create_mail_decision_run": ui_create_mail_decision_run,
            "ui_display_mode_toggle": ui_display_mode_toggle,
            "ui_email_attachments_reanalyze": ui_email_attachments_reanalyze,
            "ui_email_classification_regenerate": ui_email_classification_regenerate,
            "ui_email_summary_regenerate": ui_email_summary_regenerate,
            "ui_evaluation": ui_evaluation,
            "ui_evaluation_case": ui_evaluation_case,
            "ui_evaluation_case_trace": ui_evaluation_case_trace,
            "ui_gmail_connect": ui_gmail_connect,
            "ui_gmail_disconnect": ui_gmail_disconnect,
            "ui_gmail_settings_sync": ui_gmail_settings_sync,
            "ui_gmail_settings_sync_outbound": ui_gmail_settings_sync_outbound,
            "ui_gmail_sync_settings": ui_gmail_sync_settings,
            "ui_hiworks_settings_sync": ui_hiworks_settings_sync,
            "ui_hiworks_sync_settings": ui_hiworks_sync_settings,
            "ui_latest_mail_decision_run": ui_latest_mail_decision_run,
            "ui_mail_decision_run": ui_mail_decision_run,
            "ui_mail_decision_steps": ui_mail_decision_steps,
            "ui_manual_assign_review_email": ui_manual_assign_review_email,
            "ui_my_work_email_drawer": ui_my_work_email_drawer,
            "ui_naver_settings_sync": ui_naver_settings_sync,
            "ui_naver_sync_settings": ui_naver_sync_settings,
            "ui_receive_latest_duplicate_demo_mail": ui_receive_latest_duplicate_demo_mail,
            "ui_root": ui_root,
            "ui_route_email_manual": ui_route_email_manual,
            "ui_routing_summary": ui_routing_summary,
            "ui_routing_table": ui_routing_table,
            "ui_save_gmail_client_config": ui_save_gmail_client_config,
            "ui_save_gmail_tokens": ui_save_gmail_tokens,
            "ui_search": ui_search,
            "ui_search_results": ui_search_results,
            "ui_settings": ui_settings,
            "ui_settings_auto_assignment_policy": ui_settings_auto_assignment_policy,
            "ui_settings_create_assignee": ui_settings_create_assignee,
            "ui_settings_deactivate_assignee": ui_settings_deactivate_assignee,
            "ui_settings_delete_assignee": ui_settings_delete_assignee,
            "ui_settings_routing_reorder": ui_settings_routing_reorder,
            "ui_settings_toggle_assignee": ui_settings_toggle_assignee,
            "ui_settings_update_assignee": ui_settings_update_assignee,
            "ui_trash_email": ui_trash_email,
            "ui_work_complete": ui_work_complete,
            "ui_work_in_progress_toggle": ui_work_in_progress_toggle,
            "ui_work_reply_initiate": ui_work_reply_initiate,
        }
    )
)


app.include_router(
    build_jobs_router(
        jobs_enabled=postgres_jobs_enabled,
        list_jobs=_postgres_job_repository.list_jobs,
        job_by_id=_postgres_job_repository.job_by_id,
        run_pending=_postgres_email_analysis_worker.run_pending,
        public_job=_public_job,
    )
)

app.include_router(
    build_mail_query_router(
        dashboard_summary=dashboard_summary,
        mail_rows=mail_rows,
        email_detail=_email_detail_by_ref,
        jobs_enabled=postgres_jobs_enabled,
        jobs_for_email=_postgres_job_repository.jobs_for_email,
        public_job=_public_job,
    )
)

app.include_router(build_search_router(search_service=mail_search_service))

app.include_router(
    build_mail_analysis_router(
        process_analysis_job=_require_processed_email_analysis_job,
        reanalyze_attachments=_reanalyze_email_attachments_guarded,
        email_detail=_email_detail_by_ref,
        public_job=_public_job,
    )
)

app.include_router(build_manual_routing_router(manual_assign=_manual_assign_review_email))

app.include_router(build_attachment_router(resolve_attachment=_attachment_path_by_ref))

app.include_router(build_demo_noop_router())

app.include_router(
    build_dashboard_ui_router(
        render_view=render_view,
        dashboard_context=dashboard_context,
        templates=templates,
    )
)

app.include_router(
    build_inbox_ui_router(
        mail_rows=mail_rows,
        status_matches=status_matches_work_filter,
        resolve_selected_index=_resolve_selected_index,
        visible_rows=visible_work_rows_for_request,
        inbox_context=inbox_context,
        render_view=render_view,
    )
)

app.include_router(
    build_work_ui_router(
        assignee_work_context=assignee_work_context,
        render_view=render_view,
    )
)

app.include_router(
    build_monitoring_ui_router(
        ops_console_context=ops_console_context,
        render_view=render_view,
        templates=templates,
        email_detail=_email_detail_by_ref,
        ensure_can_view=ensure_can_view_work_email,
        ui_globals=ui_globals,
        related_emails=related_emails,
    )
)

app.include_router(
    build_documents_ui_router(
        document_types_context=document_types_context,
        render_view=render_view,
        templates=templates,
    )
)

app.include_router(
    build_address_book_ui_router(
        address_book_context=address_book_context,
        render_view=render_view,
        templates=templates,
    )
)

app.include_router(
    build_mail_display_ui_router(
        parse_form=_urlencoded_form,
        mail_rows=mail_rows,
        dashboard_rows=dashboard_rows_for_request,
        visible_rows=visible_work_rows_for_request,
        status_matches=status_matches_work_filter,
        dashboard_reference_date=_dashboard_reference_date,
        ui_globals=ui_globals,
        templates=templates,
        email_detail=_email_detail_by_ref,
        ensure_can_view=ensure_can_view_work_email,
        mark_mail_read=_mark_mail_read_for_current_user,
        related_emails=related_emails,
    )
)
