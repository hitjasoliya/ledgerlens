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

from services.identity.main import app as identity_app
from common.database import initialize_database, engine, SessionLocal
from common.models import User
from common.auth import get_password_hash


@pytest.fixture(scope="module")
def client():
    initialize_database()
    db = SessionLocal()
    admin = db.query(User).filter(User.username == "test_admin").first()
    if not admin:
        admin = User(
            username="test_admin",
            hashed_password=get_password_hash("password123"),
            role="admin",
        )
        db.add(admin)
        db.commit()
    db.close()

    with TestClient(identity_app) as c:
        yield c


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_ready_reports_status(client):
    res = client.get("/ready")
    assert res.status_code in (200, 503)


def test_login_success(client):
    res = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "password123"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["username"] == "test_admin"
    assert data["user"]["role"] == "admin"


def test_login_invalid_password(client):
    res = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "wrongpassword"},
    )
    assert res.status_code == 401


def test_create_user_duplicate_username_returns_409(client):
    login = client.post(
        "/api/auth/login",
        json={"username": "test_admin", "password": "password123"},
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Attempt to create existing username
    res = client.post(
        "/api/users",
        headers=headers,
        json={"username": "test_admin", "password": "password123", "role": "employee"},
    )
    assert res.status_code == 409
