import os
import sys
from pathlib import Path
import pytest
from fastapi import Request
from fastapi.datastructures import Headers
from fastapi.testclient import TestClient

root_dir = Path(__file__).resolve().parent.parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from services.gateway.main import app as gateway_app, _filter_client_headers, _filter_downstream_response_headers, get_client


@pytest.fixture(scope="module")
def client():
    with TestClient(gateway_app) as c:
        yield c


def test_gateway_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_gateway_ready_reports_degraded_when_downstream_offline(client):
    # Downstream services and redis are offline in unit context
    res = client.get("/ready")
    assert res.status_code == 503
    data = res.json()
    assert data["detail"]["status"] == "degraded"
    assert "identity" in data["detail"]["dependencies"]


def test_filter_client_headers_strips_hop_by_hop_and_identity_overrides():
    raw_headers = Headers({
        "host": "gateway.internal",
        "connection": "X-Custom-Hop, Keep-Alive",
        "x-custom-hop": "strip-this",
        "keep-alive": "timeout=5",
        "te": "trailers",
        "upgrade": "websocket",
        "content-length": "100",
        "x-user-id": "attacker-injected",
        "x-role": "admin",
        "authorization": "Bearer valid-token",
        "accept": "application/json",
    })
    filtered = _filter_client_headers(raw_headers)

    # Stripped headers
    assert "host" not in filtered
    assert "connection" not in filtered
    assert "x-custom-hop" not in filtered
    assert "keep-alive" not in filtered
    assert "te" not in filtered
    assert "upgrade" not in filtered
    assert "content-length" not in filtered
    assert "x-user-id" not in filtered
    assert "x-role" not in filtered

    # Retained headers
    assert filtered.get("authorization") == "Bearer valid-token"
    assert filtered.get("accept") == "application/json"


def test_get_client_requires_lifespan():
    # Outside lifespan, get_client raises RuntimeError
    scope = {"type": "http", "app": gateway_app}
    uninitialized_app = type("App", (), {"state": type("State", (), {})()})()
    req = Request({"type": "http", "app": uninitialized_app})
    with pytest.raises(RuntimeError) as exc_info:
        get_client(req)
    assert "Gateway HTTP client is uninitialized" in str(exc_info.value)
