import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

root_dir = Path(__file__).resolve().parent.parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from services.ingestion.main import app as ingestion_app
from common.database import Base, engine, SessionLocal
from common.models import IngestionJob, Document


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(ingestion_app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_job_status_not_found(client):
    res = client.get("/api/ingest/jobs/nonexistent-job-id")
    assert res.status_code == 404


def test_get_documents_empty(client):
    res = client.get("/api/documents")
    assert res.status_code == 200
    assert isinstance(res.json(), list)
