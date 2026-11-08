"""Account removal and ownership transfer regression tests (Ticket 16).

Verifies that deleting an account:
1. Requires a named active administrator recipient if the account owns documents.
2. Rejects invalid, departing, or non-admin recipients.
3. Atomically transfers document ownership to the named administrator while
   preserving the document PDFs, original uploader attribution, and existing recipient grants.
4. Irreversibly deletes the departing account's private conversations without transferring them.
5. Inactivates the departing account's credentials across all microservices immediately.
"""
import uuid
import pytest


def _create_user(http, gateway, admin_headers, username, role="employee"):
    res = http.post(
        f"{gateway}/api/users",
        headers=admin_headers,
        json={"username": username, "password": "password123", "role": role},
    )
    res.raise_for_status()
    user_data = res.json()

    login_res = http.post(
        f"{gateway}/api/auth/login",
        json={"username": username, "password": "password123"},
    )
    login_res.raise_for_status()
    login_data = login_res.json()
    return {
        **user_data,
        "token": login_data["access_token"],
        "headers": {"Authorization": f"Bearer {login_data['access_token']}"},
    }


def test_account_removal_requires_named_admin_when_owning_documents(
    live_services, actors, upload_document
):
    http, urls = live_services["http"], live_services["urls"]
    gateway = urls["gateway"]
    admin = actors["admin"]

    # 1. Create a departing employee account
    dep_name = f"departing_{uuid.uuid4().hex[:6]}"
    departing = _create_user(http, gateway, admin["headers"], dep_name)

    # 2. Upload a document owned by this departing user
    uploaded = upload_document(departing)
    doc_id = uploaded["id"]

    # 3. Attempt deletion without transfer_to -> must fail (400)
    del_no_recipient = http.delete(
        f"{gateway}/api/users/{departing['id']}",
        headers=admin["headers"],
    )
    assert del_no_recipient.status_code == 400

    # 4. Attempt transfer to self (departing user) -> must fail (400)
    del_self = http.delete(
        f"{gateway}/api/users/{departing['id']}?transfer_to={departing['id']}",
        headers=admin["headers"],
    )
    assert del_self.status_code == 400

    # 5. Attempt transfer to non-existent user -> must fail (400)
    del_nonexistent = http.delete(
        f"{gateway}/api/users/{departing['id']}?transfer_to={uuid.uuid4()}",
        headers=admin["headers"],
    )
    assert del_nonexistent.status_code == 400

    # 6. Attempt transfer to non-admin employee -> must fail (400)
    del_to_employee = http.delete(
        f"{gateway}/api/users/{departing['id']}?transfer_to={actors['other']['id']}",
        headers=admin["headers"],
    )
    assert del_to_employee.status_code == 400

    # 7. Departing user and owned document remain intact after rejected attempts
    docs_after = http.get(f"{gateway}/api/documents", headers=departing["headers"])
    assert docs_after.status_code == 200
    assert any(d["id"] == doc_id for d in docs_after.json()["items"])


def test_valid_account_transfer_preserves_attribution_grants_and_cleans_history(
    live_services, actors, upload_document, ready_document):
    http, urls = live_services["http"], live_services["urls"]
    gateway = urls["gateway"]
    admin = actors["admin"]
    other = actors["other"]

    # 1. Create departing employee
    dep_name = f"dep_transfer_{uuid.uuid4().hex[:6]}"
    departing = _create_user(http, gateway, admin["headers"], dep_name)

    # 2. Upload document owned by departing user
    uploaded = upload_document(departing)
    doc_id = uploaded["id"]

    # 3. Share document with 'other' employee
    share_res = http.put(
        f"{gateway}/api/documents/{doc_id}/access",
        headers=admin["headers"],
        json={"access_list": [departing["id"], other["id"]]},
    )
    assert share_res.status_code == 200

    # 4. Departing user creates a private conversation
    chat_create = http.post(
        f"{gateway}/api/chat/sessions",
        headers=departing["headers"],
        json={"title": "Private Departing Chat", "selected_document_ids": [ready_document(departing)]},
    )
    chat_create.raise_for_status()
    session_id = chat_create.json()["id"]
    http.post(
        f"{gateway}/api/chat/sessions/{session_id}/messages", headers=departing["headers"],
        json={ "message": "hello"},
    ).raise_for_status()

    # 5. Valid deletion with transfer to active admin
    delete_res = http.delete(
        f"{gateway}/api/users/{departing['id']}?transfer_to={admin['id']}",
        headers=admin["headers"],
    )
    assert delete_res.status_code == 204

    # 6. Verify departing credentials fail everywhere (401)
    for service, path in (
        ("gateway", "/api/documents"),
        ("identity", "/api/auth/me"),
        ("ingestion", "/api/documents"),
        ("rag", "/api/chat/sessions"),
    ):
        assert http.get(f"{urls[service]}{path}", headers=departing["headers"]).status_code == 401

    # 7. Verify document ownership transferred to admin
    admin_docs = http.get(f"{gateway}/api/documents", headers=admin["headers"]).json()["items"]
    transferred_doc = next(d for d in admin_docs if d["id"] == doc_id)
    assert transferred_doc["owner_id"] == admin["id"]
    # Original uploader attribution is preserved
    assert transferred_doc["uploaded_by_id"] == departing["id"]
    # Existing recipient grant to other employee is preserved
    assert other["id"] in transferred_doc["access_list"]

    # 8. Recipient 'other' still has access to the document
    other_docs = http.get(f"{gateway}/api/documents", headers=other["headers"]).json()["items"]
    assert any(d["id"] == doc_id for d in other_docs)

    # 9. Private conversation was irreversibly deleted; admin does NOT inherit it
    admin_session_check = http.get(
        f"{gateway}/api/chat/sessions/{session_id}",
        headers=admin["headers"],
    )
    assert admin_session_check.status_code == 404
