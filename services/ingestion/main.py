from __future__ import annotations

import asyncio
import datetime
import logging
import re
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

root_dir = Path(__file__).resolve().parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile
from sqlalchemy import and_, delete, func, or_, select, text, update
from sqlalchemy.orm import Session

from common.access import can_read, require_document
from common.auth import get_admin_user, get_current_user
from common.config import settings
from common.database import SessionLocal, get_db, initialize_database
from common.http import UploadBodyLimitMiddleware, configure_validation_errors, page_params
from common.migrate import ReindexRefused, queue_reindex
from common.models import Document, DocumentGrant, IngestionJob, User, utcnow
from common.schemas import (
    ClearChatResponse,
    DocumentResponse,
    EmbeddingsClearResponse,
    HealthResponse,
    IngestResponse,
    JobStatusResponse,
    Page,
    ResourceId,
    UpdateAccessRequest,
)

try:
    from pipeline import DocumentRejected, IngestionPipeline
except ImportError:
    from services.ingestion.pipeline import DocumentRejected, IngestionPipeline

logger = logging.getLogger(__name__)

pipeline = IngestionPipeline()
_stop_event = asyncio.Event()
_worker_trigger = asyncio.Event()
_worker_tasks: List[asyncio.Task] = []


def _format_timestamp_ms(dt: Optional[datetime.datetime]) -> int:
    if not dt:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def _sanitize_error_message(exc: Exception) -> str:
    if isinstance(exc, DocumentRejected):
        return str(exc)
    return f"Processing failed ({type(exc).__name__}); retry after the failing service recovers"


def _begin_write_lock(session: Session) -> None:
    """Acquire immediate exclusive write coordination lock across engines."""
    if session.bind.dialect.name == "sqlite":
        session.execute(text("BEGIN IMMEDIATE"))


class HeartbeatThread(threading.Thread):
    """Pulse worker claim lease while long blocking work is in flight."""

    def __init__(
        self,
        job_id: str,
        claim_token: str,
        interval: float,
        stop_event: threading.Event,
        abort_event: threading.Event,
    ) -> None:
        super().__init__(daemon=True)
        self.job_id = job_id
        self.claim_token = claim_token
        self.interval = max(1.0, interval)
        self.stop_event = stop_event
        self.abort_event = abort_event

    def run(self) -> None:
        while not self.stop_event.wait(self.interval):
            try:
                with SessionLocal() as s:
                    now = utcnow()
                    new_lease = now + datetime.timedelta(seconds=settings.JOB_LEASE_SECONDS)
                    res = s.execute(
                        update(IngestionJob)
                        .where(
                            IngestionJob.id == self.job_id,
                            IngestionJob.worker_id == self.claim_token,
                            IngestionJob.status == "processing",
                        )
                        .values(
                            lease_until=new_lease,
                            updated_at=now,
                        )
                    )
                    s.commit()
                    if res.rowcount == 0:
                        logger.warning("Heartbeat detected claim loss for job %s", self.job_id)
                        self.abort_event.set()
                        break
            except Exception as exc:
                logger.warning("Heartbeat tick failed for job %s: %s", self.job_id, exc)


def _cleanup_deleted_document(db: Session, document_id: str) -> tuple[int, int, bool]:
    _begin_write_lock(db)
    document = db.scalar(
        select(Document).where(Document.id == document_id).with_for_update()
    )
    if document is None:
        db.rollback()
        return 0, 0, True
    if document.status not in ("deleting", "cleanup_pending"):
        db.rollback()
        return 0, 0, False
    active = db.scalar(select(IngestionJob.id).where(
        IngestionJob.document_id == document_id, IngestionJob.lease_until > utcnow()
    ).limit(1))
    if active is not None:
        document.status = "cleanup_pending"
        document.error_message = "Cleanup pending while an ingestion worker drains"
        db.commit()
        return 0, 0, False

    chunks, files = 0, 0
    failed = False
    try:
        chunks = pipeline.es_client.delete_document_chunks(document_id)
    except Exception as exc:
        logger.warning("Search cleanup pending for %s (%s)", document_id, type(exc).__name__)
        failed = True
    try:
        root = settings.UPLOAD_DIR.resolve()
        path = (root / document.storage_path).resolve()
        if not document.storage_path or not path.is_relative_to(root):
            raise ValueError("Stored path requires reconciliation")
        if path.exists():
            path.unlink()
            files = 1
    except Exception as exc:
        logger.warning("Storage cleanup pending for %s (%s)", document_id, type(exc).__name__)
        failed = True
    if failed:
        document.status = "cleanup_pending"
        document.error_message = "Cleanup pending; restore search/storage or reconcile the stored path"
        db.commit()
        return chunks, files, False
    db.execute(delete(IngestionJob).where(IngestionJob.document_id == document_id))
    db.delete(document)
    db.commit()
    return chunks, files, True


def _process_reconcile_deletions(db: Session) -> bool:
    identifiers = list(db.scalars(
        select(Document.id).where(Document.status.in_(("deleting", "cleanup_pending")))
    ))
    db.rollback()
    completed = False
    for identifier in identifiers:
        _chunks, _files, removed = _cleanup_deleted_document(db, identifier)
        completed = completed or removed
    return completed


def _claim_next_job(db: Session, worker_instance_id: str) -> Optional[Tuple[str, str, int]]:
    now = utcnow()
    candidates = list(db.execute(
        select(IngestionJob.id, IngestionJob.document_id).where(
            (IngestionJob.status == "queued")
            | ((IngestionJob.status == "processing") & (IngestionJob.lease_until < now))
        ).order_by(IngestionJob.created_at, IngestionJob.id).limit(10)
    ))
    db.rollback()
    for job_id, document_id in candidates:
        _begin_write_lock(db)
        document = db.scalar(
            select(Document).where(Document.id == document_id).with_for_update()
        )
        job = db.scalar(select(IngestionJob).where(IngestionJob.id == job_id).with_for_update())
        now = utcnow()
        if job is None or not (
            job.status == "queued"
            or (job.status == "processing" and job.lease_until is not None and job.lease_until < now)
        ):
            db.rollback()
            continue
        if document is None or document.status in ("deleting", "cleanup_pending"):
            job.status, job.stage = "failed", "cancelled"
            job.lease_until = None
            db.commit()
            continue
        if job.attempts >= 3:
            job.status = document.status = "failed"
            job.stage = "failed"
            job.error_message = document.error_message = "Worker recovery limit reached; explicitly reindex"
            job.lease_until = None
            db.commit()
            continue
        if job.status == "processing":
            # A crashed process may have an ES request still in flight. A new
            # version fences its output out of every subsequent retrieval.
            document.version += 1
            job.document_version = document.version
            document.chunks_indexed = 0
        elif job.document_version != document.version:
            job.status, job.stage = "failed", "superseded"
            db.commit()
            continue
        token = f"{worker_instance_id}:{uuid.uuid4().hex}"
        job.status, job.stage, job.worker_id = "processing", "claimed", token
        job.lease_until = now + datetime.timedelta(seconds=settings.JOB_LEASE_SECONDS)
        job.attempts += 1
        job.updated_at = now
        document.status = "processing"
        version = document.version
        db.commit()
        return job_id, token, version
    return None


def _execute_job(job_id: str, claim_token: str, expected_version: int) -> None:
    """Execute all ingestion stages with continuous heartbeat, fencing, and locked publication."""
    with SessionLocal() as db:
        job = db.get(IngestionJob, job_id)
        if not job or not job.document_id or job.worker_id != claim_token:
            return

        doc = db.get(Document, job.document_id)
        if not doc or doc.status in ("deleting", "cleanup_pending") or doc.version != expected_version:
            job.status = "failed"
            job.stage = "cancelled"
            job.error_message = "Document was deleted, cancelled, or superseded"
            job.updated_at = utcnow()
            db.commit()
            return

        doc_id = doc.id
        doc_filename = doc.filename
        storage_path = doc.storage_path
        doc.status = "processing"
        db.commit()

    heartbeat_stop = threading.Event()
    heartbeat_abort = threading.Event()
    pulse_interval = max(1.0, settings.JOB_LEASE_SECONDS / 3.0)
    heartbeat_thread = HeartbeatThread(
        job_id=job_id,
        claim_token=claim_token,
        interval=pulse_interval,
        stop_event=heartbeat_stop,
        abort_event=heartbeat_abort,
    )
    heartbeat_thread.start()

    def update_stage(stage_name: str, pages: int = 0, chunks_created: int = 0, chunks_indexed: int = 0) -> bool:
        if heartbeat_abort.is_set():
            return False
        with SessionLocal() as s:
            res = s.execute(
                update(IngestionJob)
                .where(
                    IngestionJob.id == job_id,
                    IngestionJob.worker_id == claim_token,
                    IngestionJob.status == "processing",
                )
                .values(
                    stage=stage_name,
                    lease_until=utcnow() + datetime.timedelta(seconds=settings.JOB_LEASE_SECONDS),
                    updated_at=utcnow(),
                    pages_parsed=pages if pages else IngestionJob.pages_parsed,
                    chunks_created=chunks_created if chunks_created else IngestionJob.chunks_created,
                    chunks_indexed=chunks_indexed if chunks_indexed else IngestionJob.chunks_indexed,
                )
            )
            s.commit()
            return res.rowcount == 1

    try:
        # Stage 1: Parsing in killable child process
        if not update_stage("parsing"):
            return

        file_path = (settings.UPLOAD_DIR / storage_path).resolve()
        if not file_path.is_file():
            raise FileNotFoundError("Source PDF file not found in storage")

        items, pages_parsed = pipeline.parse_pdf(str(file_path))
        if pages_parsed == 0 or not items:
            raise ValueError("Zero pages or usable items extracted from document")

        # Stage 2: Chunking with real tokenizer and honest provenance
        if not update_stage("chunking", pages=pages_parsed):
            return

        chunks = pipeline.chunker.chunk_items(
            items=items,
            filename=doc_filename,
            document_id=doc_id,
            version=expected_version,
        )
        if not chunks:
            raise ValueError("Docling chunker produced zero chunks from document")

        # Stage 3: Embedding
        if not update_stage("embedding", pages=pages_parsed, chunks_created=len(chunks)):
            return

        texts = [c["text"] for c in chunks]
        embeddings = pipeline.embedder.embed_batch(texts)
        if len(embeddings) != len(chunks):
            raise ValueError("Embedding provider returned an incomplete batch")

        for chunk, emb in zip(chunks, embeddings):
            chunk["vector"] = emb
            chunk["embedding_model"] = pipeline.embedder.model

        if not update_stage("indexing", pages=pages_parsed, chunks_created=len(chunks)):
            return
        # Stage 4 & 5: Indexing and Atomic CAS Publication under Exclusive Lock
        # Acquire coordination lock BEFORE indexing to fence late writes and prevent orphans
        with SessionLocal() as s:
            _begin_write_lock(s)

            locked_doc = s.scalars(
                select(Document).where(Document.id == doc_id).with_for_update()
            ).first()
            locked_job = s.scalars(
                select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
            ).first()

            if (
                locked_doc is None
                or locked_doc.status in ("deleting", "cleanup_pending")
                or locked_doc.version != expected_version
                or locked_job is None
                or locked_job.worker_id != claim_token
                or locked_job.status != "processing"
                or heartbeat_abort.is_set()
            ):
                s.rollback()
                return


            # Perform indexing while holding coordination lock
            indexed_count = pipeline.es_client.upsert_chunks(chunks, dims=pipeline.embedder.dims)
            if indexed_count != len(chunks):
                s.rollback()
                raise ValueError(f"Indexed chunk count mismatch: {indexed_count} != {len(chunks)}")

            # Atomic CAS publication
            doc_cas = s.execute(
                update(Document)
                .where(
                    Document.id == doc_id,
                    Document.status == "processing",
                    Document.version == expected_version,
                )
                .values(
                    status="searchable",
                    pages_parsed=pages_parsed,
                    chunks_created=len(chunks),
                    chunks_indexed=indexed_count,
                    parser="docling",
                    embedding_model=pipeline.embedder.model,
                    embedding_dims=pipeline.embedder.dims,
                    error_message=None,
                )
            )
            if doc_cas.rowcount != 1:
                s.rollback()
                _safe_rollback_chunks(doc_id, expected_version)
                return

            job_cas = s.execute(
                update(IngestionJob)
                .where(
                    IngestionJob.id == job_id,
                    IngestionJob.worker_id == claim_token,
                    IngestionJob.status == "processing",
                )
                .values(
                    status="completed",
                    stage="completed",
                    pages_parsed=pages_parsed,
                    chunks_created=len(chunks),
                    chunks_indexed=indexed_count,
                    lease_until=None,
                    error_message=None,
                    updated_at=utcnow(),
                )
            )
            if job_cas.rowcount != 1:
                s.rollback()
                _safe_rollback_chunks(doc_id, expected_version)
                return

            s.commit()

        heartbeat_stop.set()
        heartbeat_thread.join(timeout=2.0)

    except Exception as exc:
        heartbeat_stop.set()
        heartbeat_thread.join(timeout=2.0)
        clean_err = _sanitize_error_message(exc)
        # Operators need the cause; users only ever see the sanitized message.
        logger.error("Job %s execution failed: %s: %s", job_id, type(exc).__name__, exc, exc_info=exc)

        with SessionLocal() as s:
            _begin_write_lock(s)
            locked_job = s.scalars(
                select(IngestionJob).where(IngestionJob.id == job_id).with_for_update()
            ).first()
            if locked_job and locked_job.worker_id == claim_token and locked_job.status == "processing":
                locked_job.status = "failed"
                locked_job.error_message = f"{locked_job.stage}: {clean_err}"
                locked_job.lease_until = None

                locked_doc = s.scalars(
                    select(Document).where(Document.id == doc_id).with_for_update()
                ).first()
                if locked_doc and locked_doc.status not in ("deleting", "cleanup_pending"):
                    locked_doc.status = "failed"
                    locked_doc.error_message = locked_job.error_message
                s.commit()
    finally:
        heartbeat_stop.set()
        heartbeat_thread.join()
        with SessionLocal() as acknowledgement:
            acknowledgement.execute(update(IngestionJob).where(
                IngestionJob.id == job_id, IngestionJob.worker_id == claim_token,
                IngestionJob.stage == "cancelled",
            ).values(lease_until=None, worker_id=None))
            acknowledgement.commit()


def _safe_rollback_chunks(doc_id: str, expected_version: int) -> None:
    """Roll back ES chunks only if document has not been superseded by a newer version."""
    try:
        with SessionLocal() as s:
            cur = s.get(Document, doc_id)
            if cur and cur.version > expected_version:
                return  # Newer version exists; do not delete newer chunks
        pipeline.es_client.delete_document_chunks(doc_id, version=expected_version)
    except Exception as exc:
        logger.warning("Rollback chunk deletion failed for doc %s: %s", doc_id, exc)


def _worker_sync_step(worker_instance_id: str) -> bool:
    """Single synchronous worker step: reconcile deletions or claim & execute job."""
    with SessionLocal() as db:
        if _process_reconcile_deletions(db):
            return True

        claimed = _claim_next_job(db, worker_instance_id)

    if claimed:
        job_id, claim_token, version = claimed
        _execute_job(job_id, claim_token, version)
        return True
    return False


async def _worker_loop(worker_instance_id: str) -> None:
    """Continuous durable background worker loop with globally unique ID."""
    logger.info("Ingestion worker %s started", worker_instance_id)
    while not _stop_event.is_set():
        try:
            acted = await asyncio.to_thread(_worker_sync_step, worker_instance_id)
            if not acted:
                try:
                    await asyncio.wait_for(
                        _worker_trigger.wait(),
                        timeout=settings.WORKER_POLL_SECONDS,
                    )
                    _worker_trigger.clear()
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Ingestion worker %s failed (%s)", worker_instance_id, type(exc).__name__)
            await asyncio.sleep(settings.WORKER_POLL_SECONDS)
    logger.info("Ingestion worker %s stopped", worker_instance_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()

    _stop_event.clear()
    _worker_tasks.clear()
    for _ in range(settings.INGESTION_WORKERS):
        unique_worker_id = f"worker-{uuid.uuid4().hex}"
        task = asyncio.create_task(_worker_loop(unique_worker_id))
        _worker_tasks.append(task)
    logger.info("Started %d background ingestion worker(s)", len(_worker_tasks))

    yield

    logger.info("Stopping ingestion workers...")
    _stop_event.set()
    _worker_trigger.set()
    await asyncio.gather(*_worker_tasks)
    pipeline.close()
    logger.info("Ingestion workers stopped and pipeline closed")



app = FastAPI(title="LedgerLens Ingestion Service", lifespan=lifespan)
configure_validation_errors(app)
app.add_middleware(UploadBodyLimitMiddleware)


@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")


@app.get("/ready")
def ready(db: Session = Depends(get_db)):
    failures = []
    # 1. SQL Database
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        failures.append("SQL database unavailable")

    # 2. Redis
    try:
        from common.auth import get_redis_client
        get_redis_client().ping()
    except Exception as exc:
        failures.append("Redis unavailable")

    # 3. Elasticsearch
    try:
        if not pipeline.es_client.is_available():
            failures.append("Elasticsearch unavailable")
    except Exception as exc:
        failures.append("Elasticsearch unavailable")

    # 4. Docling Parser
    try:
        if not pipeline.is_converter_available():
            failures.append("Docling parser unavailable")
    except Exception as exc:
        failures.append("Docling unavailable")
    if not pipeline.embedder.is_available():
        failures.append("Configured embedding model unavailable")

    if failures:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "unavailable", "failures": failures},
        )
    return {"status": "ready"}


@app.post("/api/documents", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uploader_id = current_user.id
    async with request.form(max_files=1, max_fields=0) as form:
        if set(form) != {"file"}:
            raise HTTPException(status_code=400, detail="Only one 'file' upload is accepted")
        file = form["file"]
        if not isinstance(file, UploadFile):
            raise HTTPException(status_code=400, detail="Multipart 'file' must be a PDF upload")
        filename = file.filename or ""
        if (
            not filename
            or not filename.lower().endswith(".pdf")
            or any(character in filename for character in ("\0", "/", "\\"))
            or ".." in filename
            or any(ord(character) < 32 for character in filename)
            or len(filename) > 255
        ):
            raise HTTPException(status_code=400, detail="Invalid or unsafe PDF filename")

        basename = f"{uuid.uuid4().hex}.pdf"
        target = settings.UPLOAD_DIR / basename
        succeeded = False
        try:
            size = 0
            signature = bytearray()
            with target.open("xb") as stored:
                while chunk := await file.read(settings.UPLOAD_READ_BYTES):
                    size += len(chunk)
                    if size > settings.UPLOAD_MAX_BYTES:
                        raise HTTPException(status_code=413, detail="PDF exceeds the allowed file size")
                    if len(signature) < 5:
                        signature.extend(chunk[:5 - len(signature)])
                    stored.write(chunk)
            if signature != b"%PDF-":
                raise HTTPException(status_code=400, detail="Uploaded file is not a PDF")

            try:
                import pypdfium2 as pdfium
                pdf = pdfium.PdfDocument(str(target))
                try:
                    page_count = len(pdf)
                finally:
                    pdf.close()
                if page_count == 0:
                    raise ValueError("Empty PDF")
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid or unreadable PDF") from None
            if page_count > settings.UPLOAD_MAX_PAGES:
                raise HTTPException(
                    status_code=413,
                    detail=f"PDF has {page_count} pages; the limit is {settings.UPLOAD_MAX_PAGES}",
                )

            _begin_write_lock(db)
            uploader = db.scalars(
                select(User).where(User.id == uploader_id).with_for_update()
            ).first()
            if uploader is None or uploader.role not in ("admin", "employee"):
                raise HTTPException(status_code=401, detail="Account is not active")
            document_id = str(uuid.uuid4())
            job_id = str(uuid.uuid4())
            document = Document(
                id=document_id,
                filename=filename,
                source=f"/api/documents/{document_id}/source",
                uploaded_by_id=uploader.id,
                owner_id=uploader.id,
                access_list=[],
                storage_path=basename,
                status="queued",
                version=1,
            )
            job = IngestionJob(
                id=job_id, document_id=document_id, filename=filename,
                status="queued", stage="queued", document_version=1,
            )
            db.add_all([document, job])
            db.commit()
            succeeded = True
            _worker_trigger.set()
            return IngestResponse(
                source=filename, id=document_id, job_id=job_id,
                pages_parsed=0, chunks_created=0, chunks_indexed=0,
            )
        finally:
            if not succeeded:
                db.rollback()
                target.unlink(missing_ok=True)


@app.get("/api/jobs/{job_id}", response_model=JobStatusResponse)
def get_job_status(
    job_id: ResourceId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    job = db.get(IngestionJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    if job.document_id:
        doc = db.get(Document, job.document_id)
        if not doc or not can_read(current_user, doc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    elif current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")

    return JobStatusResponse(
        job_id=job.id,
        status=job.status,
        stage=job.stage,
        error_message=job.error_message,
        pages_parsed=job.pages_parsed,
        chunks_created=job.chunks_created,
        chunks_indexed=job.chunks_indexed,
        document_id=job.document_id,
    )


def _document_response(db: Session, doc: Document, usernames: Optional[dict] = None) -> DocumentResponse:
    if usernames is None:
        uploader = db.get(User, doc.uploaded_by_id)
        usernames = {doc.uploaded_by_id: uploader.username} if uploader else {}
    return DocumentResponse(
        id=doc.id,
        filename=doc.filename,
        source=doc.source,
        uploaded_by_id=doc.uploaded_by_id,
        uploaded_by=usernames.get(doc.uploaded_by_id, "unknown"),
        owner_id=doc.owner_id,
        uploaded_at=_format_timestamp_ms(doc.uploaded_at),
        access_list=doc.access_list,
        pages_parsed=doc.pages_parsed,
        chunks_created=doc.chunks_created,
        chunks_indexed=doc.chunks_indexed,
        status=doc.status,
        parser=doc.parser,
        embedding_model=doc.embedding_model,
        embedding_dims=doc.embedding_dims,
        error_message=doc.error_message,
    )


@app.get("/api/documents", response_model=Page[DocumentResponse])
def list_documents(
    page: tuple[int, int] = Depends(page_params),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Documents the caller may read: admins see all, others their own and shared ones."""
    limit, offset = page
    visible = Document.status.not_in(["deleting", "cleanup_pending"])
    if current_user.role != "admin":
        visible = and_(visible, or_(
            Document.owner_id == current_user.id,
            Document.grants.any(DocumentGrant.user_id == current_user.id),
        ))
    total = db.scalar(select(func.count()).select_from(Document).where(visible)) or 0
    docs = db.scalars(
        select(Document).where(visible)
        .order_by(Document.uploaded_at.desc(), Document.id)
        .limit(limit).offset(offset)
    ).all()
    uploader_ids = {d.uploaded_by_id for d in docs}
    usernames = dict(db.execute(
        select(User.id, User.username).where(User.id.in_(uploader_ids))
    ).all()) if uploader_ids else {}
    return Page[DocumentResponse](
        items=[_document_response(db, d, usernames) for d in docs],
        total=total, limit=limit, offset=offset,
    )


@app.get("/api/documents/{document_id}/source")
def get_document_source(
    document_id: ResourceId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = require_document(db, document_id, current_user, searchable=False)

    file_path = (settings.UPLOAD_DIR / doc.storage_path).resolve()
    if not file_path.is_relative_to(settings.UPLOAD_DIR.resolve()) or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document file not found",
        )

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=doc.filename,
    )


@app.put("/api/documents/{document_id}/access", response_model=DocumentResponse)
def update_document_access(
    document_id: ResourceId,
    body: UpdateAccessRequest,
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc or doc.status in ("deleting", "cleanup_pending"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    recipient_ids = list(dict.fromkeys(body.access_list))
    if recipient_ids:
        valid_users = db.scalars(select(User).where(User.id.in_(recipient_ids))).all()
        valid_ids = {u.id for u in valid_users}
        invalid = [uid for uid in recipient_ids if uid not in valid_ids]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid recipient ID(s): {', '.join(invalid)}",
            )

    doc.access_list = recipient_ids
    db.commit()
    db.refresh(doc)
    return _document_response(db, doc)


@app.post("/api/documents/{document_id}/reindex", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
def reindex_document(
    document_id: ResourceId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Parse a document again, e.g. after a failure. Owners and admins only."""
    _begin_write_lock(db)
    doc = db.scalars(select(Document).where(Document.id == document_id).with_for_update()).first()
    if not doc or not can_read(current_user, doc) or (
        current_user.role != "admin" and doc.owner_id != current_user.id
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    try:
        job = queue_reindex(db, doc)
    except ReindexRefused as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None
    db.commit()
    _worker_trigger.set()
    return IngestResponse(
        source=doc.filename, id=doc.id, job_id=job.id,
        pages_parsed=0, chunks_created=0, chunks_indexed=0,
    )


@app.delete("/api/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: ResourceId,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _begin_write_lock(db)
    doc = db.scalars(
        select(Document).where(Document.id == document_id).with_for_update()
    ).first()
    if not doc or doc.status in ("deleting", "cleanup_pending"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    if current_user.role != "admin" and doc.owner_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Immediate access denial while preserving active lease_until proof
    doc.status = "deleting"
    db.execute(
        update(IngestionJob)
        .where(
            IngestionJob.document_id == doc.id,
            IngestionJob.status.in_(["queued", "processing"]),
        )
        .values(
            status="failed",
            stage="cancelled",
            error_message="Document deleted",
            updated_at=utcnow(),
        )
    )
    db.commit()

    _chunks, _files, complete = _cleanup_deleted_document(db, document_id)
    if not complete:
        raise HTTPException(status_code=503, detail="Document is unavailable; physical cleanup remains pending")


@app.delete("/api/documents", response_model=EmbeddingsClearResponse)
def delete_all_documents(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    _begin_write_lock(db)
    documents = list(db.scalars(select(Document).order_by(Document.id).with_for_update()))
    identifiers = [document.id for document in documents]
    for document in documents:
        document.status = "deleting"
    if identifiers:
        db.execute(update(IngestionJob).where(
            IngestionJob.document_id.in_(identifiers),
            IngestionJob.status.in_(("queued", "processing")),
        ).values(status="failed", stage="cancelled", error_message="Store wipe", updated_at=utcnow()))
    db.commit()
    deleted_chunks, files_deleted, pending = 0, 0, 0
    for identifier in identifiers:
        chunks, files, complete = _cleanup_deleted_document(db, identifier)
        deleted_chunks += chunks
        files_deleted += files
        pending += not complete
    if pending:
        raise HTTPException(status_code=503, detail="Store access removed; physical cleanup remains pending")
    return EmbeddingsClearResponse(ok=True, deleted=deleted_chunks, files_deleted=files_deleted)
