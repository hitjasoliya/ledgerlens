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

from services.gateway.main import app as gateway_app


@pytest.fixture(scope="module")
def client():
    with TestClient(gateway_app) as c:
        yield c


def test_gateway_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert "status" in res.json()
