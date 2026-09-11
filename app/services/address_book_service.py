from __future__ import annotations

from collections import Counter
from typing import Any


_NON_ORGANIZATION_LABELS = {
    "발주",
    "문의",
    "서비스",
    "기술",
    "기타",
    "미분류",
    "인증서 요청",
    "클레임",
    "호환성 확인",
    "납기 확인",
    "도면 검토",
    "결제 문의",
    "견적 요청",
    "서비스 요청",
    "사양 검토",
    "기술 문의",
    "긴급 장애",
    "긴급 고장",
}


def address_book_view(
    rows: list[dict[str, Any]],
    *,
    query: str = "",
    organization: str = "",
    limit_recent: int = 3,
) -> dict[str, Any]:
    """Build sender profiles from stored mail rows without inventing organization data."""

    profiles_by_address: dict[str, dict[str, Any]] = {}
    for row in rows:
        address = _sender_address(row)
        if not address:
            continue
        key = address.casefold()
        profile = profiles_by_address.setdefault(
            key,
            {
                "sender_address": address,
                "sender_name": _sender_name(row, address),
                "organization": "",
                "email_count": 0,
                "thread_count": 0,
                "first_seen": "",
                "last_seen": "",
                "categories": Counter(),
                "recent_emails": [],
                "_thread_keys": set(),
            },
        )
        profile["email_count"] += 1
        if not profile["sender_name"] or profile["sender_name"] == profile["sender_address"]:
            profile["sender_name"] = _sender_name(row, address)
        if not profile["organization"]:
            profile["organization"] = _organization(row)
        category = str(row.get("mail_category") or row.get("business_label") or "").strip()
        if category:
            profile["categories"][category] += 1
        profile["_thread_keys"].add(_thread_key(row))
        seen_at = str(row.get("date") or row.get("received_at") or row.get("created_at") or "").strip()
        if seen_at:
            if not profile["last_seen"]:
                profile["last_seen"] = seen_at
            profile["first_seen"] = seen_at
        if len(profile["recent_emails"]) < limit_recent:
            profile["recent_emails"].append(_history_item(row))

    query_text = " ".join(query.split()).casefold()
    selected_organization = " ".join(organization.split())
    profiles = []
    organization_counts: Counter[str] = Counter()
    for profile in profiles_by_address.values():
        categories: Counter[str] = profile.pop("categories")
        thread_keys: set[str] = profile.pop("_thread_keys")
        profile["thread_count"] = len({key for key in thread_keys if key})
        profile["organization"] = profile["organization"] or "미확인"
        organization_counts[str(profile["organization"])] += 1
        profile["top_categories"] = [
            {"label": label, "count": count}
            for label, count in categories.most_common(3)
        ]
        if selected_organization and str(profile["organization"]) != selected_organization:
            continue
        if query_text:
            searchable = " ".join(
                [
                    str(profile.get("sender_name") or ""),
                    str(profile.get("sender_address") or ""),
                    str(profile.get("organization") or ""),
                    " ".join(item["subject"] for item in profile["recent_emails"]),
                    " ".join(item["mail_category"] for item in profile["recent_emails"]),
                ]
            ).casefold()
            if query_text not in searchable:
                continue
        profiles.append(profile)

    profiles.sort(
        key=lambda profile: (
            -int(profile.get("email_count") or 0),
            str(profile.get("sender_name") or "").casefold(),
            str(profile.get("sender_address") or "").casefold(),
        )
    )
    return {
        "query": query,
        "selected_organization": selected_organization,
        "address_book_organizations": [
            {"label": label, "count": count}
            for label, count in sorted(
                organization_counts.items(),
                key=_organization_filter_sort_key,
            )
        ],
        "address_book_profiles": profiles,
        "address_book_profile_count": len(profiles),
        "address_book_email_count": sum(int(profile.get("email_count") or 0) for profile in profiles),
        "address_book_thread_count": sum(int(profile.get("thread_count") or 0) for profile in profiles),
    }


def _organization_filter_sort_key(item: tuple[str, int]) -> tuple[bool, int, str]:
    label, count = item
    return label == "미확인", -count, label


def attach_sender_contacts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles = {
        str(profile.get("sender_address") or "").casefold(): profile
        for profile in address_book_view(rows).get("address_book_profiles", [])
    }
    attached = []
    for row in rows:
        address = _sender_address(row)
        profile = profiles.get(address.casefold()) if address else None
        attached.append({**row, "sender_contact": profile or _fallback_profile(row)})
    return attached


def sender_contact_for_email(email: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    address = _sender_address(email)
    for row in attach_sender_contacts(rows):
        contact = row.get("sender_contact") if isinstance(row.get("sender_contact"), dict) else {}
        if address and str(contact.get("sender_address") or "").casefold() == address.casefold():
            return contact
    return _fallback_profile(email)


def _sender_address(row: dict[str, Any]) -> str:
    return str(row.get("sender_address") or row.get("from") or "").strip()


def _fallback_profile(row: dict[str, Any]) -> dict[str, Any]:
    address = _sender_address(row)
    return {
        "sender_name": _sender_name(row, address),
        "sender_address": address,
        "organization": _organization(row) or "미확인",
        "email_count": 1 if address else 0,
        "thread_count": 1 if address else 0,
        "last_seen": str(row.get("date") or row.get("received_at") or row.get("created_at") or "").strip(),
        "top_categories": [],
        "recent_emails": [_history_item(row)] if address else [],
    }


def _sender_name(row: dict[str, Any], address: str) -> str:
    name = str(row.get("sender_name") or row.get("from") or "").strip()
    return name or address


def _organization(row: dict[str, Any]) -> str:
    classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
    facts = row.get("mail_facts") if isinstance(row.get("mail_facts"), dict) else {}
    for value in (
        row.get("customer_name"),
        classification.get("customer_name"),
        classification.get("counterparty"),
        facts.get("customer_name"),
    ):
        text = str(value or "").strip()
        if text and not _is_non_organization_label(text, row):
            return text
    candidates = facts.get("customer_candidates")
    if isinstance(candidates, list):
        for value in candidates:
            text = str(value or "").strip()
            if text and not _is_non_organization_label(text, row):
                return text
    return ""


def _is_non_organization_label(value: str, row: dict[str, Any]) -> bool:
    normalized = " ".join(value.split()).casefold()
    if not normalized:
        return True
    row_labels = {
        str(row.get("mail_category") or "").strip(),
        str(row.get("business_label") or "").strip(),
    }
    classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
    for key in ("mail_category", "business_label", "primary_type", "category"):
        row_labels.add(str(classification.get(key) or "").strip())
    blocked = {label for label in row_labels.union(_NON_ORGANIZATION_LABELS) if label}
    return normalized in {" ".join(label.split()).casefold() for label in blocked}


def _thread_key(row: dict[str, Any]) -> str:
    return str(
        row.get("provider_thread_id")
        or row.get("thread_id")
        or row.get("subject_normalized")
        or row.get("subject")
        or row.get("email_uid")
        or ""
    ).strip()


def _history_item(row: dict[str, Any]) -> dict[str, str]:
    return {
        "email_uid": str(row.get("email_uid") or ""),
        "subject": str(row.get("subject") or "(제목 없음)"),
        "date": str(row.get("date") or row.get("received_at") or row.get("created_at") or ""),
        "mail_category": str(row.get("mail_category") or row.get("business_label") or "미분류"),
        "work_status_label": str(row.get("work_status_label") or ""),
        "routing_display": str(row.get("routing_display") or ""),
    }
