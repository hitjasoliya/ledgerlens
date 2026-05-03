from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import tempfile
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    ClearChatResponse,
    HealthResponse,
    IngestResponse,
)
from rag.ingestion.ingest_pipeline import IngestPipeline
from rag.orchestrator.engine import RAGEngine

_engine: Optional[RAGEngine] = None


def get_engine() -> RAGEngine:
    global _engine
    if _engine is None:
        _engine = RAGEngine()
    return _engine


app = FastAPI(title="RAG Adani API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/chat", response_model=ChatResponse)
def chat(body: ChatRequest) -> ChatResponse:
    engine = get_engine()
    result = engine.chat(
        body.message, 
        current_user_id=body.user_id, 
        current_session_id=body.session_id
    )
    cites_raw = result.get("citations") or []
    citations = [
        Citation(page=int(c["page"]), chunk_id=str(c["chunk_id"]))
        for c in cites_raw
    ]
    return ChatResponse(
        answer=str(result.get("answer", "")),
        citations=citations,
        chunks_used=int(result.get("chunks_used", 0)),
    )


@app.post("/api/chat/clear", response_model=ClearChatResponse)
def clear_chat() -> ClearChatResponse:
    engine = get_engine()
    engine.clear_history()
    return ClearChatResponse(ok=True)


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(...),
    user_id: str = Form("guest"),
    session_id: str = Form("default_session"),
    is_persistent: bool = Form(False),
    allowed_users: str = Form("")
) -> IngestResponse:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a PDF file")

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)

        pipeline = IngestPipeline()
        allowed_users_list = [u.strip() for u in allowed_users.split(",") if u.strip()]
        summary = pipeline.run(
            tmp_path,
            owner_id=user_id,
            session_id=session_id,
            is_persistent=is_persistent,
            allowed_users=allowed_users_list
        )
        return IngestResponse(
            source=str(summary["source"]),
            pages_parsed=int(summary["pages_parsed"]),
            chunks_created=int(summary["chunks_created"]),
            chunks_indexed=int(summary["chunks_indexed"]),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/session/end", response_model=ClearChatResponse)
def end_session(session_id: str = Form(...)) -> ClearChatResponse:
    engine = get_engine()
    deleted = engine.es_client.delete_session_chunks(session_id)
    print(f"Session {session_id} ended. Deleted {deleted} non-persistent chunks.")
    engine.clear_history()
    return ClearChatResponse(ok=True)
