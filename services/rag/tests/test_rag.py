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

from services.rag.main import app as rag_app
from common.database import Base, engine


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    with TestClient(rag_app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_chat_greeting(client):
    res = client.post(
        "/api/chat",
        json={"message": "hello", "user_id": "test_user", "session_id": "s1"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert len(data["answer"]) > 0


def test_chat_session_creation(client):
    res = client.post("/api/chat/sessions", json={"title": "Test Chat"})
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Test Chat"
    assert "id" in data
