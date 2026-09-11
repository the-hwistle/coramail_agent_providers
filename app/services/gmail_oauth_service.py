from __future__ import annotations

import logging
import os
from typing import Any

from app.integrations.gmail.sync_client import GMAIL_PRIMARY_SCOPES
from app.repositories.gmail_account_repository import GmailAccountRepository


logger = logging.getLogger(__name__)


class GmailOAuthService:
    def __init__(self, repository: GmailAccountRepository):
        self.repository = repository

    def authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        flow = self._flow(redirect_uri)
        return flow.authorization_url(
            access_type="offline",
            prompt="consent",
        )

    def complete_callback(self, *, redirect_uri: str, authorization_response: str) -> dict[str, Any]:
        flow = self._flow(redirect_uri)
        previous_relax_scope = os.environ.get("OAUTHLIB_RELAX_TOKEN_SCOPE")
        os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = "1"
        try:
            flow.fetch_token(authorization_response=authorization_response)
        finally:
            if previous_relax_scope is None:
                os.environ.pop("OAUTHLIB_RELAX_TOKEN_SCOPE", None)
            else:
                os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"] = previous_relax_scope
        credentials = flow.credentials
        email_address = self._profile_email(credentials)
        self.repository.save_connected_account(
            email_address=email_address,
            token_json=credentials.to_json(),
            scopes=list(credentials.scopes or GMAIL_PRIMARY_SCOPES),
        )
        return {"email_address": email_address}

    def _profile_email(self, credentials: Any) -> str:
        try:
            service = self._gmail_service(credentials)
            profile = service.users().getProfile(userId="me").execute()
        except Exception:
            logger.exception("Gmail OAuth token was issued, but Gmail profile lookup failed")
            return ""
        return str(profile.get("emailAddress") or "").strip()

    def _flow(self, redirect_uri: str) -> Any:
        if not self.repository.has_client_config():
            raise RuntimeError("Gmail OAuth client JSON is not configured.")
        try:
            from google_auth_oauthlib.flow import Flow
        except ImportError as exc:
            raise RuntimeError("Google OAuth dependencies are not installed.") from exc
        client_config = self.repository.client_config_info()
        if client_config:
            flow = Flow.from_client_config(client_config, scopes=GMAIL_PRIMARY_SCOPES)
        else:
            flow = Flow.from_client_secrets_file(str(self.repository.client_config_path), scopes=GMAIL_PRIMARY_SCOPES)
        flow.redirect_uri = redirect_uri
        return flow

    @staticmethod
    def _gmail_service(credentials: Any) -> Any:
        try:
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("Google API dependencies are not installed.") from exc
        return build("gmail", "v1", credentials=credentials)
