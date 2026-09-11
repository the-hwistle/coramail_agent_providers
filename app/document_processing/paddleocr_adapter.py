from __future__ import annotations

import html
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PaddleOCRParsedDocument:
    text: str
    html: str
    page_texts: list[str]
    warnings: list[str]


def paddleocr_enabled() -> bool:
    value = os.getenv("CORAMAIL_PADDLEOCR_ENABLED", "false").strip().casefold()
    return value not in {"0", "false", "off", "no", "never", "disabled"}


def paddleocr_mode() -> str:
    value = os.getenv("CORAMAIL_PADDLEOCR_MODE", "auto").strip().casefold()
    return value if value in {"auto", "always"} else "auto"


def parse_with_paddleocr(path: Path) -> PaddleOCRParsedDocument | None:
    if not paddleocr_enabled():
        return None
    try:
        pipeline = _paddleocr_pipeline()
    except Exception:
        return None

    try:
        output = _predict(pipeline, path)
    except Exception as exc:
        return PaddleOCRParsedDocument(text="", html="", page_texts=[], warnings=[f"paddleocr_failed:{type(exc).__name__}"])

    page_texts: list[str] = []
    page_html: list[str] = []
    for index, result in enumerate(output, start=1):
        markdown = _result_markdown(result)
        text = _markdown_to_plain_text(markdown)
        if text:
            page_texts.append(text)
        rendered = _markdown_to_html(markdown)
        if rendered:
            page_html.append(f'<section data-page="{index}">\n<h2>Page {index}</h2>\n{rendered}\n</section>')

    text = "\n\n".join(page_texts).strip()
    document_html = "\n".join(page_html).strip()
    if not text and not document_html:
        return PaddleOCRParsedDocument(text="", html="", page_texts=[], warnings=["paddleocr_no_text"])
    return PaddleOCRParsedDocument(text=text, html=document_html, page_texts=page_texts, warnings=["paddleocr_structurev3"])


@lru_cache(maxsize=1)
def _paddleocr_pipeline() -> Any:
    os.environ.setdefault("PADDLE_PDX_CACHE_HOME", "/tmp/coramail-paddlex-cache")
    from paddleocr import PPStructureV3

    kwargs: dict[str, Any] = {}
    device = os.getenv("CORAMAIL_PADDLEOCR_DEVICE", "").strip()
    if device:
        kwargs["device"] = device
    kwargs["use_doc_orientation_classify"] = _env_bool("CORAMAIL_PADDLEOCR_DOC_ORIENTATION", False)
    kwargs["use_doc_unwarping"] = _env_bool("CORAMAIL_PADDLEOCR_DOC_UNWARPING", False)
    kwargs["use_textline_orientation"] = _env_bool("CORAMAIL_PADDLEOCR_TEXTLINE_ORIENTATION", False)
    kwargs["enable_mkldnn"] = _env_bool("CORAMAIL_PADDLEOCR_MKLDNN", False)
    return PPStructureV3(**kwargs)


def _predict(pipeline: Any, path: Path) -> list[Any]:
    kwargs = {
        "input": str(path),
        "use_doc_orientation_classify": _env_bool("CORAMAIL_PADDLEOCR_DOC_ORIENTATION", False),
        "use_doc_unwarping": _env_bool("CORAMAIL_PADDLEOCR_DOC_UNWARPING", False),
        "use_textline_orientation": _env_bool("CORAMAIL_PADDLEOCR_TEXTLINE_ORIENTATION", False),
        "use_table_orientation_classify": _env_bool("CORAMAIL_PADDLEOCR_TABLE_ORIENTATION", False),
        "enable_mkldnn": _env_bool("CORAMAIL_PADDLEOCR_MKLDNN", False),
    }
    try:
        return list(pipeline.predict(**kwargs))
    except TypeError:
        return list(pipeline.predict(str(path)))


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().casefold()
    if not value:
        return default
    return value in {"1", "true", "yes", "on"}


def _result_markdown(result: Any) -> str:
    markdown = getattr(result, "markdown", None)
    if isinstance(markdown, dict):
        texts = markdown.get("markdown_texts")
        if isinstance(texts, list):
            return "\n\n".join(str(item) for item in texts if str(item).strip()).strip()
        if texts:
            return str(texts).strip()
    if isinstance(markdown, str):
        return markdown.strip()

    payload = getattr(result, "json", None) or getattr(result, "res", None)
    if isinstance(payload, dict):
        return _json_payload_text(payload)
    return ""


def _json_payload_text(payload: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("rec_text", "text", "html", "markdown"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    rec_texts = payload.get("rec_texts")
    if isinstance(rec_texts, list):
        values.extend(str(item).strip() for item in rec_texts if str(item).strip())
    parsing = payload.get("parsing_res_list")
    if isinstance(parsing, list):
        for item in parsing:
            if isinstance(item, dict):
                values.extend(str(item.get(key) or "").strip() for key in ("text", "content", "html") if item.get(key))
    return "\n".join(value for value in values if value).strip()


def _markdown_to_plain_text(markdown: str) -> str:
    rows = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped or _is_markdown_table_separator(stripped):
            continue
        if stripped.startswith("#"):
            stripped = stripped.lstrip("#").strip()
        rows.append(re.sub(r"<[^>]+>", " ", stripped))
    return "\n".join(" ".join(row.split()) for row in rows if row.strip()).strip()


def _markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    table_rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            _flush_table(blocks, table_rows)
            continue
        if "|" in stripped and not _is_markdown_table_separator(stripped):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if len(cells) > 1:
                table_rows.append(cells)
                continue
        _flush_table(blocks, table_rows)
        if stripped.startswith("#"):
            level = min(6, max(1, len(stripped) - len(stripped.lstrip("#"))))
            blocks.append(f"<h{level}>{html.escape(stripped.lstrip('#').strip())}</h{level}>")
        elif stripped.startswith("<") and stripped.endswith(">"):
            blocks.append(stripped)
        else:
            blocks.append(f"<p>{html.escape(stripped)}</p>")
    _flush_table(blocks, table_rows)
    return "\n".join(blocks).strip()


def _flush_table(blocks: list[str], rows: list[list[str]]) -> None:
    if not rows:
        return
    rendered_rows = []
    for index, row in enumerate(rows):
        tag = "th" if index == 0 else "td"
        rendered_cells = "".join(f"<{tag}>{html.escape(cell)}</{tag}>" for cell in row)
        rendered_rows.append(f"<tr>{rendered_cells}</tr>")
    blocks.append("<table>\n" + "\n".join(rendered_rows) + "\n</table>")
    rows.clear()


def _is_markdown_table_separator(line: str) -> bool:
    normalized = line.replace("|", "").replace(":", "").replace("-", "").strip()
    return not normalized and "-" in line
