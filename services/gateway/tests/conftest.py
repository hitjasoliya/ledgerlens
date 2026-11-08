"""Real HTTP services with disposable persistence; no forwarding substitutes."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import pytest

from services.gateway.tests.redis_harness import start_redis_server


@pytest.fixture(scope="module")
def live_services():
    root = Path(__file__).resolve().parents[3]
    temporary = tempfile.TemporaryDirectory(prefix="ledgerlens-http-")
    resources = Path(temporary.name)
    live_redis = start_redis_server(
        data_dir=resources / "redis", prefix="ledgerlens-live-redis-"
    )
    listeners = {}
    processes = []
    logs = []
    urls = {}
    for name in ("identity", "ingestion", "rag", "gateway"):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        listeners[name] = listener
        urls[name] = f"http://127.0.0.1:{listener.getsockname()[1]}"
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join((str(root), str(root / "packages/common/src"))),
        "DATABASE_URL": f"sqlite:///{resources / 'live.sqlite'}",
        "UPLOAD_DIR": str(resources / "uploads"),
        "REDIS_URL": live_redis.url,
        "IDENTITY_SERVICE_URL": urls["identity"],
        "INGESTION_SERVICE_URL": urls["ingestion"],
        "RAG_SERVICE_URL": urls["rag"],
        "ENV": "test",
        "RAG_GENERATOR_ADAPTER": "deterministic",
    }
    try:
        with httpx.Client(timeout=10, trust_env=False) as http:
            for name, listener in listeners.items():
                log = (resources / f"{name}.log").open("w+")
                logs.append(log)
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        f"services.{name}.main:app",
                        "--fd",
                        str(listener.fileno()),
                        "--log-level",
                        "warning",
                    ],
                    cwd=resources,
                    env=env,
                    pass_fds=(listener.fileno(),),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                processes.append(process)
                deadline = time.monotonic() + 45
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        break
                    try:
                        if (
                            http.get(f"{urls[name]}/health", timeout=1).status_code
                            == 200
                        ):
                            break
                    except httpx.TransportError:
                        time.sleep(0.05)
                else:
                    pytest.fail(f"{name} did not become healthy")
                if process.poll() is not None:
                    log.seek(0)
                    pytest.fail(f"{name} exited during startup:\n{log.read()}")
                listener.close()
            yield {
                "urls": urls,
                "http": http,
                "resources": resources,
                "redis": live_redis,
            }
    finally:
        for listener in listeners.values():
            listener.close()
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
        for process in reversed(processes):
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for log in logs:
            log.close()
        live_redis.cleanup()
        temporary.cleanup()


@pytest.fixture
def live_redis(live_services):
    """Access the owned live Redis instance."""
    return live_services["redis"]


@pytest.fixture(scope="module")
def actors(live_services):
    http = live_services["http"]
    gateway = live_services["urls"]["gateway"]

    def login(username, password):
        response = http.post(
            f"{gateway}/api/auth/login",
            json={"username": username, "password": password},
        )
        response.raise_for_status()
        data = response.json()
        return {
            **data["user"],
            "token": data["access_token"],
            "headers": {"Authorization": f"Bearer {data['access_token']}"},
        }

    admin = login("admin", os.environ["ADMIN_INITIAL_PASSWORD"])
    result = {"admin": admin}
    for username in ("owner", "other"):
        response = http.post(
            f"{gateway}/api/users",
            headers=admin["headers"],
            json={"username": username, "password": "password123", "role": "employee"},
        )
        response.raise_for_status()
        result[username] = login(username, "password123")
    return result


@pytest.fixture
def upload_document(live_services):
    stream = b"BT /F1 12 Tf 72 720 Td (Synthetic authorization report) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{number} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(pdf)
    pdf.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode())
    pdf.extend(f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())

    def upload(actor):
        http, gateway = live_services["http"], live_services["urls"]["gateway"]
        response = http.post(
            f"{gateway}/api/documents", headers=actor["headers"],
            files={"file": ("synthetic.pdf", bytes(pdf), "application/pdf")},
        )
        response.raise_for_status()
        # Authorization and ownership transitions must work while indexing is
        # still pending; parser/provider readiness is not this fixture's seam.
        return response.json()

    return upload


@pytest.fixture
def ready_document(live_services):
    """Give an actor an already-indexed document so they can start a chat.

    Chats must be created with documents. These tests exercise authorization and
    ownership, not parsing, so the row is written directly instead of racing the
    live ingestion worker.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from common.config import settings
    from common.models import Document

    engine = create_engine(f"sqlite:///{live_services['resources'] / 'live.sqlite'}")

    def make(actor, access_list=()):
        document_id = str(uuid.uuid4())
        with Session(engine) as db:
            db.add(Document(
                id=document_id, filename="ready.pdf", source="ready.pdf",
                uploaded_by_id=actor["id"], owner_id=actor["id"],
                access_list=list(access_list), storage_path=f"{document_id}.pdf",
                status="searchable", version=1, parser="docling",
                embedding_model=settings.EMBEDDING_MODEL,
                embedding_dims=settings.EMBEDDING_DIMS,
                pages_parsed=1, chunks_created=1, chunks_indexed=1,
            ))
            db.commit()
        return document_id

    yield make
    engine.dispose()
