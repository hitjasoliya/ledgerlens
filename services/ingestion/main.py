from __future__ import annotations
import logging
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

root_dir = Path(__file__).resolve().parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form, Header
from sqlalchemy.orm import Session

from common.database import engine, SessionLocal, Base, get_db
from common.models import Document, IngestionJob, User
from common.schemas import (
    IngestResponse,
    JobStatusResponse,
    DocumentResponse,
    UpdateAccessRequest,
    ClearChatResponse,
    EmbeddingsClearResponse,
    HealthResponse,
)
from common.auth import decode_access_token
try:
    from pipeline import IngestionPipeline
except ImportError:
    from services.ingestion.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)
pipeline = IngestionPipeline()
executor = ThreadPoolExecutor(max_workers=4)

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="LedgerLens Ingestion Service")


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


def run_ingestion_background(
    job_id: str,
    pdf_path: str,
    filename: str,
    document_id: str,
    allowed_users: List[str],
    scope: str,
    is_persistent: bool,
    session_id: Optional[str],
):
    db = SessionLocal()
    try:
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if job:
            job.status = "processing"
            db.commit()

        result = pipeline.process(
            pdf_path=pdf_path,
            filename=filename,
            document_id=document_id,
            allowed_users=allowed_users,
            scope=scope,
            is_persistent=is_persistent,
            session_id=session_id,
        )

        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc:
            doc.pages_parsed = result["pages_parsed"]
            doc.chunks_created = result["chunks_created"]
            doc.chunks_indexed = result["chunks_indexed"]

        if job:
            job.status = "completed"
            job.pages_parsed = result["pages_parsed"]
            job.chunks_created = result["chunks_created"]
            job.chunks_indexed = result["chunks_indexed"]
            db.commit()

    except Exception as exc:
        logger.error(f"Ingestion job {job_id} failed: {exc}")
        job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.error_message = str(exc)
            db.commit()
    finally:
        db.close()


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.post("/api/ingest", response_model=IngestResponse, status_code=202)
async def ingest(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    user_role: Optional[str] = Form(None),
    scope: str = Form("employee"),
    is_persistent: str = Form("true"),
    session_id: str = Form("default_session"),
    allowed_users: str = Form(""),
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported",
        )

    auth_user_id, auth_user_role = extract_user_credentials(authorization, x_user_id, x_user_role)
    effective_user_id = user_id or auth_user_id
    effective_user_role = user_role or auth_user_role

    doc_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())

    persistent_bool = is_persistent.lower() == "true"
    save_path = UPLOAD_DIR / f"{doc_id}_{file.filename}"

    with open(save_path, "wb") as f:
        content = await file.read()
        f.write(content)

    # Comma-separated access list from the client, e.g. "admin_persistent" uploads
    requested = [u.strip() for u in allowed_users.split(",") if u.strip()]
    allowed = list(dict.fromkeys([effective_user_id] + requested))
    if effective_user_id == "guest":
        allowed = requested

    # Create DB records
    doc = Document(
        id=doc_id,
        filename=file.filename,
        source=file.filename,
        uploaded_by_id=effective_user_id,
        scope=scope,
        access_list=allowed,
        is_persistent=persistent_bool,
        session_id=session_id,
    )
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        filename=file.filename,
        status="pending",
    )
    db.add(doc)
    db.add(job)
    db.commit()

    # Enqueue background task
    executor.submit(
        run_ingestion_background,
        job_id=job_id,
        pdf_path=str(save_path),
        filename=file.filename,
        document_id=doc_id,
        allowed_users=allowed,
        scope=scope,
        is_persistent=persistent_bool,
        session_id=session_id,
    )

    return IngestResponse(
        source=file.filename,
        pages_parsed=0,
        chunks_created=0,
        chunks_indexed=0,
        id=doc_id,
        job_id=job_id,
    )


@app.get("/api/ingest/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(IngestionJob).filter(IngestionJob.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found",
        )
    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        pages_parsed=job.pages_parsed,
        chunks_created=job.chunks_created,
        chunks_indexed=job.chunks_indexed,
        error_message=job.error_message,
        document_id=job.document_id,
    )


@app.delete("/api/embeddings", response_model=EmbeddingsClearResponse)
def clear_embeddings(db: Session = Depends(get_db)):
    """Wipe the whole document store: ES chunks, uploaded files, and DB records."""
    deleted = pipeline.es_client.delete_all_chunks()

    files_deleted = 0
    for f in UPLOAD_DIR.iterdir():
        if f.is_file():
            try:
                f.unlink(missing_ok=True)
                files_deleted += 1
            except Exception as exc:
                logger.warning(f"Could not delete upload file {f.name}: {exc}")

    docs_deleted = db.query(Document).delete()
    jobs_deleted = db.query(IngestionJob).delete()
    db.commit()
    logger.info(
        "Cleared document store: %d chunks, %d files, %d docs, %d jobs",
        deleted, files_deleted, docs_deleted, jobs_deleted,
    )
    return EmbeddingsClearResponse(
        ok=True,
        deleted=deleted,
        files_deleted=files_deleted,
    )


def _latest_jobs(db: Session) -> Dict[str, IngestionJob]:
    """Map document_id -> most recent ingestion job."""
    latest: Dict[str, IngestionJob] = {}
    for job in db.query(IngestionJob).all():
        if not job.document_id:
            continue
        prev = latest.get(job.document_id)
        if prev is None or job.created_at > prev.created_at:
            latest[job.document_id] = job
    return latest


def _index_status(doc: Document, latest_jobs: Dict[str, IngestionJob]) -> tuple[str, Optional[str]]:
    job = latest_jobs.get(doc.id)
    if job:
        return job.status, job.error_message
    if doc.chunks_indexed > 0:
        return "completed", None
    return "unknown", None


@app.get("/api/documents", response_model=List[DocumentResponse])
def get_documents(
    user_id: Optional[str] = None,
    user_role: Optional[str] = None,
    session_id: str = "default_session",
    authorization: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    x_user_role: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    auth_user_id, auth_user_role = extract_user_credentials(authorization, x_user_id, x_user_role)
    effective_user_id = user_id or auth_user_id
    effective_user_role = user_role or auth_user_role

    docs = db.query(Document).all()
    latest_jobs = _latest_jobs(db)
    res = []
    for doc in docs:
        if (
            effective_user_role == "admin"
            or doc.scope == "employee"
            or effective_user_id in (doc.access_list or [])
            or doc.session_id == session_id
        ):
            index_status, job_error = _index_status(doc, latest_jobs)
            res.append(
                DocumentResponse(
                    id=doc.id,
                    filename=doc.filename,
                    source=doc.source,
                    uploaded_by_id=doc.uploaded_by_id,
                    uploaded_by=doc.uploaded_by_id,
                    uploaded_at=int(doc.uploaded_at.timestamp() * 1000),
                    scope=doc.scope,
                    access_list=doc.access_list or [],
                    pages_parsed=doc.pages_parsed,
                    chunks_created=doc.chunks_created,
                    chunks_indexed=doc.chunks_indexed,
                    is_persistent=doc.is_persistent,
                    session_id=doc.session_id,
                    index_status=index_status,
                    job_error=job_error,
                )
            )
    return res


@app.put("/api/documents/{document_id}/access", response_model=DocumentResponse)
def update_document_access(
    document_id: str,
    body: UpdateAccessRequest,
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    doc.access_list = body.access_list
    db.commit()
    db.refresh(doc)

    index_status, job_error = _index_status(doc, _latest_jobs(db))
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        source=doc.source,
        uploaded_by_id=doc.uploaded_by_id,
        uploaded_by=doc.uploaded_by_id,
        uploaded_at=int(doc.uploaded_at.timestamp() * 1000),
        scope=doc.scope,
        access_list=doc.access_list or [],
        pages_parsed=doc.pages_parsed,
        chunks_created=doc.chunks_created,
        chunks_indexed=doc.chunks_indexed,
        is_persistent=doc.is_persistent,
        session_id=doc.session_id,
        index_status=index_status,
        job_error=job_error,
    )


@app.delete("/api/documents/{document_id}", response_model=ClearChatResponse)
def delete_document(document_id: str, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Delete ES vector chunks
    try:
        pipeline.es_client.delete_document_chunks(doc.id)
    except Exception as exc:
        logger.warning(f"Could not delete vector chunks for {doc.id}: {exc}")

    # Delete stored file on disk if exists
    for f in UPLOAD_DIR.glob(f"{doc.id}_*"):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass

    db.delete(doc)
    db.commit()
    return ClearChatResponse(ok=True)
