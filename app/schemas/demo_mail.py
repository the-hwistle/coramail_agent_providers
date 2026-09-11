from __future__ import annotations

from pydantic import BaseModel, Field


class DemoAttachment(BaseModel):
    id: str
    provider_attachment_id: str = ""
    filename: str
    storage_uri: str
    content_type: str = "application/octet-stream"
    file_group: str = "file"
    file_size: int | None = None
    checksum_sha256: str = ""
    is_inline: bool = False
    processing_status: str = "pending"
    mapping_basis: str = ""


class DemoRecipient(BaseModel):
    id: str
    recipient_type: str
    name: str = ""
    address: str


class DemoExpectedLabels(BaseModel):
    mail_category: str = "unclassified"
    document_category: str = ""
    priority: str = "normal"
    urgency: str = ""
    importance: str = ""
    attention_quadrant: str = ""
    assignee_area: str = ""
    business_refs: list[str] = Field(default_factory=list)
    vessel_names: list[str] = Field(default_factory=list)
    equipment: list[str] = Field(default_factory=list)
    key_spec_fields: dict[str, str] = Field(default_factory=dict)
    counterparty: str = ""
    follow_up_of: str = ""


class DemoMessage(BaseModel):
    id: str
    provider_message_id: str
    provider_thread_id: str = ""
    rfc_message_id: str = ""
    sender_name: str = ""
    sender_address: str
    subject: str
    subject_normalized: str = ""
    body_text: str
    snippet: str = ""
    sent_at: str
    received_at: str = ""
    has_attachment: bool = False
    attachment_count: int = 0
    processing_status: str = "received"
    recipients: list[DemoRecipient] = Field(default_factory=list)
    attachments: list[DemoAttachment] = Field(default_factory=list)
    expected_demo_labels: DemoExpectedLabels = Field(default_factory=DemoExpectedLabels)


class DemoEmailAccount(BaseModel):
    id: str
    provider: str
    email_address: str
    display_name: str = ""
    status: str = "active"
    timezone: str = "Asia/Seoul"


class DemoFixture(BaseModel):
    fixture_version: int
    name: str
    description: str = ""
    source: dict[str, str] = Field(default_factory=dict)
    id_policy: dict[str, str] = Field(default_factory=dict)
    email_account: DemoEmailAccount
    messages: list[DemoMessage] = Field(default_factory=list)
