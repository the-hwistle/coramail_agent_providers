from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Protocol
from uuid import uuid4

from app.services.mail_search_service import normalize_search_query


CHAT_HISTORY_MAX_TURNS = 8
CHAT_CLIENT_HISTORY_MAX_TURNS = 4
CHAT_TEXT_LIMIT = 1200
CHAT_BUSINESS_IDENTIFIER_PATTERN = re.compile(r"(?=.*[A-Za-z])(?=.*\d)[0-9A-Za-z][0-9A-Za-z._/-]{4,}")
CHAT_FOLLOW_UP_PATTERN = re.compile(r"(그|해당|위|이전|방금|앞(?:선|의)|이\s*(메일|견적서|문서)|저\s*(메일|견적서|문서))")
CHAT_SHORT_FIELD_FOLLOW_UP_PATTERN = re.compile(r"(납기|금액|총액|수량|품번|발신자|보낸\s*사람|원본)")
CHAT_EVIDENCE_REQUIRED_PATTERN = re.compile(
    r"(메일|이메일|첨부|견적서|문서|원본|담당자|배정|라우팅|분류|카테고리|긴급|"
    r"납기|금액|총액|수량|품번|제품|발신자|보낸\s*사람|제목|수신\s*시각|고객|업체|회사|"
    r"최신|최근|찾아|검색|보여줘|확인)"
)
CHAT_EVIDENCE_FACT_PATTERN = re.compile(
    r"(담당자|배정|라우팅|분류|카테고리|긴급|납기|금액|총액|수량|품번|제품|발신자|"
    r"보낸\s*사람|제목|수신\s*시각|최신|최근|찾아|검색|보여줘|확인)"
)
CHAT_EVIDENCE_COMPOSITION_PATTERN = re.compile(r"(초안|답장|회신|작성|써줘)")
CHAT_EVIDENCE_OPTIONAL_PATTERN = re.compile(
    r"(초안|답장|회신|작성|써줘|브레인스토밍|의견|검토|개선|제안|일반적|절차|프로세스)"
)
CHAT_EVIDENCE_UNNEEDED_PATTERN = re.compile(
    r"(사용법|화면|탭|기능|도움말|문장|표현|공손|짧게|간결|다듬|고쳐|바꿔|번역)"
)
CHAT_EVIDENCE_REQUIRED = "required"
CHAT_EVIDENCE_OPTIONAL = "optional"
CHAT_EVIDENCE_NONE = "none"


class MailSearchLike(Protocol):
    def search(self, query: str, *, limit: int = 5, conversation_context: str = "") -> dict[str, Any]: ...


@dataclass
class MailChatTurn:
    query: str
    answer: str
    result: dict[str, Any] | None = None
    error: str = ""
    search_query: str = ""
    evidence_policy: str = CHAT_EVIDENCE_REQUIRED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def compact(self) -> dict[str, Any]:
        return {
            "query": _chat_text(self.query),
            "answer": _chat_text(self.answer),
            "search_query": _chat_text(self.search_query),
            "evidence_policy": _evidence_policy_value(self.evidence_policy),
            "results": _compact_result_items(self.result),
        }


@dataclass
class MailChatSession:
    session_id: str
    turns: list[MailChatTurn] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def append(self, turn: MailChatTurn) -> None:
        self.turns.append(turn)
        self.turns = self.turns[-CHAT_HISTORY_MAX_TURNS:]
        self.updated_at = datetime.now(timezone.utc)


class MailChatSessionStore:
    def __init__(self, *, max_sessions: int = 128):
        self.max_sessions = max_sessions
        self._sessions: dict[str, MailChatSession] = {}
        self._lock = Lock()

    def get_or_create(self, session_id: str = "") -> MailChatSession:
        with self._lock:
            requested_id = _safe_session_id(session_id)
            if requested_id and requested_id in self._sessions:
                return self._sessions[requested_id]
            session = MailChatSession(session_id=requested_id or uuid4().hex)
            self._sessions[session.session_id] = session
            self._trim_locked()
            return session

    def _trim_locked(self) -> None:
        if len(self._sessions) <= self.max_sessions:
            return
        stale_ids = sorted(
            self._sessions,
            key=lambda session_id: self._sessions[session_id].updated_at,
        )
        for session_id in stale_ids[: max(0, len(self._sessions) - self.max_sessions)]:
            self._sessions.pop(session_id, None)


class MailChatService:
    def __init__(self, store: MailChatSessionStore):
        self.store = store

    def session_context(self, session_id: str = "") -> dict[str, Any]:
        session = self.store.get_or_create(session_id)
        return self._context(session)

    def ask(
        self,
        *,
        session_id: str,
        query: str,
        search_service: MailSearchLike,
        limit: int = 5,
        compact_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        session = self.store.get_or_create(session_id)
        if not session.turns and compact_history:
            self._restore_compact_history(session, compact_history)
        normalized_query = normalize_search_query(query)
        if not normalized_query:
            return self._context(session)

        evidence_policy = chat_evidence_policy(normalized_query)
        search_query = self.resolve_search_query(normalized_query, session.turns)
        conversation_context = self.conversation_context(session.turns)
        error = ""
        result: dict[str, Any] | None = None
        try:
            result = search_service.search(
                search_query,
                limit=limit,
                conversation_context=conversation_context,
            )
        except Exception as exc:  # noqa: BLE001
            error = _chat_error_message(exc)
        answer = _chat_text(error or (result or {}).get("answer") or "답변을 생성하지 못했습니다.")
        session.append(
            MailChatTurn(
                query=normalized_query,
                answer=answer,
                result=result,
                error=error,
                search_query=search_query,
                evidence_policy=evidence_policy,
            )
        )
        return self._context(session)

    def _restore_compact_history(self, session: MailChatSession, compact_history: list[dict[str, Any]]) -> None:
        for raw_turn in compact_history[-CHAT_HISTORY_MAX_TURNS:]:
            if not isinstance(raw_turn, dict):
                continue
            query = _chat_text(raw_turn.get("query"))
            answer = _chat_text(raw_turn.get("answer"))
            if not query and not answer:
                continue
            session.append(
                MailChatTurn(
                    query=query,
                    answer=answer,
                    search_query=_chat_text(raw_turn.get("search_query")),
                    evidence_policy=_evidence_policy_value(raw_turn.get("evidence_policy")),
                    result={"results": _restore_result_items(raw_turn.get("results"))},
                )
            )

    def resolve_search_query(self, query: str, turns: list[MailChatTurn]) -> str:
        if not query or not turns or not _query_needs_history_constraint(query):
            return query
        target_identifiers: list[str] = []
        fallback_identifiers: list[str] = []
        for turn in reversed(turns[-3:]):
            target_identifiers.extend(_result_target_identifiers(turn.result))
            fallback_identifiers.extend(_result_business_identifiers(turn.result))
            fallback_identifiers.extend(_business_identifiers(f"{turn.query} {turn.answer} {turn.search_query}"))
        identifiers = target_identifiers or fallback_identifiers
        ordered_identifiers: list[str] = []
        for identifier in identifiers:
            if identifier.casefold() not in {item.casefold() for item in ordered_identifiers}:
                ordered_identifiers.append(identifier)
        if not ordered_identifiers:
            return query
        label = "관련 메일 UID" if target_identifiers else "관련 업무 식별자"
        return f"{query} {label}: {' '.join(ordered_identifiers[:3])}"

    def conversation_context(self, turns: list[MailChatTurn]) -> str:
        context_lines: list[str] = []
        for index, turn in enumerate(turns[-CHAT_HISTORY_MAX_TURNS:], start=1):
            context_lines.append(f"이전 질문 {index}: {_chat_text(turn.query, limit=360)}")
            context_lines.append(f"이전 답변 {index}: {_chat_text(turn.answer, limit=520)}")
            if turn.search_query and turn.search_query != turn.query:
                context_lines.append(f"이전 검색 질의 {index}: {_chat_text(turn.search_query, limit=360)}")
            context_lines.extend(_result_context_lines(index, turn.result))
        return "\n".join(context_lines)

    @staticmethod
    def _context(session: MailChatSession) -> dict[str, Any]:
        return {
            "session_id": session.session_id,
            "turns": session.turns,
            "compact_turns": [turn.compact() for turn in session.turns[-CHAT_CLIENT_HISTORY_MAX_TURNS:]],
        }


def _chat_text(value: object, *, limit: int = CHAT_TEXT_LIMIT) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def chat_evidence_policy(query: str) -> str:
    normalized = normalize_search_query(query)
    if not normalized:
        return CHAT_EVIDENCE_NONE
    if CHAT_EVIDENCE_FACT_PATTERN.search(normalized):
        return CHAT_EVIDENCE_REQUIRED
    if CHAT_EVIDENCE_COMPOSITION_PATTERN.search(normalized):
        return CHAT_EVIDENCE_OPTIONAL
    if _business_identifiers(normalized) or _query_needs_history_constraint(normalized):
        return CHAT_EVIDENCE_REQUIRED
    if CHAT_EVIDENCE_REQUIRED_PATTERN.search(normalized):
        return CHAT_EVIDENCE_REQUIRED
    if CHAT_EVIDENCE_OPTIONAL_PATTERN.search(normalized):
        return CHAT_EVIDENCE_OPTIONAL
    if CHAT_EVIDENCE_UNNEEDED_PATTERN.search(normalized):
        return CHAT_EVIDENCE_NONE
    return CHAT_EVIDENCE_OPTIONAL


def _evidence_policy_value(value: object) -> str:
    policy = str(value or "").strip()
    if policy in {CHAT_EVIDENCE_REQUIRED, CHAT_EVIDENCE_OPTIONAL, CHAT_EVIDENCE_NONE}:
        return policy
    return CHAT_EVIDENCE_REQUIRED


def _compact_result_items(result: dict[str, Any] | None) -> list[dict[str, str]]:
    if not result:
        return []
    compact_items: list[dict[str, str]] = []
    for item in (result.get("results") or [])[:3]:
        if not isinstance(item, dict):
            continue
        compact_items.append(
            {
                "email_uid": _chat_text(item.get("email_uid"), limit=120),
                "source_type": _chat_text(item.get("source_type"), limit=40),
                "source": _chat_text(item.get("source"), limit=180),
                "title": _chat_text(item.get("title"), limit=180),
                "sender": _chat_text(item.get("sender"), limit=180),
                "category": _chat_text(item.get("category"), limit=80),
                "received_at": _chat_text(item.get("received_at"), limit=80),
                "business_refs": _chat_text(", ".join(str(value) for value in item.get("business_refs") or []), limit=220),
                "preview": _chat_text(item.get("raw_preview") or item.get("preview"), limit=360),
            }
        )
    return compact_items


def _restore_result_items(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for raw_item in value[:3]:
        if not isinstance(raw_item, dict):
            continue
        restored = {
            "email_uid": _chat_text(raw_item.get("email_uid"), limit=120),
            "source_type": _chat_text(raw_item.get("source_type"), limit=40),
            "source": _chat_text(raw_item.get("source"), limit=180),
            "title": _chat_text(raw_item.get("title"), limit=180),
            "sender": _chat_text(raw_item.get("sender"), limit=180),
            "category": _chat_text(raw_item.get("category"), limit=80),
            "received_at": _chat_text(raw_item.get("received_at"), limit=80),
            "business_refs": _restore_business_refs(raw_item.get("business_refs")),
            "preview": _chat_text(raw_item.get("preview"), limit=360),
            "raw_preview": _chat_text(raw_item.get("preview"), limit=360),
        }
        if any(restored.values()):
            items.append(restored)
    return items


def _restore_business_refs(value: object) -> list[str]:
    if isinstance(value, list):
        return [_chat_text(item, limit=80) for item in value if _chat_text(item, limit=80)]
    text = _chat_text(value, limit=220)
    return [item.strip() for item in text.split(",") if item.strip()]


def _chat_error_message(exc: Exception) -> str:
    raw_message = _chat_text(exc, limit=1600)
    normalized = raw_message.casefold()
    if "llm http 429" in normalized or "resource_exhausted" in normalized or "quota" in normalized:
        return (
            "대화 근거를 조회하지 못했습니다: Gemini API 할당량이 초과되었습니다. "
            "잠시 후 다시 시도하거나 로컬 LLM 설정으로 전환해 주세요."
        )
    if "invalid structured llm response" in normalized:
        return "답변 생성 중 모델 응답 형식이 깨졌습니다. 검색된 근거 기준으로 다시 시도해 주세요."
    return f"대화 근거를 조회하지 못했습니다: {raw_message}"


def _safe_session_id(session_id: str) -> str:
    raw = str(session_id or "").strip()
    return raw if re.fullmatch(r"[0-9a-fA-F-]{12,64}", raw) else ""


def _business_identifiers(text: str) -> list[str]:
    identifiers: list[str] = []
    for match in CHAT_BUSINESS_IDENTIFIER_PATTERN.finditer(text or ""):
        token = match.group(0).strip(".,;:()[]{}<>\"'“”‘’")
        if not token:
            continue
        if _looks_like_date_identifier(token):
            continue
        has_uppercase_letter = any(character.isalpha() and character.isupper() for character in token)
        has_business_separator = any(separator in token for separator in ("-", "/", "_"))
        if not has_uppercase_letter and not has_business_separator:
            continue
        if token.casefold() not in {item.casefold() for item in identifiers}:
            identifiers.append(token)
    return identifiers


def _looks_like_date_identifier(token: str) -> bool:
    return bool(
        re.fullmatch(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", token)
        or re.fullmatch(r"\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}", token)
    )


def _result_target_identifiers(result: dict[str, Any] | None) -> list[str]:
    identifiers: list[str] = []
    if not result:
        return identifiers
    for item in result.get("results") or []:
        if not isinstance(item, dict):
            continue
        identifiers.extend(_business_identifiers(str(item.get("email_uid") or "")))
    ordered: list[str] = []
    for identifier in identifiers:
        if identifier.casefold() not in {item.casefold() for item in ordered}:
            ordered.append(identifier)
    return ordered


def _result_business_identifiers(result: dict[str, Any] | None) -> list[str]:
    identifiers: list[str] = []
    if not result:
        return identifiers
    for item in result.get("results") or []:
        if not isinstance(item, dict):
            continue
        for value in item.get("business_refs") or []:
            identifiers.extend(_business_identifiers(str(value)))
        identifiers.extend(_business_identifiers(str(item.get("title") or "")))
        identifiers.extend(_business_identifiers(str(item.get("source") or "")))
    ordered: list[str] = []
    for identifier in identifiers:
        if identifier.casefold() not in {item.casefold() for item in ordered}:
            ordered.append(identifier)
    return ordered


def _result_context_lines(turn_index: int, result: dict[str, Any] | None) -> list[str]:
    if not result:
        return []
    lines: list[str] = []
    for result_index, item in enumerate((result.get("results") or [])[:3], start=1):
        if not isinstance(item, dict):
            continue
        parts = [
            _context_part("email_uid", item.get("email_uid")),
            _context_part("source_type", item.get("source_type")),
            _context_part("source", item.get("source")),
            _context_part("title", item.get("title")),
            _context_part("sender", item.get("sender")),
            _context_part("category", item.get("category")),
            _context_part("received_at", item.get("received_at")),
            _context_part("business_refs", ", ".join(str(value) for value in item.get("business_refs") or [])),
            _context_part("preview", item.get("raw_preview") or item.get("preview")),
        ]
        compact_parts = [part for part in parts if part]
        if compact_parts:
            lines.append(f"이전 근거 {turn_index}-{result_index}: " + " | ".join(compact_parts))
    return lines


def _context_part(label: str, value: object, *, limit: int = 220) -> str:
    text = _chat_text(value, limit=limit)
    return f"{label}={text}" if text else ""


def _query_needs_history_constraint(query: str) -> bool:
    normalized = normalize_search_query(query)
    if not normalized:
        return False
    if _business_identifiers(normalized):
        return False
    if CHAT_FOLLOW_UP_PATTERN.search(normalized):
        return True
    return len(normalized) <= 24 and bool(CHAT_SHORT_FIELD_FOLLOW_UP_PATTERN.search(normalized))
