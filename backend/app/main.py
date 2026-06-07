from __future__ import annotations

import sys
from pathlib import Path

if __package__ is None:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import os
import tempfile
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.database import engine, Base, get_db, SessionLocal
from app.models import User as DBUser
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user, get_admin_user
from app.schemas import (
    ChatRequest,
    ChatResponse,
    Citation,
    ClearChatResponse,
    HealthResponse,
    IngestResponse,
    LoginRequest,
    LoginResponse,
    UserResponse,
    UserCreateRequest,
)
from rag.ingestion.ingest_pipeline import IngestPipeline
from rag.ingestion.page_renderer import PageRenderer
from rag.ingestion.layout_detector import LayoutDetector
from rag.orchestrator.engine import RAGEngine

_engine: Optional[RAGEngine] = None


def get_engine() -> RAGEngine:
    global _engine
    if _engine is None:
        _engine = RAGEngine()
    return _engine


app = FastAPI(title="CapitalQuery API")

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

cache_dir = Path(__file__).resolve().parent.parent / "data" / "cache"
cache_dir.mkdir(parents=True, exist_ok=True)
app.mount("/cache", StaticFiles(directory=str(cache_dir)), name="cache")

@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(DBUser).count() == 0:
            admin_user = DBUser(
                username="admin",
                hashed_password=get_password_hash("admin123"),
                role="admin"
            )
            db.add(admin_user)
            db.commit()
            print("[Startup] Seeded default admin user 'admin' / 'admin123'")
    finally:
        db.close()



@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/auth/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(DBUser).filter(DBUser.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    if user.role != body.role:
        raise HTTPException(status_code=401, detail=f"User is not registered as {body.role}")
        
    access_token = create_access_token(data={"sub": user.username})
    created_at_ts = int(user.created_at.timestamp() * 1000)
    
    user_res = UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        createdAt=created_at_ts
    )
    return LoginResponse(
        access_token=access_token,
        user=user_res
    )


@app.get("/api/auth/me", response_model=UserResponse)
def get_me(current_user: DBUser = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        createdAt=int(current_user.created_at.timestamp() * 1000)
    )


@app.get("/api/users", response_model=list[UserResponse])
def get_users(
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_admin_user)
) -> list[UserResponse]:
    users = db.query(DBUser).all()
    return [
        UserResponse(
            id=u.id,
            username=u.username,
            role=u.role,
            createdAt=int(u.created_at.timestamp() * 1000)
        )
        for u in users
    ]


@app.post("/api/users", response_model=UserResponse)
def create_user(
    body: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_admin_user)
) -> UserResponse:
    existing = db.query(DBUser).filter(DBUser.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    new_user = DBUser(
        username=body.username,
        hashed_password=get_password_hash(body.password),
        role=body.role,
        created_by=current_user.id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        role=new_user.role,
        createdAt=int(new_user.created_at.timestamp() * 1000)
    )


@app.delete("/api/users/{user_id}", response_model=ClearChatResponse)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: DBUser = Depends(get_admin_user)
) -> ClearChatResponse:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own admin account")
        
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    db.delete(user)
    db.commit()
    return ClearChatResponse(ok=True)


@app.post("/api/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    current_user: DBUser = Depends(get_current_user)
) -> ChatResponse:
    engine = get_engine()
    result = engine.chat(
        body.message, 
        current_user_id=current_user.id, 
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
def clear_chat(current_user: DBUser = Depends(get_current_user)) -> ClearChatResponse:
    engine = get_engine()
    engine.clear_history()
    return ClearChatResponse(ok=True)


@app.post("/api/ingest", response_model=IngestResponse)
async def ingest(
    file: UploadFile = File(...),
    user_id: str = Form("guest"),
    session_id: str = Form("default_session"),
    is_persistent: bool = Form(False),
    allowed_users: str = Form(""),
    current_user: DBUser = Depends(get_current_user)
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
            owner_id=current_user.id,
            session_id=session_id,
            is_persistent=is_persistent,
            allowed_users=allowed_users_list
        )
        return IngestResponse(
            source=str(summary["source"]),
            pages_parsed=int(summary["pages_parsed"]),
            chunks_created=int(summary["chunks_created"]),
            chunks_indexed=int(summary["chunks_indexed"]),
            pages_failed=int(summary.get("pages_failed", 0)),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/session/end", response_model=ClearChatResponse)
def end_session(
    session_id: str = Form(...),
    current_user: DBUser = Depends(get_current_user)
) -> ClearChatResponse:
    engine = get_engine()
    deleted = engine.es_client.delete_session_chunks(session_id)
    print(f"Session {session_id} ended. Deleted {deleted} non-persistent chunks.")
    engine.clear_history()
    return ClearChatResponse(ok=True)


@app.post("/api/admin/layout-preview")
async def layout_preview(
    file: UploadFile = File(...),
    current_user: DBUser = Depends(get_admin_user)
) -> dict:
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Expected a PDF file")

    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp_path = tmp.name
            content = await file.read()
            tmp.write(content)
            
        renderer = PageRenderer()
        detector = LayoutDetector()
        
        pages = renderer.render(tmp_path)
        file_hash = renderer._compute_file_hash(tmp_path)
        
        response_pages = []
        for p in pages:
            regions = detector.detect(p["image"], p["page"])
            image_url = f"/cache/{file_hash}_p{p['page']}_dpi{renderer.dpi}.png"
            response_pages.append({
                "page_num": p["page"],
                "image_url": image_url,
                "width": p["width"],
                "height": p["height"],
                "regions": regions
            })
            
        return {"pages": response_pages}
        
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if tmp_path and os.path.isfile(tmp_path):
            os.unlink(tmp_path)

