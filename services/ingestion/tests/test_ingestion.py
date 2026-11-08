import datetime
import io
import sys
import threading
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

root_dir = Path(__file__).resolve().parent.parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from common.auth import create_access_token, get_password_hash
from common.config import settings
from common.database import SessionLocal, initialize_database
from common.models import Document, IngestionJob, User, utcnow
from services.ingestion.main import (
    HeartbeatThread,
    _claim_next_job,
    _execute_job,
    _process_reconcile_deletions,
    app as ingestion_app,
    pipeline,
)
from services.ingestion.pipeline import DoclingChunker, IngestionPipeline
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
import services.ingestion.main as ingestion_module
from common.migrate import ensure_current


def make_valid_pdf_bytes(text: str = "Test Financial Report Q3 2024 Revenue $50M") -> bytes:
    stream = f"BT /F1 12 Tf 50 700 Td ({text}) Tj ET".encode("ascii")
    length = len(stream)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length " + str(length).encode("ascii") + b" >> stream\n" + stream + b"\nendstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000244 00000 n \n"
        b"0000000320 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n395\n%%EOF"
    )


@pytest.fixture(scope="module")
def client():
    initialize_database()
    with patch.object(ingestion_module, "_worker_sync_step", return_value=False), TestClient(ingestion_app) as c:
        yield c


@pytest.fixture
def worker_db(tmp_path, monkeypatch):
    bind = create_engine(f"sqlite:///{tmp_path / 'worker.sqlite'}", connect_args={"check_same_thread": False})
    ensure_current(bind)
    factory = sessionmaker(bind=bind, autoflush=False)
    monkeypatch.setattr(ingestion_module, "SessionLocal", factory)
    with factory() as db:
        db.add(User(id="user-emp1-ingest", username="worker-owner", role="employee", hashed_password="unused"))
        db.commit()
        yield db
    bind.dispose()


@pytest.fixture(scope="module")
def seeded_users():
    initialize_database()
    db = SessionLocal()
    users_data = {
        "admin": {"id": "user-admin-ingest", "username": "admin_ingest", "role": "admin"},
        "emp1": {"id": "user-emp1-ingest", "username": "emp1_ingest", "role": "employee"},
        "emp2": {"id": "user-emp2-ingest", "username": "emp2_ingest", "role": "employee"},
        "emp3": {"id": "user-emp3-ingest", "username": "emp3_ingest", "role": "employee"},
    }

    for key, data in users_data.items():
        existing = db.get(User, data["id"])
        if not existing:
            u = User(
                id=data["id"],
                username=data["username"],
                hashed_password=get_password_hash("TestPassword123!"),
                role=data["role"],
            )
            db.add(u)
        else:
            existing.role = data["role"]
            existing.username = data["username"]
    db.commit()
    db.close()
    return users_data


@pytest.fixture(scope="module")
def admin_headers(seeded_users):
    u = seeded_users["admin"]
    token = create_access_token({"sub": u["username"], "id": u["id"], "role": u["role"]})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def emp1_headers(seeded_users):
    u = seeded_users["emp1"]
    token = create_access_token({"sub": u["username"], "id": u["id"], "role": u["role"]})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def emp2_headers(seeded_users):
    u = seeded_users["emp2"]
    token = create_access_token({"sub": u["username"], "id": u["id"], "role": u["role"]})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def emp3_headers(seeded_users):
    u = seeded_users["emp3"]
    token = create_access_token({"sub": u["username"], "id": u["id"], "role": u["role"]})
    return {"Authorization": f"Bearer {token}"}


def test_readiness_recovers_without_confusing_liveness(client):
    with patch.object(pipeline.es_client, "is_available", return_value=True), patch.object(
        pipeline, "is_converter_available", return_value=True
    ), patch.object(pipeline.embedder, "is_available", return_value=False) as embedding:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        embedding.return_value = True
        assert client.get("/ready").status_code == 200


def test_unauthenticated_and_forged_requests_denied(client):
    assert client.get("/api/documents").status_code == 401
    assert client.post("/api/documents").status_code == 401
    assert client.get("/api/jobs/job-1").status_code == 401
    assert client.get("/api/documents/doc-1/source").status_code == 401
    assert client.put("/api/documents/doc-1/access", json={"access_list": []}).status_code == 401
    assert client.delete("/api/documents/doc-1").status_code == 401
    assert client.delete("/api/documents").status_code == 401

    forged = {"Authorization": "Bearer forged.invalid.token"}
    assert client.get("/api/documents", headers=forged).status_code == 401
    assert client.delete("/api/documents/doc-1", headers=forged).status_code == 401


def test_upload_file_only_and_size_boundary(client, emp1_headers):
    # 1. Non-PDF extension rejected
    non_pdf = {"file": ("report.txt", b"plain text report", "text/plain")}
    res_bad_ext = client.post("/api/documents", files=non_pdf, headers=emp1_headers)
    assert res_bad_ext.status_code == 400

    # 2. Corrupted PDF content rejected
    corrupt_pdf = {"file": ("corrupt.pdf", b"%PDF-1.4 garbage corrupt bytes", "application/pdf")}
    res_corrupt = client.post("/api/documents", files=corrupt_pdf, headers=emp1_headers)
    assert res_corrupt.status_code == 400

    # 3. Unsafe filenames rejected
    valid_pdf = make_valid_pdf_bytes("Financial Report 2024")
    res_unsafe_name = client.post(
        "/api/documents",
        files={"file": ("../../etc/passwd.pdf", valid_pdf, "application/pdf")},
        headers=emp1_headers,
    )
    assert res_unsafe_name.status_code == 400

    # 4. Extra/obsolete multipart fields rejected
    res_extra_field = client.post(
        "/api/documents",
        files={"file": ("report.pdf", valid_pdf, "application/pdf")},
        data={"allowed_users": "user-123"},
        headers=emp1_headers,
    )
    assert res_extra_field.status_code == 400

    # 5. Size limit enforcement (50 MiB boundary)
    with patch.object(settings, "UPLOAD_MAX_BYTES", 50):
        res_overflow = client.post(
            "/api/documents",
            files={"file": ("large_report.pdf", valid_pdf, "application/pdf")},
            headers=emp1_headers,
        )
        assert res_overflow.status_code == 413

    # 6. Valid PDF upload accepted with file ONLY
    res_ok = client.post(
        "/api/documents",
        files={"file": ("annual_report_2024.pdf", valid_pdf, "application/pdf")},
        headers=emp1_headers,
    )
    assert res_ok.status_code == 202
    data = res_ok.json()
    assert data["source"] == "annual_report_2024.pdf"
    assert "id" in data
    assert "job_id" in data


def test_persistent_private_library_authorization(client, emp1_headers, emp2_headers, admin_headers):
    valid_pdf = make_valid_pdf_bytes("Emp1 Private Secret Strategy")
    res_upload = client.post(
        "/api/documents",
        files={"file": ("private_secret.pdf", valid_pdf, "application/pdf")},
        headers=emp1_headers,
    )
    assert res_upload.status_code == 202
    doc_id = res_upload.json()["id"]
    job_id = res_upload.json()["job_id"]

    # Uploader (emp1) can view in library list
    res_emp1_docs = client.get("/api/documents", headers=emp1_headers)
    assert res_emp1_docs.status_code == 200
    matching = [d for d in res_emp1_docs.json()["items"] if d["id"] == doc_id]
    assert len(matching) == 1
    # Check timestamp format in milliseconds
    assert matching[0]["uploaded_at"] > 1_000_000_000_000

    # Other employee (emp2) CANNOT see document in library
    res_emp2_docs = client.get("/api/documents", headers=emp2_headers)
    assert doc_id not in [d["id"] for d in res_emp2_docs.json()["items"]]

    # Other employee CANNOT check job status (returns 404)
    assert client.get(f"/api/jobs/{job_id}", headers=emp2_headers).status_code == 404

    # Other employee CANNOT access source PDF (returns 404)
    assert client.get(f"/api/documents/{doc_id}/source", headers=emp2_headers).status_code == 404

    # Admin CAN see document in library and inspect job status
    assert doc_id in [d["id"] for d in client.get("/api/documents", headers=admin_headers).json()["items"]]
    assert client.get(f"/api/jobs/{job_id}", headers=admin_headers).status_code == 200


def test_admin_sharing_and_owner_retention(client, emp1_headers, emp2_headers, emp3_headers, admin_headers, seeded_users):
    valid_pdf = make_valid_pdf_bytes("Q4 Earnings Results")
    res_upload = client.post(
        "/api/documents",
        files={"file": ("q4_earnings.pdf", valid_pdf, "application/pdf")},
        headers=emp1_headers,
    )
    doc_id = res_upload.json()["id"]

    # 1. Non-admin cannot update sharing
    res_emp_share = client.put(
        f"/api/documents/{doc_id}/access",
        json={"access_list": [seeded_users["emp2"]["id"]]},
        headers=emp1_headers,
    )
    assert res_emp_share.status_code == 403

    # 2. Admin cannot grant access to non-existent user ID
    res_bad_share = client.put(
        f"/api/documents/{doc_id}/access",
        json={"access_list": ["non-existent-user-id-xyz"]},
        headers=admin_headers,
    )
    assert res_bad_share.status_code == 400

    # 3. Admin grants access to emp2
    res_share = client.put(
        f"/api/documents/{doc_id}/access",
        json={"access_list": [seeded_users["emp2"]["id"]]},
        headers=admin_headers,
    )
    assert res_share.status_code == 200
    assert seeded_users["emp2"]["id"] in res_share.json()["access_list"]

    # 4. Now emp2 can see the document in library and access source
    assert doc_id in [d["id"] for d in client.get("/api/documents", headers=emp2_headers).json()["items"]]
    res_emp2_source = client.get(f"/api/documents/{doc_id}/source", headers=emp2_headers)
    assert res_emp2_source.status_code == 200

    # 5. emp3 (ungranted) still cannot see or access
    assert doc_id not in [d["id"] for d in client.get("/api/documents", headers=emp3_headers).json()["items"]]
    assert client.get(f"/api/documents/{doc_id}/source", headers=emp3_headers).status_code == 404

    # 6. Active owner (emp1) retains full read/source/delete rights
    assert client.get(f"/api/documents/{doc_id}/source", headers=emp1_headers).status_code == 200

    # 7. Admin revokes emp2
    res_revoke = client.put(
        f"/api/documents/{doc_id}/access",
        json={"access_list": []},
        headers=admin_headers,
    )
    assert res_revoke.status_code == 200
    assert client.get(f"/api/documents/{doc_id}/source", headers=emp2_headers).status_code == 404


def test_document_deletion_permissions_and_existence_leakage(client, emp1_headers, emp2_headers, emp3_headers, admin_headers, seeded_users):
    valid_pdf = make_valid_pdf_bytes("Document to Delete")
    res_upload = client.post(
        "/api/documents",
        files={"file": ("delete_me.pdf", valid_pdf, "application/pdf")},
        headers=emp1_headers,
    )
    doc_id = res_upload.json()["id"]

    # Admin shares with emp2
    client.put(
        f"/api/documents/{doc_id}/access",
        json={"access_list": [seeded_users["emp2"]["id"]]},
        headers=admin_headers,
    )

    # Recipient (emp2) CANNOT delete the document (returns 404 to avoid leaking existence)
    res_del_recipient = client.delete(f"/api/documents/{doc_id}", headers=emp2_headers)
    assert res_del_recipient.status_code == 404

    # Unrelated user (emp3) CANNOT delete the document (returns 404)
    res_del_emp3 = client.delete(f"/api/documents/{doc_id}", headers=emp3_headers)
    assert res_del_emp3.status_code == 404

    # Owner (emp1) CAN delete the document
    res_del_owner = client.delete(f"/api/documents/{doc_id}", headers=emp1_headers)
    assert res_del_owner.status_code == 503  # Physical cleanup is unavailable, not falsely complete.
    with SessionLocal() as db:
        assert db.get(Document, doc_id).status == "cleanup_pending"

    # Immediate denial: access is gone for everyone
    assert client.get(f"/api/documents/{doc_id}/source", headers=emp1_headers).status_code == 404


def test_docling_chunker_deterministic_token_bounds_and_immutability():
    chunker = DoclingChunker(chunk_size=50, chunk_overlap=5)

    # Immutable input test
    original_text = "Operating revenue for fiscal year was $500M."
    items = [
        {"page_number": 1, "item_type": "section_header", "text": "Financial Summary"},
        {"page_number": 1, "item_type": "paragraph", "text": original_text},
    ]
    chunks1 = chunker.chunk_items(items, filename="report.pdf", document_id="doc-test-1", version=1)
    # Check that items were NOT mutated
    assert items[1]["text"] == original_text

    chunks2 = chunker.chunk_items(items, filename="report.pdf", document_id="doc-test-1", version=1)
    assert len(chunks1) == len(chunks2)
    assert chunks1[0]["chunk_id"] == chunks2[0]["chunk_id"]

    # Oversized table splitting with real tokenizer
    header = "| Metric | FY23 | FY24 |\n|---|---|---|"
    rows = [f"| Line Item {i} | ${i*10}K | ${i*12}K |" for i in range(1, 30)]
    table_text = header + "\n" + "\n".join(rows)

    table_items = [{"page_number": 2, "item_type": "table", "text": table_text}]
    table_chunks = chunker.chunk_items(table_items, filename="report.pdf", document_id="doc-test-1", version=1)

    assert len(table_chunks) > 1
    for tc in table_chunks:
        assert tc["item_type"] == "table"
        assert tc["page_number"] == 2
        assert "| Metric | FY23 | FY24 |" in tc["text"]
        # Real token count is strictly bounded
        assert chunker.count_tokens(tc["text"]) <= chunker.chunk_size


def test_durable_worker_claims_heartbeats_and_fencing(worker_db):
    db = worker_db
    doc_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now = utcnow()

    doc = Document(
        id=doc_id,
        filename="test_worker.pdf",
        source=f"/api/documents/{doc_id}/source",
        uploaded_by_id="user-emp1-ingest",
        owner_id="user-emp1-ingest",
        uploaded_at=now,
        storage_path=f"{uuid.uuid4().hex}.pdf",
        status="queued",
        version=1,
    )
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        filename="test_worker.pdf",
        status="queued",
        stage="queued",
        document_version=1,
        attempts=0,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.add(job)
    db.commit()

    # 1. Atomic claim with unique fencing token
    worker1_id = f"worker-{uuid.uuid4().hex}"
    claimed = _claim_next_job(db, worker_instance_id=worker1_id)
    assert claimed is not None
    claimed_job_id, claim_token1, version = claimed
    assert claimed_job_id == job_id
    assert worker1_id in claim_token1

    # 2. HeartbeatThread updates lease
    stop_event = threading.Event()
    abort_event = threading.Event()
    hb = HeartbeatThread(
        job_id=job_id,
        claim_token=claim_token1,
        interval=0.1,
        stop_event=stop_event,
        abort_event=abort_event,
    )
    hb.start()

    # Check lease was pulsed
    stop_event.set()
    hb.join(timeout=1.0)
    assert not abort_event.is_set()

    # 3. Simulate claim loss: worker 2 reclaims expired job
    worker2_id = f"worker-{uuid.uuid4().hex}"
    job_in_db = db.get(IngestionJob, job_id)
    job_in_db.lease_until = now - datetime.timedelta(seconds=60)
    db.commit()

    reclaimed = _claim_next_job(db, worker_instance_id=worker2_id)
    assert reclaimed is not None
    assert reclaimed[0] == job_id
    assert worker2_id in reclaimed[1]
    assert reclaimed[2] > version
    assert db.get(Document, doc_id).version == reclaimed[2]

    # Stale worker 1 attempt to execute must abort because claim token mismatch
    _execute_job(job_id, claim_token1, version)
    job_after_stale = db.get(IngestionJob, job_id)
    # Status remains processing under worker 2, NOT marked failed by stale worker 1!
    assert job_after_stale.worker_id == reclaimed[1]

    db.delete(job_in_db)
    db.delete(doc)
    db.commit()
    db.close()


def test_late_deletion_race_prevents_resurrection(worker_db):
    db = worker_db
    doc_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now = utcnow()

    doc = Document(
        id=doc_id,
        filename="race_test.pdf",
        source=f"/api/documents/{doc_id}/source",
        uploaded_by_id="user-emp1-ingest",
        owner_id="user-emp1-ingest",
        uploaded_at=now,
        storage_path=f"{uuid.uuid4().hex}.pdf",
        status="deleting",  # Deleted while worker was in flight
        version=1,
    )
    claim_token = f"worker-test:{uuid.uuid4().hex[:8]}"
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        filename="race_test.pdf",
        status="processing",
        stage="indexing",
        worker_id=claim_token,
        document_version=1,
        attempts=1,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.add(job)
    db.commit()

    with patch.object(pipeline.es_client, "delete_document_chunks") as mock_delete:
        _execute_job(job_id, claim_token, expected_version=1)
        db.refresh(doc)
        db.refresh(job)
        assert doc.status == "deleting"
        assert job.status == "failed"

    db.delete(job)
    db.delete(doc)
    db.commit()
    db.close()


def test_reconcile_deletions_fences_active_worker(worker_db):
    db = worker_db
    doc_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    now = utcnow()

    doc = Document(
        id=doc_id,
        filename="fence_test.pdf",
        source=f"/api/documents/{doc_id}/source",
        uploaded_by_id="user-emp1-ingest",
        owner_id="user-emp1-ingest",
        uploaded_at=now,
        storage_path=f"{uuid.uuid4().hex}.pdf",
        status="deleting",
        version=1,
    )
    job = IngestionJob(
        id=job_id,
        document_id=doc_id,
        filename="fence_test.pdf",
        status="processing",
        worker_id="active-worker-claim",
        lease_until=now + datetime.timedelta(seconds=60),  # Active lease
        document_version=1,
        attempts=1,
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    db.add(job)
    db.commit()

    # While worker has active lease, tombstone is NOT removed
    reconciled = _process_reconcile_deletions(db)
    assert reconciled is False
    assert db.get(Document, doc_id) is not None

    # After lease expires, reconciliation finishes cleanup durably
    job.lease_until = now - datetime.timedelta(seconds=60)
    db.commit()

    with patch.object(pipeline.es_client, "delete_document_chunks") as mock_del_es:
        reconciled_after = _process_reconcile_deletions(db)
        assert reconciled_after is True
        assert db.get(Document, doc_id) is None

    db.close()

def _blocking_parser_worker(pdf_path: str, conn: Any) -> None:
    import time
    time.sleep(10)
    conn.send({"items": [], "total_pages": 1})


def test_killable_parser_process_timeout_and_termination():
    """Verify that a hung parser child process is terminated within bounded time."""
    pipe = IngestionPipeline(parser_worker_fn=_blocking_parser_worker)
    start_time = datetime.datetime.now()
    with patch.object(settings, "PARSER_TIMEOUT_SECONDS", 0.5):
        with pytest.raises(TimeoutError) as exc_info:
            pipe.parse_pdf("dummy_path.pdf")
        assert "exceeded configured limit" in str(exc_info.value)

    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    # Must terminate within bounded time (< 3.0s), not wait 10s
    assert elapsed < 3.5


def test_unstructured_oversized_table_rejected():
    """Oversized non-standard tables without row headers must fail explicitly."""
    chunker = DoclingChunker(chunk_size=20, chunk_overlap=2)
    non_standard_table = "Header Without Standard Separator\n" + "\n".join([f"Data Row {i} with values" for i in range(20)])
    items = [{"page_number": 1, "item_type": "table", "text": non_standard_table}]

    with pytest.raises(ValueError) as exc_info:
        chunker.chunk_items(items, filename="bad_table.pdf", document_id="doc-tbl", version=1)


def test_scoped_store_wipe_preserves_unrelated_files(client, admin_headers):
    """Store wipe must unlink only captured document paths, not sweep the directory."""
    # Create an unrelated file in UPLOAD_DIR
    unrelated_file = settings.UPLOAD_DIR / f"unrelated_{uuid.uuid4().hex}.txt"
    unrelated_file.write_text("Preserved unmanaged file")

    try:
        with patch.object(pipeline.es_client, "delete_document_chunks", return_value=0):
            res = client.delete("/api/documents", headers=admin_headers)
        assert res.status_code == 200
        # Unrelated file must still exist!
        assert unrelated_file.exists()
    finally:
        unrelated_file.unlink(missing_ok=True)


def _upload(client, headers, filename: str, text: str) -> dict:
    res = client.post(
        "/api/documents",
        files={"file": (filename, make_valid_pdf_bytes(text), "application/pdf")},
        headers=headers,
    )
    assert res.status_code == 202
    return res.json()


def _stored_file(document_id: str) -> Path:
    with SessionLocal() as db:
        return settings.UPLOAD_DIR / db.get(Document, document_id).storage_path


def _listed(client, headers) -> set[str]:
    return {d["id"] for d in client.get("/api/documents", headers=headers).json()["items"]}


def test_disk_cleanup_failure_stays_denied_until_storage_recovers(
    client, emp1_headers, emp2_headers, admin_headers, seeded_users
):
    """A real read-only upload directory keeps deletion pending without restoring access."""
    # Never change permissions on anything but the run-owned disposable storage.
    assert "ledgerlens-tests-" in str(settings.UPLOAD_DIR.resolve())
    deleted = _upload(client, emp1_headers, "disk_failure.pdf", "Disk failure revenue 10")
    survivor = _upload(client, emp2_headers, "disk_survivor.pdf", "Unrelated revenue 20")
    client.put(
        f"/api/documents/{deleted['id']}/access",
        json={"access_list": [seeded_users["emp2"]["id"]]},
        headers=admin_headers,
    )
    deleted_file, survivor_file = _stored_file(deleted["id"]), _stored_file(survivor["id"])
    control = settings.UPLOAD_DIR / f"unmanaged_{uuid.uuid4().hex}.pdf"
    control.write_bytes(make_valid_pdf_bytes("Unmanaged control"))
    mode = settings.UPLOAD_DIR.stat().st_mode
    try:
        with patch.object(pipeline.es_client, "delete_document_chunks", return_value=0):
            settings.UPLOAD_DIR.chmod(0o555)
            assert client.delete(f"/api/documents/{deleted['id']}", headers=emp1_headers).status_code == 503

            # Access is withdrawn immediately although the bytes remain on disk.
            assert deleted_file.exists()
            for headers in (emp1_headers, emp2_headers, admin_headers):
                assert deleted["id"] not in _listed(client, headers)
                assert client.get(f"/api/documents/{deleted['id']}/source", headers=headers).status_code == 404
            assert client.delete(f"/api/documents/{deleted['id']}", headers=emp1_headers).status_code == 404

            # Reconciliation while storage is still failing stays pending, never complete.
            with SessionLocal() as db:
                _process_reconcile_deletions(db)
                assert db.get(Document, deleted["id"]).status == "cleanup_pending"
            assert deleted_file.exists()

            settings.UPLOAD_DIR.chmod(mode)
            with SessionLocal() as db:
                _process_reconcile_deletions(db)
                assert db.get(Document, deleted["id"]) is None
                assert db.scalar(
                    select(IngestionJob.id).where(IngestionJob.document_id == deleted["id"])
                ) is None
        assert not deleted_file.exists()
        assert survivor_file.exists() and control.exists()
        assert survivor["id"] in _listed(client, emp2_headers)
        assert client.get(f"/api/documents/{survivor['id']}/source", headers=emp2_headers).status_code == 200
    finally:
        settings.UPLOAD_DIR.chmod(mode)
        control.unlink(missing_ok=True)


def test_store_wipe_during_active_claim_cannot_resurrect(client, emp1_headers, admin_headers):
    """Wipe fences an in-flight worker, then finishes cleanup and spares unmanaged PDFs."""
    managed = _upload(client, emp1_headers, "wipe_inflight.pdf", "In-flight revenue 30")
    managed_file = _stored_file(managed["id"])
    control = settings.UPLOAD_DIR / f"unmanaged_{uuid.uuid4().hex}.pdf"
    control.write_bytes(make_valid_pdf_bytes("Unmanaged wipe control"))
    claim = f"paused-worker:{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        job = db.get(IngestionJob, managed["job_id"])
        job.status, job.stage, job.worker_id = "processing", "embedding", claim
        job.lease_until = utcnow() + datetime.timedelta(seconds=60)
        version = db.get(Document, managed["id"]).version
        db.commit()
    try:
        with patch.object(pipeline.es_client, "delete_document_chunks", return_value=0) as es_delete, \
                patch.object(pipeline.es_client, "upsert_chunks") as publish:
            assert client.delete("/api/documents", headers=admin_headers).status_code == 503
            assert managed["id"] not in _listed(client, admin_headers)
            assert client.get(f"/api/documents/{managed['id']}/source", headers=emp1_headers).status_code == 404

            # The paused worker resumes with its old claim and must not publish anything.
            _execute_job(managed["job_id"], claim, version)
            publish.assert_not_called()
            with SessionLocal() as db:
                assert db.get(Document, managed["id"]).status == "cleanup_pending"
                assert db.get(IngestionJob, managed["job_id"]).status == "failed"
            assert managed_file.exists()

            with SessionLocal() as db:
                db.get(IngestionJob, managed["job_id"]).lease_until = utcnow() - datetime.timedelta(seconds=1)
                db.commit()
                _process_reconcile_deletions(db)
                assert db.get(Document, managed["id"]) is None
            es_delete.assert_any_call(managed["id"])
        assert not managed_file.exists()
        assert control.exists()
    finally:
        control.unlink(missing_ok=True)


def test_reindex_retries_a_failed_document_for_its_owner_or_an_admin(
    client, seeded_users, emp1_headers, emp2_headers, admin_headers
):
    uploaded = _upload(client, emp1_headers, "retry.pdf", "Retry me")
    document_id = uploaded["id"]
    url = f"/api/documents/{document_id}/reindex"

    assert client.post(url, headers=emp1_headers).status_code == 409  # still queued

    with SessionLocal() as db:
        db.get(Document, document_id).status = "failed"
        db.commit()

    assert client.post(url, headers=emp2_headers).status_code == 404  # not theirs
    retried = client.post(url, headers=emp1_headers)
    assert retried.status_code == 202
    assert retried.json()["job_id"] != uploaded["job_id"]
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        assert (document.status, document.version) == ("queued", 2)
        document.status = "failed"
        db.commit()
    assert client.post(url, headers=admin_headers).status_code == 202

    job = client.get(f"/api/jobs/{retried.json()['job_id']}", headers=emp1_headers)
    assert job.status_code == 200 and job.json()["document_id"] == document_id


def test_document_list_is_paged(client, emp1_headers):
    for name in ("page-a.pdf", "page-b.pdf"):
        _upload(client, emp1_headers, name, name)
    page = client.get("/api/documents?limit=1", headers=emp1_headers).json()
    assert len(page["items"]) == 1 and page["total"] >= 2 and page["limit"] == 1
    second = client.get("/api/documents?limit=1&offset=1", headers=emp1_headers).json()
    assert second["items"][0]["id"] != page["items"][0]["id"]


def _blank_pdf(pages: int) -> bytes:
    import io

    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    for _ in range(pages):
        document.new_page(612, 792)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def test_upload_rejects_pdfs_over_the_page_limit_before_queueing(client, emp1_headers, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_MAX_PAGES", 2)
    before = client.get("/api/documents", headers=emp1_headers).json()["total"]

    too_long = client.post(
        "/api/documents",
        files={"file": ("long.pdf", _blank_pdf(3), "application/pdf")},
        headers=emp1_headers,
    )
    assert too_long.status_code == 413
    assert "3 pages" in too_long.json()["detail"] and "2" in too_long.json()["detail"]
    assert client.get("/api/documents", headers=emp1_headers).json()["total"] == before

    at_limit = client.post(
        "/api/documents",
        files={"file": ("short.pdf", _blank_pdf(2), "application/pdf")},
        headers=emp1_headers,
    )
    assert at_limit.status_code == 202
