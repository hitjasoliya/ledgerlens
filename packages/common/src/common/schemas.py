from typing import Annotated, Generic, List, Literal, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator

UserRole = Literal["admin", "employee"]
ResourceId = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
]


# Auth & User Schemas
class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=72)

    @field_validator("username")
    @classmethod
    def reject_blank_username(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Username must not be blank")
        return value

    @field_validator("password")
    @classmethod
    def bound_password_bytes(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must be at most 72 UTF-8 bytes")
        return value


class UserResponse(BaseModel):
    id: str
    username: str
    role: UserRole
    createdAt: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserCreateRequest(LoginRequest):
    role: UserRole = "employee"


# Document and ingestion contracts
DocumentStatus = Literal[
    "queued", "processing", "searchable", "failed", "deleting", "cleanup_pending"
]
JobStatus = Literal["queued", "processing", "completed", "failed", "cleanup_pending"]


class Citation(BaseModel):
    document_id: ResourceId
    filename: str
    page: int = Field(ge=1)
    chunk_id: str
    source_url: str


class DocumentResponse(BaseModel):
    id: str
    filename: str
    source: str
    uploaded_by_id: str
    uploaded_by: str
    owner_id: Optional[str] = None
    uploaded_at: int
    access_list: List[str]
    pages_parsed: int
    chunks_created: int
    chunks_indexed: int
    status: DocumentStatus
    parser: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dims: Optional[int] = None
    error_message: Optional[str] = None


class IngestResponse(BaseModel):
    source: str
    pages_parsed: int
    chunks_created: int
    chunks_indexed: int
    id: str
    job_id: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: str
    error_message: Optional[str] = None
    pages_parsed: int = 0
    chunks_created: int = 0
    chunks_indexed: int = 0
    document_id: Optional[str] = None


class UpdateAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_list: List[ResourceId] = Field(max_length=1000)


class ChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=10000)

    @field_validator("message")
    @classmethod
    def reject_blank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must not be blank")
        return value


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = Field(default_factory=list)
    chunks_used: int = 0
    message_id: Optional[str] = None
    user_message_id: Optional[str] = None


class ChatMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str
    citations: List[Citation] = Field(default_factory=list)
    chunks_used: int = 0
    unavailable: bool = False
    created_at: int


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    user_id: str
    created_at: int
    updated_at: int
    selected_document_ids: List[str] = Field(default_factory=list)
    revision: int = 0
    messages: List[ChatMessageResponse] = Field(default_factory=list)


class ChatSessionSummary(BaseModel):
    """A chat as listed in the sidebar; load the chat itself for its messages."""

    id: str
    title: str
    created_at: int
    updated_at: int
    selected_document_ids: List[str] = Field(default_factory=list)
    message_count: int = 0


class ChatSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New Chat", min_length=1, max_length=200)
    # A chat's documents are chosen once, here, and never change afterwards.
    selected_document_ids: List[ResourceId] = Field(min_length=1, max_length=100)


class RegenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: ResourceId


class ClearChatResponse(BaseModel):
    ok: bool


class EmbeddingsClearResponse(BaseModel):
    ok: bool
    deleted: int = 0
    files_deleted: int = 0
    cleanup_pending: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"


PAGE_DEFAULT_LIMIT = 50
PAGE_MAX_LIMIT = 200

ItemT = TypeVar("ItemT")


class Page(BaseModel, Generic[ItemT]):
    """One page of a list endpoint: `items[offset : offset + limit]` of `total`."""

    items: List[ItemT]
    total: int
    limit: int
    offset: int
