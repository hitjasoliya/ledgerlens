from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)


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


class ClearChatResponse(BaseModel):
    ok: bool


class HealthResponse(BaseModel):
    status: str
