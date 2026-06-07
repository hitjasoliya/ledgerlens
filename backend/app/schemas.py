from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    user_id: str = "guest"
    session_id: str = "default_session"


class Citation(BaseModel):
    page: int
    chunk_id: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]
    chunks_used: int


class IngestResponse(BaseModel):
    source: str
    pages_parsed: int
    chunks_created: int
    chunks_indexed: int
    pages_failed: int = 0



class ClearChatResponse(BaseModel):
    ok: bool


class HealthResponse(BaseModel):
    status: str


class LoginRequest(BaseModel):
    username: str
    password: str
    role: str


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
    role: str

