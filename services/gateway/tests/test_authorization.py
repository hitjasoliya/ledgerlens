import jwt
import datetime
import time
import uuid

import pytest

from common.auth import create_access_token

from common.config import settings


def test_anonymous_document_access_is_denied_at_gateway_and_downstream(live_services):
    http = live_services["http"]
    urls = live_services["urls"]
    for service in ("gateway", "ingestion"):
        response = http.get(f"{urls[service]}/api/documents")
        assert response.status_code == 401, (service, response.text)


def test_malformed_signed_token_claims_are_unauthorized(live_services, actors):
    token = jwt.encode(
        {"id": actors["owner"]["id"], "sub": actors["owner"]["username"], "exp": {}, "jti": uuid.uuid4().hex},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    response = live_services["http"].get(
        f"{live_services['urls']['gateway']}/api/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401


def test_invalid_credentials_fail_independently_in_every_service(live_services, actors):
    owner = actors["owner"]
    expired = create_access_token(
        {"id": owner["id"], "sub": owner["username"]},
        expires_delta=datetime.timedelta(seconds=-1),
    )
    missing_identity = jwt.encode(
        {"sub": owner["username"], "exp": time.time() + 60, "jti": uuid.uuid4().hex},
        settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM,
    )
    invalid_identity = create_access_token({"id": [], "sub": owner["username"]})
    for service, path in (
        ("gateway", "/api/documents"), ("identity", "/api/auth/me"),
        ("ingestion", "/api/documents"), ("rag", "/api/chat/sessions"),
    ):
        for authorization in (
            "Bearer", "Bearer a b", "Basic credentials", "Bearer invalid",
            f"Bearer {expired}", f"Bearer {missing_identity}", f"Bearer {invalid_identity}",
        ):
            response = live_services["http"].get(
                f"{live_services['urls'][service]}{path}",
                headers={
                    "Authorization": authorization,
                    "X-User-ID": actors["admin"]["id"],
                    "X-User-Role": "admin",
                },
            )
            assert response.status_code == 401, (service, response.text)


def test_roles_come_from_account_not_headers_or_token_claims(live_services, actors):
    http, urls = live_services["http"], live_services["urls"]
    owner = actors["owner"]
    false_admin_token = create_access_token(
        {"id": owner["id"], "sub": owner["username"], "role": "admin"}
    )
    forged_headers = {
        "Authorization": f"Bearer {false_admin_token}",
        "X-User-ID": actors["admin"]["id"], "X-User-Role": "admin",
    }
    for service in ("gateway", "identity"):
        response = http.get(f"{urls[service]}/api/users", headers=forged_headers)
        assert response.status_code == 403
        admin = actors["admin"]
        stale_employee_claim = create_access_token(
            {"id": admin["id"], "sub": admin["username"], "role": "employee"}
        )
        response = http.get(
            f"{urls[service]}/api/users",
            headers={"Authorization": f"Bearer {stale_employee_claim}"},
        )
        assert response.status_code == 200
        assert owner["id"] in {user["id"] for user in response.json()["items"]}
    for service in ("gateway", "ingestion"):
        assert http.delete(f"{urls[service]}/api/documents", headers=forged_headers).status_code == 403
        assert http.put(
            f"{urls[service]}/api/documents/unknown/access",
            headers=forged_headers, json={"access_list": []},
        ).status_code == 403


def test_foreign_conversations_cannot_be_entered_even_by_admin(live_services, actors, ready_document):
    http, urls = live_services["http"], live_services["urls"]
    owner = actors["owner"]
    created = http.post(
        f"{urls['gateway']}/api/chat/sessions",
        headers=owner["headers"],
        json={"title": "Private report discussion", "selected_document_ids": [ready_document(owner)]},
    )
    assert created.status_code == 201
    session_id = created.json()["id"]
    assert http.post(
        f"{urls['gateway']}/api/chat/sessions/{session_id}/messages", headers=owner["headers"],
        json={"message": "hello"},
    ).status_code == 200
    history_url = f"{urls['gateway']}/api/chat/sessions/{session_id}"
    original = http.get(history_url, headers=owner["headers"]).json()["messages"]
    assert [message["content"] for message in original if message["role"] == "user"] == ["hello"]
    for service in ("gateway", "rag"):
        for intruder in (actors["other"], actors["admin"]):
            headers = {**intruder["headers"], "X-User-ID": owner["id"], "X-User-Role": "admin"}
            assert http.get(
                f"{urls[service]}/api/chat/sessions/{session_id}", headers=headers,
            ).status_code == 404
            assert http.post(
                f"{urls[service]}/api/chat/sessions/{session_id}/messages", headers=headers,
                json={"message": "unauthorized append"},
            ).status_code == 404
            for path in (f"/api/chat/sessions/{session_id}/messages", f"/api/chat/sessions/{session_id}"):
                assert http.delete(f"{urls[service]}{path}", headers=headers).status_code == 404
            listed = http.get(
                f"{urls[service]}/api/chat/sessions",
                headers=headers, params={"user_id": owner["id"]},
            )
            assert listed.status_code == 200
            assert session_id not in {item["id"] for item in listed.json()["items"]}
    assert http.get(history_url, headers=owner["headers"]).json()["messages"] == original
    spoofed_create = http.post(
        f"{urls['gateway']}/api/chat/sessions",
        headers=actors["other"]["headers"],
        params={"user_id": owner["id"]},
        json={"selected_document_ids": [ready_document(actors["other"])]},
    )
    assert spoofed_create.status_code == 201
    assert spoofed_create.json()["user_id"] == actors["other"]["id"]
    assert http.post(
        f"{urls['gateway']}/api/chat/sessions/{session_id}/messages", headers=actors["other"]["headers"],
        json={"message": "hello", "user_id": owner["id"]},
    ).status_code == 422


def test_owner_mutations_remain_available(live_services, actors, ready_document):
    http, gateway = live_services["http"], live_services["urls"]["gateway"]
    owner = actors["owner"]
    created = http.post(
        f"{gateway}/api/chat/sessions", headers=owner["headers"],
        json={"title": "Owned chat", "selected_document_ids": [ready_document(owner)]},
    )
    created.raise_for_status()
    session_id = created.json()["id"]
    history_url = f"{gateway}/api/chat/sessions/{session_id}"
    assert http.post(
        f"{gateway}/api/chat/sessions/{session_id}/messages", headers=owner["headers"],
        json={"message": "hello"},
    ).status_code == 200
    assert http.delete(
        f"{gateway}/api/chat/sessions/{session_id}/messages", headers=owner["headers"],
    ).status_code == 204
    history = http.get(history_url, headers=owner["headers"])
    assert history.status_code == 200
    assert history.json()["messages"] == []
    assert http.delete(
        f"{gateway}/api/chat/sessions/{session_id}", headers=owner["headers"],
    ).status_code == 204
    assert http.get(history_url, headers=owner["headers"]).status_code == 404


def test_removed_account_credentials_are_rejected_everywhere(live_services, actors):
    http, urls = live_services["http"], live_services["urls"]
    created = http.post(
        f"{urls['gateway']}/api/users", headers=actors["admin"]["headers"],
        json={"username": "departing", "password": "password123", "role": "employee"},
    )
    assert created.status_code == 200
    login = http.post(
        f"{urls['gateway']}/api/auth/login",
        json={"username": "departing", "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert http.delete(
        f"{urls['gateway']}/api/users/{created.json()['id']}",
        headers=actors["admin"]["headers"],
    ).status_code == 204
    for service, path in (
        ("gateway", "/api/documents"), ("identity", "/api/auth/me"),
        ("ingestion", "/api/documents"), ("rag", "/api/chat/sessions"),
    ):
        assert http.get(f"{urls[service]}{path}", headers=headers).status_code == 401


@pytest.mark.parametrize("changes", [
    {"role": "superuser"}, {"role": 1}, {"username": "   "},
    {"password": "x" * 73}, {"password": "é" * 37},
])
def test_invalid_account_requests_are_rejected(live_services, actors, changes):
    response = live_services["http"].post(
        f"{live_services['urls']['gateway']}/api/users",
        headers=actors["admin"]["headers"],
        json={"username": "invalid-account", "password": "password123", "role": "employee", **changes},
    )
    assert response.status_code == 422


def test_password_byte_boundary_and_login_contract(live_services, actors):
    http, gateway = live_services["http"], live_services["urls"]["gateway"]
    credentials = {"username": "byte-boundary", "password": "é" * 36}
    created = http.post(
        f"{gateway}/api/users", headers=actors["admin"]["headers"],
        json={**credentials, "role": "employee"},
    )
    assert created.status_code == 200
    response = http.post(f"{gateway}/api/auth/login", json=credentials)
    assert response.status_code == 200
    profile = http.get(
        f"{gateway}/api/auth/me",
        headers={"Authorization": f"Bearer {response.json()['access_token']}"},
    )
    assert profile.status_code == 200
    assert profile.json()["id"] == created.json()["id"]
    assert profile.json()["role"] == "employee"
    assert http.post(
        f"{gateway}/api/auth/login", json={**credentials, "role": "admin"},
    ).status_code == 422


def test_anonymous_operations_cannot_trust_identity_headers(live_services, actors):
    http, urls = live_services["http"], live_services["urls"]
    forged = {"X-User-ID": actors["admin"]["id"], "X-User-Role": "admin"}
    operations = {
        "identity": [("GET", "/api/users"), ("POST", "/api/users"), ("POST", "/api/auth/logout")],
        "ingestion": [
            ("POST", "/api/documents"), ("GET", "/api/documents"), ("GET", "/api/jobs/unknown"),
            ("PUT", "/api/documents/unknown/access"), ("POST", "/api/documents/unknown/reindex"),
            ("DELETE", "/api/documents/unknown"), ("DELETE", "/api/documents"),
        ],
        "rag": [
            ("POST", "/api/chat/sessions/unknown/messages"), ("GET", "/api/chat/sessions"),
            ("POST", "/api/chat/sessions"), ("GET", "/api/chat/sessions/unknown"),
            ("DELETE", "/api/chat/sessions/unknown/messages"), ("DELETE", "/api/chat/sessions/unknown"),
        ],
    }
    for service, requests in operations.items():
        for method, path in requests:
            for entrypoint in (service, "gateway"):
                response = http.request(method, f"{urls[entrypoint]}{path}", headers=forged)
                assert response.status_code == 401, (entrypoint, method, path, response.text)




def test_upload_identity_sharing_and_deletion_permissions(live_services, actors, upload_document):
    http, urls = live_services["http"], live_services["urls"]
    gateway = urls["gateway"]
    owner, other, admin = actors["owner"], actors["other"], actors["admin"]
    uploaded = upload_document(owner)
    document_id = uploaded["id"]
    documents = http.get(f"{gateway}/api/documents", headers=admin["headers"]).json()["items"]
    document = next(item for item in documents if item["id"] == document_id)
    assert document["uploaded_by_id"] == owner["id"]
    for service in ("gateway", "ingestion"):
        denied = http.post(
            f"{urls[service]}/api/documents", headers=other["headers"],
            files={"file": ("denied.pdf", b"%PDF-1.4", "application/pdf")},
            data={"allowed_users": owner["id"], "user_role": "admin"},
        )
        assert denied.status_code == 400
    shared = http.put(
        f"{gateway}/api/documents/{document_id}/access", headers=admin["headers"],
        json={"access_list": [owner["id"], other["id"]]},
    )
    assert shared.status_code == 200
    visible = http.get(f"{gateway}/api/documents", headers=other["headers"]).json()["items"]
    assert document_id in {item["id"] for item in visible}
    for service in ("gateway", "ingestion"):
        assert http.delete(
            f"{urls[service]}/api/documents/{document_id}", headers=other["headers"],
        ).status_code == 404
    assert http.delete(
        f"{gateway}/api/documents/{document_id}", headers=owner["headers"],
    ).status_code == 503
    owner_deleted = http.get(f"{gateway}/api/documents", headers=admin["headers"]).json()["items"]
    assert document_id not in {item["id"] for item in owner_deleted}
    second = upload_document(owner)
    assert http.delete(
        f"{gateway}/api/documents/{second['id']}", headers=admin["headers"],
    ).status_code == 503
    third = upload_document(admin)
    http.put(
        f"{gateway}/api/documents/{third['id']}/access", headers=admin["headers"],
        json={"access_list": [other["id"]]},
    ).raise_for_status()
    visible = http.get(f"{gateway}/api/documents", headers=other["headers"]).json()["items"]
    assert third["id"] in {item["id"] for item in visible}
    assert http.delete(f"{gateway}/api/documents", headers=admin["headers"]).status_code == 503
    assert http.get(
        f"{gateway}/api/documents/{third['id']}/source", headers=other["headers"],
    ).status_code == 404


def test_validation_errors_do_not_echo_credentials(live_services, actors):
    http, gateway = live_services["http"], live_services["urls"]["gateway"]
    private_value = "private-validation-fixture-do-not-echo-" * 3
    response = http.post(
        f"{gateway}/api/auth/login", json={"username": "admin", "password": private_value},
    )
    assert response.status_code == 422
    assert private_value not in response.text
    created = http.post(
        f"{gateway}/api/users", headers=actors["admin"]["headers"],
        json={"username": "invalid-password-fixture", "password": private_value, "role": "employee"},
    )
    assert created.status_code == 422
    assert private_value not in created.text
