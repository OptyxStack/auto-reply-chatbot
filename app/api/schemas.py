"""Pydantic schemas for API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Conversations ---
class CreateConversationRequest(BaseModel):
    external_user_id: str | None = None
    metadata: dict[str, Any] | None = None


class ConversationResponse(BaseModel):
    id: str
    external_user_id: str | None
    metadata: dict[str, Any] | None
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class CitationSchema(BaseModel):
    chunk_id: str
    source_url: str
    doc_type: str


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    citations: list[CitationSchema] | None = None


class AssistantMessageResponse(BaseModel):
    message_id: str
    role: str = "assistant"
    content: str
    decision: str  # PASS | ASK_USER | ESCALATE
    followup_questions: list[str] = Field(default_factory=list)
    citations: list[CitationSchema] = Field(default_factory=list)
    confidence: float
    debug: dict[str, Any] | None = None
    created_at: datetime


class SendMessageResponse(BaseModel):
    conversation_id: str
    message: AssistantMessageResponse


class ConversationDetailResponse(BaseModel):
    id: str
    external_user_id: str | None
    metadata: dict[str, Any] | None
    created_at: datetime
    messages: list[MessageResponse]


# --- Admin / Ingest ---
class IngestDocument(BaseModel):
    url: str = Field(..., description="Source URL")
    title: str = Field(default="Untitled")
    raw_text: str | None = None
    raw_html: str | None = None
    content: str | None = None
    doc_type: str = Field(default="other")
    effective_date: str | None = None
    last_updated: str | None = None
    product: str | None = None
    region: str | None = None
    metadata: dict[str, Any] | None = None
    source_file: str | None = None


class IngestRequest(BaseModel):
    documents: list[IngestDocument]


class IngestResponse(BaseModel):
    job_id: str
    documents_count: int
    status: str = "queued"


# --- Health ---
class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict[str, str]


# --- SSE streaming ---
class StreamChunk(BaseModel):
    type: str  # content | citations | done | error
    data: str | dict | None = None
