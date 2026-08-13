from typing import List, Optional
from pydantic import BaseModel, Field


# Auth & User Schemas
class LoginRequest(BaseModel):
    username: str
    password: str
    role: Optional[str] = "employee"


class UserResponse(BaseModel):
    id: str
    username: str
    role: str
    createdAt: int


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class UserCreateRequest(BaseModel):
    username: str
    password: str
    role: str = "employee"


# Document & Ingestion Schemas
class Citation(BaseModel):
    page: int
    chunk_id: str


class DocumentResponse(BaseModel):
    id: str
    filename: str
    source: str
    uploaded_by_id: str
    uploaded_by: str
    uploaded_at: int
    scope: str
    access_list: List[str]
    pages_parsed: int
    chunks_created: int
    chunks_indexed: int
    is_persistent: bool
    session_id: Optional[str] = None
    index_status: str = "unknown"  # pending | processing | completed | failed | unknown
    job_error: Optional[str] = None


class IngestResponse(BaseModel):
    source: str
    pages_parsed: int
    chunks_created: int
    chunks_indexed: int
    pages_failed: int = 0
    id: Optional[str] = None
    job_id: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending, processing, completed, failed
    error_message: Optional[str] = None
    pages_parsed: int = 0
    chunks_created: int = 0
    chunks_indexed: int = 0
    document_id: Optional[str] = None


class UpdateAccessRequest(BaseModel):
    access_list: List[str]


# Chat & RAG Schemas
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    user_id: Optional[str] = "guest"
    session_id: Optional[str] = "default_session"


class ChatResponse(BaseModel):
    answer: str
    citations: List[Citation] = []
    chunks_used: int = 0


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    citations: List[Citation] = []
    chunks_used: int = 0
    created_at: int


class ChatSessionResponse(BaseModel):
    id: str
    title: str
    user_id: str
    created_at: int
    updated_at: int
    context_file_id: Optional[str] = None
    messages: List[ChatMessageResponse] = []


class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Chat"
    context_file_id: Optional[str] = None


class ClearChatResponse(BaseModel):
    ok: bool


class EmbeddingsClearResponse(BaseModel):
    ok: bool
    deleted: int = 0
    files_deleted: int = 0


class HealthResponse(BaseModel):
    status: str = "ok"
