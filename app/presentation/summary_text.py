from __future__ import annotations

import re


_SCHEDULED_AND_REQUESTS_PATTERN = re.compile(
    r"(?P<event>[\w가-힣·/\- ]{2,40}?)(?:을|를) 예정하고,\s*(?P<request>.+요청(?:합니다|했습니다|드립니다)?)"
)
_BUSINESS_REF_REPEAT_PATTERN = re.compile(
    r"\b(?P<ref>[A-Z]{2,5}-\d{4}-\d{4}-\d{2}|[A-Z]{2}\d{6,})\b(?:\s*[-–—]?\s*\b(?P=ref)\b)+"
)


def polish_korean_summary_text(text: str) -> str:
    summary = " ".join(str(text or "").split())
    if not summary:
        return summary
    summary = _BUSINESS_REF_REPEAT_PATTERN.sub(lambda match: match.group("ref"), summary)
    summary = re.sub(r"^\s*견적서\s+송부\s+(?=(?:[A-Z]{2,5}-\d{4}-\d{4}-\d{2}|[A-Z]{2}\d{6,})\b)", "", summary)
    return _SCHEDULED_AND_REQUESTS_PATTERN.sub(
        lambda match: f"{match.group('event').strip()} 예정이어서, {match.group('request').strip()}",
        summary,
    )
