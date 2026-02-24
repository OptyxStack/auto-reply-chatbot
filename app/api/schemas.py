"""Pydantic schemas for API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# --- Conversations ---
class CreateConversationRequest(BaseModel):
    source_type: Literal["ticket", "livechat"] = Field(
        ..., description="Source type: ticket or livechat"
    )
    source_id: str = Field(..., min_length=1, description="Ticket or livechat ID")
    metadata: dict[str, Any] | None = None


class ConversationResponse(BaseModel):
    id: str
    source_type: str
    source_id: str
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
    debug: dict[str, Any] | None = None


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
    source_type: str
    source_id: str
    metadata: dict[str, Any] | None
    created_at: datetime
    messages: list[MessageResponse]


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class UpdateConversationRequest(BaseModel):
    metadata: dict[str, Any] | None = None


# --- Documents CRUD ---
class DocumentResponse(BaseModel):
    id: str
    title: str
    source_url: str
    doc_type: str
    effective_date: datetime | None
    chunks_count: int
    source_file: str | None = None
    metadata: dict[str, Any] | None = None
    raw_content: str | None = None
    cleaned_content: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    page: int
    page_size: int


class DocumentCreateRequest(BaseModel):
    url: str = Field(..., description="Source URL (unique)")
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


class DocumentUpdateRequest(BaseModel):
    title: str | None = None
    doc_type: str | None = None
    effective_date: str | None = None
    metadata: dict[str, Any] | None = None


class FetchFromUrlRequest(BaseModel):
    url: str = Field(..., min_length=1, description="URL to fetch content from")


class FetchFromUrlResponse(BaseModel):
    title: str
    content: str
    raw_html: str | None = None


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


# --- Branding config (prompts, intents) ---
class AppConfigResponse(BaseModel):
    key: str
    value: str


class AppConfigUpdateRequest(BaseModel):
    value: str = Field(..., min_length=1)


class IntentResponse(BaseModel):
    id: str
    key: str
    patterns: str
    answer: str
    enabled: bool
    sort_order: int


class IntentCreateRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=64)
    patterns: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    enabled: bool = True
    sort_order: int = 0


class IntentUpdateRequest(BaseModel):
    patterns: str | None = None
    answer: str | None = None
    enabled: bool | None = None
    sort_order: int | None = None


# --- WHMCS cookies (save separately, use for crawl) ---
WHMCS_COOKIES_KEY = "whmcs_session_cookies"


class SaveWhmcsCookiesRequest(BaseModel):
    """Save WHMCS session cookies for later crawl. Paste JSON from browser."""

    session_cookies: list[dict[str, Any]] = Field(
        ...,
        min_length=1,
        description="Cookies from browser: [{name, value, domain?, path?}]",
    )


class SaveWhmcsCookiesResponse(BaseModel):
    status: str = "ok"
    count: int = Field(..., description="Number of cookies saved")


class CheckWhmcsCookiesRequest(BaseModel):
    """Check if cookies authenticate. Uses saved cookies if session_cookies not provided."""

    session_cookies: list[dict[str, Any]] | None = None
    base_url: str = Field(
        default="https://greencloudvps.com/billing/greenvps",
        description="WHMCS base URL",
    )
    list_path: str = Field(
        default="supporttickets.php?filter=1",
        description="Ticket list path",
    )
    debug: bool = Field(default=False, description="Return debug info (cookies added, redirect, etc.)")


class CheckWhmcsCookiesResponse(BaseModel):
    ok: bool = Field(..., description="True if auth succeeded")
    message: str = Field(..., description="Status message")
    debug: dict[str, Any] | None = Field(default=None, description="Debug info when debug=True")


# --- Crawl tickets (uses saved cookies or inline credentials) ---
class CrawlTicketsRequest(BaseModel):
    """Crawl WHMCS tickets. Uses saved cookies from save-whmcs-cookies, or inline session_cookies/credentials."""

    username: str | None = None
    password: str | None = None
    totp_code: str | None = Field(default=None, min_length=6, max_length=8, description="2FA code")
    session_cookies: list[dict[str, Any]] | None = Field(
        None,
        description="Inline cookies (optional if already saved via save-whmcs-cookies)",
    )
    base_url: str = Field(
        default="https://greencloudvps.com/billing/greenvps",
        description="WHMCS base URL",
    )
    list_path: str = Field(
        default="supporttickets.php?filter=1",
        description="Ticket list path: supporttickets.php?filter=1",
    )
    login_path: str = Field(
        default="login.php",
        description="Login page path (for username/password mode)",
    )


class CrawlTicketsResponse(BaseModel):
    status: str = "ok"
    count: int = Field(..., description="Number of tickets crawled and saved")
    skipped: int = Field(0, description="Number of system-alert tickets skipped this run")
    saved_to: str = Field(..., description="Path to saved JSON file")
    tickets: list[dict[str, Any]] = Field(default_factory=list, description="Crawled ticket data")


# --- Health ---
class HealthResponse(BaseModel):
    status: str
    version: str
    checks: dict[str, str]


# --- SSE streaming ---
class StreamChunk(BaseModel):
    type: str  # content | citations | done | error
    data: str | dict | None = None
