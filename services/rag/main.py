from __future__ import annotations
import logging
import sys
import uuid
from pathlib import Path
from typing import List, Optional

root_dir = Path(__file__).resolve().parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)

from fastapi import FastAPI, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session

from common.database import engine, Base, get_db
from common.models import ChatSessionModel, ChatMessageModel
from common.schemas import (
    ChatRequest,
    ChatResponse,
    ChatSessionResponse,
    ChatSessionCreate,
    ChatMessageResponse,
    Citation,
    ClearChatResponse,
    HealthResponse,
)
from common.auth import decode_access_token
try:
    from engine import RAGEngine
except ImportError:
    from services.rag.engine import RAGEngine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LedgerLens RAG Service")
rag_engine = RAGEngine()


def extract_user_credentials(
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
) -> tuple[str, str]:
    if x_user_id:
        return x_user_id, x_user_role or "employee"
    if authorization and authorization.startswith("Bearer "):
        try:
            token = authorization.split(" ")[1]
            payload = decode_access_token(token)
            user_id = payload.get("id") or payload.get("sub", "guest")
            user_role = payload.get("role", "employee")
            return user_id, user_role
        except Exception:
            pass
    return "guest", "employee"


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    auth_user_id, auth_user_role = extract_user_credentials(authorization, x_user_id, x_user_role)
    effective_user_id = body.user_id if (body.user_id and body.user_id != "guest") else auth_user_id

    res = rag_engine.chat(
        db=db,
        question=body.message,
        user_id=effective_user_id,
        user_role=auth_user_role,
        session_id=body.session_id or "default_session",
    )
    return ChatResponse(
        answer=res["answer"],
        citations=[Citation(**c) for c in res.get("citations", [])],
        chunks_used=res.get("chunks_used", 0),
    )


@app.get("/api/chat/sessions", response_model=List[ChatSessionResponse])
def get_sessions(
    user_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    auth_user_id, _ = extract_user_credentials(authorization, x_user_id, x_user_role)
    effective_user_id = user_id or auth_user_id

    sessions = (
        db.query(ChatSessionModel)
        .filter(ChatSessionModel.user_id == effective_user_id)
        .order_by(ChatSessionModel.updated_at.desc())
        .all()
    )
    res = []
    for s in sessions:
        ordered = sorted(s.messages, key=lambda m: m.created_at)
        msgs = [
            ChatMessageResponse(
                id=m.id,
                role=m.role,
                content=m.content,
                citations=[Citation(**c) for c in (m.citations or [])],
                created_at=int(m.created_at.timestamp() * 1000),
            )
            for m in ordered
        ]
        res.append(
            ChatSessionResponse(
                id=s.id,
                title=s.title,
                user_id=s.user_id,
                created_at=int(s.created_at.timestamp() * 1000),
                updated_at=int(s.updated_at.timestamp() * 1000),
                context_file_id=s.context_file_id,
                messages=msgs,
            )
        )
    return res


@app.post("/api/chat/sessions", response_model=ChatSessionResponse)
def create_session(
    body: ChatSessionCreate,
    user_id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    auth_user_id, _ = extract_user_credentials(authorization, x_user_id, x_user_role)
    effective_user_id = user_id or auth_user_id

    sess_id = str(uuid.uuid4())
    sess = ChatSessionModel(
        id=sess_id,
        user_id=effective_user_id,
        title=body.title or "New Chat",
        context_file_id=body.context_file_id,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)

    return ChatSessionResponse(
        id=sess.id,
        title=sess.title,
        user_id=sess.user_id,
        created_at=int(sess.created_at.timestamp() * 1000),
        updated_at=int(sess.updated_at.timestamp() * 1000),
        context_file_id=sess.context_file_id,
        messages=[],
    )


@app.get("/api/chat/sessions/{session_id}", response_model=ChatSessionResponse)
def get_session(session_id: str, db: Session = Depends(get_db)):
    sess = db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()
    if not sess:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )
    ordered = sorted(sess.messages, key=lambda m: m.created_at)
    msgs = [
        ChatMessageResponse(
            id=m.id,
            role=m.role,
            content=m.content,
            citations=[Citation(**c) for c in (m.citations or [])],
            created_at=int(m.created_at.timestamp() * 1000),
        )
        for m in ordered
    ]
    return ChatSessionResponse(
        id=sess.id,
        title=sess.title,
        user_id=sess.user_id,
        created_at=int(sess.created_at.timestamp() * 1000),
        updated_at=int(sess.updated_at.timestamp() * 1000),
        context_file_id=sess.context_file_id,
        messages=msgs,
    )


@app.post("/api/chat/clear", response_model=ClearChatResponse)
def clear_chat(session_id: str = "default_session", db: Session = Depends(get_db)):
    db.query(ChatMessageModel).filter(
        ChatMessageModel.session_id == session_id
    ).delete()
    db.commit()
    return ClearChatResponse(ok=True)


@app.post("/api/chat/delete", response_model=ClearChatResponse)
def delete_chat(session_id: str = "default_session", db: Session = Depends(get_db)):
    sess = db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()
    if sess:
        db.delete(sess)
        db.commit()
    return ClearChatResponse(ok=True)


@app.post("/api/session/end", response_model=ClearChatResponse)
def end_session(session_id: str = "default_session", db: Session = Depends(get_db)):
    return clear_chat(session_id=session_id, db=db)
