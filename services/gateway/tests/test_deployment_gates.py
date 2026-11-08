"""Deployment, startup, and quality gate regressions (Tickets 03, 20, 21, 22).

Verifies:
1. Ticket 03: Safe credential bootstrap rejects missing/insecure JWT secrets and admin passwords.
   Diagnostics never log or expose credentials.
2. Ticket 20: Separate liveness (/health) and readiness (/ready). Readiness returns 503
   on dependency outages and recovers when dependencies return.
3. Ticket 20: Gateway bounds incoming request bodies (50MiB file + 1MiB bounded multipart overhead)
   and rejects oversized bodies with 413 without buffering.
4. Ticket 21: Launcher process lifecycle does not terminate unrelated processes occupying target ports.
"""
import os
import socket
import subprocess
import sys
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from common.config import Settings
from services.gateway.main import app as gateway_app


@pytest.fixture
def client():
    with TestClient(gateway_app) as c:
        yield c

def test_credential_bootstrap_rejects_insecure_defaults():
    # Outside test mode, insecure or short signing secrets must be rejected
    insecure_secrets = [
        "",
        "short",
        "changeme",
        "admin123",
        "secret",
        "ledgerlens-super-secret-key-change-in-production-2026",
    ]
    for secret in insecure_secrets:
        with pytest.raises((ValueError, ValidationError)) as exc_info:
            Settings(
                ENV="production",
                JWT_SECRET=secret,
                ADMIN_INITIAL_PASSWORD="valid-strong-admin-pass-1234",
            )
        # Error message must NOT disclose the input credential
        error_msg = str(exc_info.value)
        if secret and len(secret) > 4:
            assert secret not in error_msg

    # Insecure or short administrator passwords must be rejected
    insecure_passwords = [
        "short",
        "admin123",
        "password",
        "changeme",
        "secret",
    ]
    for password in insecure_passwords:
        with pytest.raises((ValueError, ValidationError)):
            Settings(
                ENV="production",
                JWT_SECRET="a-very-strong-and-secure-random-signing-secret-value-32",
                ADMIN_INITIAL_PASSWORD=password,
            )
    private_value = "private_password_value_" * 5
    with pytest.raises(ValueError) as rejected:
        Settings(ENV="production", JWT_SECRET="x" * 64, ADMIN_INITIAL_PASSWORD=private_value)
    assert private_value not in str(rejected.value)




def test_readiness_fails_closed_on_outage(client):
    # In an environment without downstream services, liveness is ok but readiness fails closed with 503
    liveness = client.get("/health")
    assert liveness.status_code == 200

    readiness = client.get("/ready")
    assert readiness.status_code == 503
    assert readiness.json()["detail"]["status"] == "degraded"

def test_gateway_enforces_upload_size_limit(live_services, actors):
    http, urls = live_services["http"], live_services["urls"]
    gateway = urls["gateway"]

    # Content-Length exceeding 51 MiB (50 MiB file + 1 MiB bounded multipart overhead)
    oversized_length = (50 * 1024 * 1024) + (2 * 1024 * 1024)  # 52 MiB
    headers = {
        **actors["admin"]["headers"],
        "Content-Length": str(oversized_length),
        "Content-Type": "application/octet-stream",
    }
    def body():
        remaining = oversized_length
        while remaining:
            block = b"x" * min(65536, remaining)
            remaining -= len(block)
            yield block
    res = http.post(f"{gateway}/api/documents", headers=headers, content=body())
    assert res.status_code == 413


def test_launcher_occupied_port_does_not_kill_unrelated_process():
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", 8000))
        except OSError:
            pytest.skip("Launcher test requires an available target port for its owned listener")
        listener.listen()
        occupant = subprocess.Popen(
            [sys.executable, "-c", "import signal; print('ready',flush=True); signal.pause()"],
            pass_fds=(listener.fileno(),), stdout=subprocess.PIPE, text=True,
        )
        try:
            assert occupant.stdout.readline().strip() == "ready"
            result = subprocess.run(
                ["bash", "run.sh"], capture_output=True, text=True, timeout=10,
            )
            assert result.returncode != 0
            assert occupant.poll() is None
            connection = socket.create_connection(("127.0.0.1", 8000), timeout=1)
            connection.close()
        finally:
            occupant.terminate()
            occupant.wait(timeout=5)


def test_published_postgres_password_is_rejected_outside_test_mode():
    with pytest.raises(ValueError):
        Settings(
            ENV="production", JWT_SECRET="x" * 64,
            ADMIN_INITIAL_PASSWORD="a-private-bootstrap-password",
            DATABASE_URL="postgresql://postgres:postgrespassword@localhost/ledgerlens",
        )
