from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


Endpoint = Callable[..., Any]
EndpointMap = Mapping[str, Endpoint]


def build_server_route_router(endpoints: EndpointMap) -> APIRouter:
    router = APIRouter()

    def endpoint(name: str) -> Endpoint:
        try:
            return endpoints[name]
        except KeyError as exc:  # pragma: no cover - composition guard
            raise RuntimeError(f"missing server route endpoint: {name}") from exc

    router.add_api_route("/login", endpoint("login_form"), methods=["GET"], response_class=HTMLResponse)
    router.add_api_route("/login", endpoint("login_submit"), methods=["POST"], response_class=HTMLResponse)
    router.add_api_route("/logout", endpoint("logout_submit"), methods=["POST"])
    router.add_api_route("/", endpoint("react_shell"), methods=["GET"], response_class=HTMLResponse)
    router.add_api_route("/react", endpoint("react_shell"), methods=["GET"], response_class=HTMLResponse)
    router.add_api_route("/legacy", endpoint("ui_root"), methods=["GET"], response_class=HTMLResponse)

    router.add_api_route(
        "/ui/my-work/emails/{email_ref}",
        endpoint("ui_my_work_email_drawer"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/work/reply-initiate",
        endpoint("ui_work_reply_initiate"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/work/in-progress",
        endpoint("ui_work_in_progress_toggle"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/work/complete",
        endpoint("ui_work_complete"),
        methods=["POST"],
    )

    router.add_api_route(
        "/ui/emails/{email_ref}/mail-decision-runs",
        endpoint("ui_create_mail_decision_run"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/mail-decision-runs/latest",
        endpoint("ui_latest_mail_decision_run"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/mail-decision-runs/{run_id}",
        endpoint("ui_mail_decision_run"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/mail-decision-runs/{run_id}/steps",
        endpoint("ui_mail_decision_steps"),
        methods=["GET"],
        response_class=HTMLResponse,
    )

    router.add_api_route("/ui/evaluation", endpoint("ui_evaluation"), methods=["GET"], response_class=HTMLResponse)
    router.add_api_route(
        "/ui/evaluation/cases/{email_message_id}",
        endpoint("ui_evaluation_case"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/evaluation/cases/{email_message_id}/trace",
        endpoint("ui_evaluation_case_trace"),
        methods=["GET"],
        response_class=HTMLResponse,
    )

    router.add_api_route("/ui/search", endpoint("ui_search"), methods=["GET"], response_class=HTMLResponse)
    router.add_api_route("/ui/search", endpoint("ui_search"), methods=["POST"], response_class=HTMLResponse)
    router.add_api_route(
        "/ui/search-results", endpoint("ui_search_results"), methods=["GET"], response_class=HTMLResponse
    )
    router.add_api_route("/ui/chats", endpoint("ui_chats"), methods=["GET"], response_class=HTMLResponse)
    router.add_api_route("/ui/chats", endpoint("ui_chats"), methods=["POST"], response_class=HTMLResponse)
    router.add_api_route(
        "/ui/chats-results", endpoint("ui_chats_results"), methods=["GET"], response_class=HTMLResponse
    )
    router.add_api_route(
        "/ui/chats/emails/{email_ref}", endpoint("ui_chat_email_drawer"), methods=["GET"], response_class=HTMLResponse
    )

    router.add_api_route("/ui/settings", endpoint("ui_settings"), methods=["GET"], response_class=HTMLResponse)
    router.add_api_route("/ui/settings", endpoint("ui_settings"), methods=["POST"], response_class=HTMLResponse)
    router.add_api_route(
        "/ui/settings/gmail-sync",
        endpoint("ui_gmail_sync_settings"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/naver-sync",
        endpoint("ui_naver_sync_settings"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/hiworks-sync",
        endpoint("ui_hiworks_sync_settings"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/mail-provider",
        endpoint("ui_settings_mail_provider"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/gmail/client-config",
        endpoint("ui_save_gmail_client_config"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/gmail/tokens",
        endpoint("ui_save_gmail_tokens"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/hiworks/account",
        endpoint("ui_save_hiworks_account"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route("/ui/settings/gmail/connect", endpoint("ui_gmail_connect"), methods=["GET"])
    router.add_api_route("/auth/gmail/callback", endpoint("gmail_oauth_callback"), methods=["GET"])
    router.add_api_route(
        "/ui/settings/gmail/disconnect",
        endpoint("ui_gmail_disconnect"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/gmail/sync",
        endpoint("ui_gmail_settings_sync"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/naver/sync",
        endpoint("ui_naver_settings_sync"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/hiworks/sync",
        endpoint("ui_hiworks_settings_sync"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/gmail/sync-outbound",
        endpoint("ui_gmail_settings_sync_outbound"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/demo/receive-latest-duplicate",
        endpoint("ui_receive_latest_duplicate_demo_mail"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/settings/routing-table",
        endpoint("ui_routing_table"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/routing-summary",
        endpoint("ui_routing_summary"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/auto-assignment-policy",
        endpoint("ui_auto_assignment_policy"),
        methods=["GET"],
        response_class=HTMLResponse,
    )
    router.add_api_route("/ui/display-mode/toggle", endpoint("ui_display_mode_toggle"), methods=["POST"])
    router.add_api_route("/ui/auto-sync/run", endpoint("ui_auto_sync_run"), methods=["POST"])
    router.add_api_route("/api/auto-sync", endpoint("auto_sync_status"), methods=["GET"])

    router.add_api_route(
        "/ui/emails/{email_ref}/classification/regenerate",
        endpoint("ui_email_classification_regenerate"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/classify",
        endpoint("ui_email_classification_regenerate"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/summary/regenerate",
        endpoint("ui_email_summary_regenerate"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/attachments/reanalyze",
        endpoint("ui_email_attachments_reanalyze"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/trash",
        endpoint("ui_trash_email"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/route-manual",
        endpoint("ui_route_email_manual"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/routing/manual-assign",
        endpoint("ui_manual_assign_review_email"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/emails/{email_ref}/routing/confirm-top-candidate",
        endpoint("ui_confirm_top_review_candidate"),
        methods=["POST"],
    )

    router.add_api_route(
        "/ui/settings/routing-table",
        endpoint("ui_settings_create_assignee"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/routing-table/{assignee_id}", endpoint("ui_settings_update_assignee"), methods=["POST"]
    )
    router.add_api_route(
        "/ui/settings/routing-table/{assignee_id}/autosave",
        endpoint("ui_settings_update_assignee"),
        methods=["POST"],
    )
    router.add_api_route(
        "/ui/settings/routing-table/{assignee_id}/toggle-active",
        endpoint("ui_settings_toggle_assignee"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/routing-table/{assignee_id}/deactivate",
        endpoint("ui_settings_deactivate_assignee"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/routing-table/{assignee_id}/delete",
        endpoint("ui_settings_delete_assignee"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/routing-summary/reorder",
        endpoint("ui_settings_routing_reorder"),
        methods=["POST"],
        response_class=HTMLResponse,
    )
    router.add_api_route(
        "/ui/settings/auto-assignment-policy",
        endpoint("ui_settings_auto_assignment_policy"),
        methods=["POST"],
        response_class=HTMLResponse,
    )

    router.add_api_route(
        "/api/demo/emails/{email_index}/attachments/{attachment_index}",
        endpoint("demo_email_attachment"),
        methods=["GET"],
    )
    return router
