"""Revocation proof through real HTTP processes and an owned Redis instance."""
import datetime

import jwt
import pytest

from common.auth import create_access_token
from common.config import settings


PROTECTED = (
    ("gateway", "/api/auth/me"),
    ("identity", "/api/auth/me"),
    ("ingestion", "/api/documents"),
    ("rag", "/api/chat/sessions"),
)


def _login(live, username="owner"):
    response = live["http"].post(
        f"{live['urls']['gateway']}/api/auth/login",
        json={"username": username, "password": "password123"},
    )
    response.raise_for_status()
    result = response.json()
    return {
        **result["user"], "token": result["access_token"],
        "headers": {"Authorization": f"Bearer {result['access_token']}"},
    }


def _assert_access(live, headers, expected):
    for service, path in PROTECTED:
        response = live["http"].get(f"{live['urls'][service]}{path}", headers=headers)
        assert response.status_code == expected, (service, response.text)


@pytest.mark.parametrize("entrypoint", ["gateway", "identity"])
def test_logout_revokes_copied_token_across_processes(live_services, actors, entrypoint):
    live = live_services
    fresh = _login(live)
    _assert_access(live, fresh["headers"], 200)
    response = live["http"].post(
        f"{live['urls'][entrypoint]}/api/auth/logout", headers=fresh["headers"],
    )
    assert response.status_code == 200
    _assert_access(live, fresh["headers"], 401)
    relogged = _login(live)
    _assert_access(live, relogged["headers"], 200)
    _assert_access(live, actors["other"]["headers"], 200)
    assert live["http"].post(
        f"{live['urls']['gateway']}/api/auth/logout", headers=fresh["headers"],
    ).status_code == 401


def test_store_outage_fails_closed_and_recovers(live_services, live_redis, actors):
    live = live_services
    fresh = _login(live)
    expired = create_access_token(
        {"id": fresh["id"], "sub": fresh["username"]},
        expires_delta=datetime.timedelta(0),
    )
    _assert_access(live, fresh["headers"], 200)
    live_redis.stop()
    try:
        _assert_access(live, fresh["headers"], 503)
        for service in ("gateway", "identity"):
            assert live["http"].post(
                f"{live['urls'][service]}/api/auth/logout", headers=fresh["headers"],
            ).status_code == 503
        for headers in ({}, {"Authorization": "Bearer malformed"}, {"Authorization": f"Bearer {expired}"}):
            _assert_access(live, headers, 401)
        assert live["http"].get(f"{live['urls']['gateway']}/health").status_code == 200
        _login(live)  # Public credential validation stays available, not protected access.
    finally:
        live_redis.start()
    _assert_access(live, fresh["headers"], 200)
    assert live["http"].post(
        f"{live['urls']['gateway']}/api/auth/logout", headers=fresh["headers"],
    ).status_code == 200
    _assert_access(live, fresh["headers"], 401)


def test_store_write_refusal_does_not_acknowledge_logout(live_services, live_redis, actors):
    live = live_services
    fresh = _login(live)
    control = live_redis.get_client()
    try:
        control.execute_command("ACL", "SETUSER", "default", "-@write")
        try:
            _assert_access(live, fresh["headers"], 200)
            assert live["http"].post(
                f"{live['urls']['gateway']}/api/auth/logout", headers=fresh["headers"],
            ).status_code == 503
            _assert_access(live, fresh["headers"], 200)
        finally:
            control.execute_command("ACL", "SETUSER", "default", "+@write")
    finally:
        control.connection_pool.disconnect()
    assert live["http"].post(
        f"{live['urls']['gateway']}/api/auth/logout", headers=fresh["headers"],
    ).status_code == 200
    _assert_access(live, fresh["headers"], 401)


def test_acknowledged_revocation_survives_redis_crash(live_services, live_redis, actors):
    live = live_services
    fresh = _login(live)
    assert live["http"].post(
        f"{live['urls']['gateway']}/api/auth/logout", headers=fresh["headers"],
    ).status_code == 200
    live_redis.restart(crash=True)
    _assert_access(live, fresh["headers"], 401)
    _assert_access(live, actors["other"]["headers"], 200)


def test_logout_preserves_document_grants_and_history(live_services, actors, upload_document, ready_document):
    live = live_services
    http, gateway = live["http"], live["urls"]["gateway"]
    owner = _login(live)
    admin = actors["admin"]["headers"]
    uploaded = upload_document(owner)
    document_id = uploaded["id"]
    granted = http.put(
        f"{gateway}/api/documents/{document_id}/access", headers=admin,
        json={"access_list": [owner["id"], actors["other"]["id"]]},
    )
    assert granted.status_code == 200
    document_before = granted.json()
    created = http.post(
        f"{gateway}/api/chat/sessions", headers=owner["headers"],
        json={"selected_document_ids": [ready_document(owner)]},
    )
    created.raise_for_status()
    session_id = created.json()["id"]
    assert http.post(
        f"{gateway}/api/chat/sessions/{session_id}/messages", headers=owner["headers"],
        json={"message": "hello"},
    ).status_code == 200
    history_url = f"{gateway}/api/chat/sessions/{session_id}"
    history_before = http.get(history_url, headers=owner["headers"]).json()["messages"]
    assert http.post(f"{gateway}/api/auth/logout", headers=owner["headers"]).status_code == 200
    assert http.get(history_url, headers=owner["headers"]).status_code == 401
    relogged = _login(live)
    history_after = http.get(history_url, headers=relogged["headers"])
    assert history_after.status_code == 200
    assert history_after.json()["messages"] == history_before
    documents = http.get(f"{gateway}/api/documents", headers=relogged["headers"])
    assert documents.status_code == 200
    assert next(doc for doc in documents.json()["items"] if doc["id"] == document_id) == document_before
    recipient_documents = http.get(f"{gateway}/api/documents", headers=actors["other"]["headers"])
    assert recipient_documents.status_code == 200
    assert document_id in {doc["id"] for doc in recipient_documents.json()["items"]}


def test_revocation_outlives_former_24_hour_cap(live_services, live_redis, actors):
    live = live_services
    token = create_access_token(
        {"id": actors["owner"]["id"], "sub": actors["owner"]["username"]},
        expires_delta=datetime.timedelta(hours=48),
    )
    headers = {"Authorization": f"Bearer {token}"}
    _assert_access(live, headers, 200)
    assert live["http"].post(
        f"{live['urls']['gateway']}/api/auth/logout", headers=headers,
    ).status_code == 200
    control = live_redis.get_client()
    try:
        # Accelerate only this owned store's expiration horizon, not JWT wall time.
        # A fixed 24h revocation would disappear; the 48h JWT is still valid.
        for key in control.scan_iter():
            remaining = control.pttl(key)
            if remaining > 0:
                control.pexpire(key, remaining - 86_401_000)
    finally:
        control.connection_pool.disconnect()
    _assert_access(live, headers, 401)
    _assert_access(live, actors["other"]["headers"], 200)


def test_legacy_tokens_without_jti_require_relogin(live_services, actors):
    token = jwt.encode(
        {"id": actors["owner"]["id"], "sub": "owner",
         "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=30)},
        settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM,
    )
    _assert_access(live_services, {"Authorization": f"Bearer {token}"}, 401)
    _assert_access(live_services, _login(live_services)["headers"], 200)
