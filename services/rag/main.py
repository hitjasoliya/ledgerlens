from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, status
import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from common.auth import get_current_user, get_redis_client
from common.config import settings
from common.http import configure_validation_errors, page_params
import common.database
from common.database import get_db
from common.models import User
from common.schemas import (
    ChatMessageRequest,
    ChatResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    ChatSessionSummary,
    HealthResponse,
    Page,
    RegenerateRequest,
    ResourceId,
)

try:
    from engine import RAGEngine
except ImportError:
    from services.rag.engine import RAGEngine

logger = logging.getLogger(__name__)

rag_engine = RAGEngine()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if hasattr(common.database, "initialize_database"):
        common.database.initialize_database()
    yield
    rag_engine.close()



app = FastAPI(title="LedgerLens RAG Service", lifespan=lifespan)
configure_validation_errors(app)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    status_details = {}
    is_ready = True

    # 1. SQL Database probe
    try:
        db.execute(text("SELECT 1"))
        status_details["database"] = "connected"
    except Exception as exc:
        logger.warning("Database readiness probe failed: %s", type(exc).__name__)
        status_details["database"] = "unavailable"
        is_ready = False

    # 2. Redis revocation probe
    try:
        redis_client = get_redis_client()
        redis_client.ping()
        status_details["redis"] = "connected"
    except Exception as exc:
        logger.warning("Redis readiness probe failed: %s", type(exc).__name__)
        status_details["redis"] = "unavailable"
        is_ready = False

    # 3. Elasticsearch probe
    try:
        if rag_engine.es_client.is_available():
            status_details["elasticsearch"] = "connected"
        else:
            status_details["elasticsearch"] = "unavailable"
            is_ready = False
    except Exception as exc:
        logger.warning("Elasticsearch readiness probe failed: %s", type(exc).__name__)
        status_details["elasticsearch"] = "unavailable"
        is_ready = False

    if rag_engine.embedder.is_available():
        status_details["embedding_service"] = "available"
    else:
        status_details["embedding_service"] = "unavailable"
        is_ready = False

    # Metadata probes are not paid generation requests.
    if rag_engine.generator.is_available():
        status_details["gemini"] = "available"
    else:
        status_details["gemini"] = "unavailable"
        is_ready = False

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "degraded", "dependencies": status_details},
        )
    return {"status": "ready", "dependencies": status_details}


@app.get("/api/chat/sessions", response_model=Page[ChatSessionSummary])
def list_sessions(
    page: tuple[int, int] = Depends(page_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit, offset = page
    return rag_engine.list_sessions(db=db, current_user=current_user, limit=limit, offset=offset)


@app.post("/api/chat/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    body: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return rag_engine.create_session(
        db=db,
        title=body.title,
        selected_document_ids=body.selected_document_ids,
        current_user=current_user,
    )


@app.get("/api/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_session(
    session_id: ResourceId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return rag_engine.get_session(db=db, session_id=session_id, current_user=current_user)


@app.delete("/api/chat/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: ResourceId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rag_engine.delete_chat(db=db, session_id=session_id, current_user=current_user)


@app.post("/api/chat/sessions/{session_id}/messages", response_model=ChatResponse)
def send_message(
    session_id: ResourceId,
    body: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return rag_engine.chat(
        db=db, question=body.message, current_user=current_user, session_id=session_id
    )


@app.delete("/api/chat/sessions/{session_id}/messages", status_code=status.HTTP_204_NO_CONTENT)
def clear_messages(
    session_id: ResourceId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rag_engine.clear_chat(db=db, session_id=session_id, current_user=current_user)


@app.post("/api/chat/sessions/{session_id}/regenerate", response_model=ChatResponse)
def regenerate(
    session_id: ResourceId,
    body: RegenerateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return rag_engine.regenerate(
        db=db, session_id=session_id, message_id=body.message_id, current_user=current_user
    )
