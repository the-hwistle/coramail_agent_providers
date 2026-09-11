from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class AttachmentAnalysisStatus(str, Enum):
    COMPLETED = "completed"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"


class AttachmentPage(BaseModel):
    page_number: int = Field(ge=1)
    text: str = ""


class AttachmentTable(BaseModel):
    name: str | None = None
    sheet_name: str | None = None
    page_number: int | None = Field(default=None, ge=1)
    rows: list[list[Any]] = Field(default_factory=list)


class AttachmentEvidence(BaseModel):
    source_type: str = "attachment"
    attachment_id: UUID
    page_number: int | None = Field(default=None, ge=1)
    text: str = Field(min_length=1)
    bbox: list[float] | None = None


class AttachmentAnalysisResult(BaseModel):
    attachment_id: UUID
    filename: str
    content_type: str
    status: AttachmentAnalysisStatus
    document_type: str | None = None
    document_type_confidence: float = Field(default=0.0, ge=0, le=1)
    analysis_summary: str = ""
    extracted_text: str = ""
    document_html: str = ""
    pages: list[AttachmentPage] = Field(default_factory=list)
    tables: list[AttachmentTable] = Field(default_factory=list)
    fields: dict[str, Any] = Field(default_factory=dict)
    evidence: list[AttachmentEvidence] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None
