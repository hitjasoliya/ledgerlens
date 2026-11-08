from __future__ import annotations

import datetime
from pathlib import Path
import sys
from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

root_dir = Path(__file__).resolve().parent.parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from common.auth import create_access_token, get_password_hash
from common.config import settings
import common.database
from common.database import Base, SessionLocal, engine
from common.models import (
    ChatMessageModel,
    ChatSessionModel,
    Document,
    User,
    utcnow,
)
from common.schemas import Citation
from common.search import DependencyUnavailable
from services.rag.components import (
    CitationParser,
    QueryRouter,
    bound_context_and_history,
)
from services.rag.main import app as rag_app
from services.rag.main import rag_engine


@pytest.fixture(scope="session")
def setup_db():
    if hasattr(common.database, "initialize_database"):
        common.database.initialize_database()
    else:
        Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def db_session(setup_db):
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(setup_db):
    with TestClient(rag_app) as c:
        yield c


@pytest.fixture
def users(db_session):
    user1 = db_session.get(User, "test-user-1")
    if not user1:
        user1 = User(
            id="test-user-1",
            username="employee_one",
            hashed_password=get_password_hash("password123"),
            role="employee",
        )
        db_session.add(user1)

    user2 = db_session.get(User, "test-user-2")
    if not user2:
        user2 = User(
            id="test-user-2",
            username="employee_two",
            hashed_password=get_password_hash("password123"),
            role="employee",
        )
        db_session.add(user2)

    admin = db_session.get(User, "test-admin-1")
    if not admin:
        admin = User(
            id="test-admin-1",
            username="admin_user",
            hashed_password=get_password_hash("password123"),
            role="admin",
        )
        db_session.add(admin)

    db_session.commit()

    token1 = create_access_token(
        {"id": user1.id, "sub": user1.username, "role": user1.role}
    )
    token2 = create_access_token(
        {"id": user2.id, "sub": user2.username, "role": user2.role}
    )
    admin_token = create_access_token(
        {"id": admin.id, "sub": admin.username, "role": admin.role}
    )

    return {
        "user1": {"id": user1.id, "headers": {"Authorization": f"Bearer {token1}"}},
        "user2": {"id": user2.id, "headers": {"Authorization": f"Bearer {token2}"}},
        "admin": {
            "id": admin.id,
            "headers": {"Authorization": f"Bearer {admin_token}"},
        },
    }


@pytest.fixture
def sample_document(db_session, users):
    doc_id = f"doc-{uuid.uuid4().hex[:8]}"
    doc = Document(
        id=doc_id,
        filename="Q2_Report.pdf",
        source="Q2_Report.pdf",
        uploaded_by_id=users["user1"]["id"],
        owner_id=users["user1"]["id"],
        access_list=[],
        storage_path=f"storage_{doc_id}.pdf",
        status="searchable",
        version=1,
        parser="docling",
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_dims=settings.EMBEDDING_DIMS,
        pages_parsed=5,
        chunks_created=10,
        chunks_indexed=10,
    )
    db_session.add(doc)
    db_session.commit()
    return doc



def test_readiness_tracks_generation_dependency_recovery(client):
    with patch.object(rag_engine.es_client, "is_available", return_value=True), patch.object(
        rag_engine.embedder, "is_available", return_value=True
    ), patch.object(rag_engine.generator, "is_available", return_value=False) as generation:
        assert client.get("/ready").status_code == 503
        generation.return_value = True
        assert client.get("/ready").status_code == 200


def test_unauthenticated_requests_rejected(client):
    assert (
        client.post(
            f"/api/chat/sessions/s1/messages", json={"message": "hi"}
        ).status_code
        == 401
    )
    assert client.get("/api/chat/sessions").status_code == 401
    assert (
        client.post(
            "/api/chat/sessions", json={"title": "new", "selected_document_ids": ["d1"]}
        ).status_code
        == 401
    )
    assert client.get("/api/chat/sessions/s1").status_code == 401
    assert client.delete(f"/api/chat/sessions/s1/messages").status_code == 401
    assert client.delete(f"/api/chat/sessions/s1").status_code == 401
    assert (
        client.post(
            "/api/chat/sessions/s1/regenerate", json={"message_id": "m1"}
        ).status_code
        == 401
    )


def test_resource_id_validation(client, users):
    # Malformed ids never reach a handler: 422 from validation, or 404 when they
    # can't even match a route (e.g. a slash or an empty segment).
    u1 = users["user1"]
    invalid_ids = ["bad session id", "bad/slash", "bad@char!", "", "a" * 129]
    for bad_id in invalid_ids:
        assert (
            client.post(
                f"/api/chat/sessions/{bad_id}/messages",
                headers=u1["headers"],
                json={"message": "hello"},
            ).status_code
            in (404, 405, 422)
        )
        assert (
            client.delete(f"/api/chat/sessions/{bad_id}/messages", headers=u1["headers"]
            ).status_code
            in (404, 405, 422)
        )
        assert (
            client.delete(f"/api/chat/sessions/{bad_id}", headers=u1["headers"]
            ).status_code
            in (404, 405, 422)
        )

    res_extra = client.post(
        f"/api/chat/sessions/valid-id/messages",
        headers=u1["headers"],
        json={
            "message": "hello",
            "user_id": "override_user"},
    )
    assert res_extra.status_code == 422


def test_session_create_and_load_owner_only(client, users, sample_document):
    u1 = users["user1"]
    u2 = users["user2"]
    admin = users["admin"]

    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={
            "title": "Alpha Project",
            "selected_document_ids": [sample_document.id],
        },
    )
    assert res_create.status_code == 201
    sess = res_create.json()
    sess_id = sess["id"]
    assert sess["selected_document_ids"] == [sample_document.id]
    assert sess["revision"] == 0

    res_owner = client.get(f"/api/chat/sessions/{sess_id}", headers=u1["headers"])
    assert res_owner.status_code == 200
    assert res_owner.json()["id"] == sess_id

    assert (
        client.get(
            f"/api/chat/sessions/{sess_id}", headers=u2["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get(
            f"/api/chat/sessions/{sess_id}", headers=admin["headers"]
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/api/chat/sessions/absent-session-id", headers=u1["headers"]
        ).status_code
        == 404
    )


def test_session_listing_is_owner_scoped(client, users, db_session, sample_document):
    u1 = users["user1"]
    u2 = users["user2"]
    admin = users["admin"]
    sample_document.access_list = [u2["id"]]
    db_session.commit()

    r1 = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "U1 Session", "selected_document_ids": [sample_document.id]},
    )
    assert r1.status_code == 201
    u1_sess_id = r1.json()["id"]

    r2 = client.post(
        "/api/chat/sessions",
        headers=u2["headers"],
        json={"title": "U2 Session", "selected_document_ids": [sample_document.id]},
    )
    assert r2.status_code == 201
    u2_sess_id = r2.json()["id"]

    u1_listing = client.get("/api/chat/sessions", headers=u1["headers"]).json()["items"]
    u1_ids = {s["id"] for s in u1_listing}
    assert u1_sess_id in u1_ids
    assert u2_sess_id not in u1_ids

    u2_listing = client.get("/api/chat/sessions", headers=u2["headers"]).json()["items"]
    u2_ids = {s["id"] for s in u2_listing}
    assert u2_sess_id in u2_ids
    assert u1_sess_id not in u2_ids

    admin_listing = client.get(
        "/api/chat/sessions", headers=admin["headers"]
    ).json()["items"]
    admin_ids = {s["id"] for s in admin_listing}
    assert u1_sess_id not in admin_ids
    assert u2_sess_id not in admin_ids


def test_chat_nonexistent_session_returns_404(client, users):
    u1 = users["user1"]
    res = client.post(
        f"/api/chat/sessions/nonexistent-sess-id/messages",
        headers=u1["headers"],
        json={"message": "hello"},
    )
    assert res.status_code == 404


def test_chat_greeting_is_answered_without_retrieval(client, users, sample_document):
    u1 = users["user1"]
    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Greeting Test", "selected_document_ids": [sample_document.id]},
    )
    sess_id = res_create.json()["id"]

    with patch.object(
        rag_engine.generator,
        "generate_greeting",
        return_value="Hello! I am LedgerLens AI.",
    ):
        res = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "Hello!"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == "Hello! I am LedgerLens AI."
        assert data["citations"] == []
        assert data["chunks_used"] == 0

    sess_res = client.get(f"/api/chat/sessions/{sess_id}", headers=u1["headers"])
    sess_data = sess_res.json()
    assert sess_data["selected_document_ids"] == [sample_document.id]
    assert len(sess_data["messages"]) == 2


def test_chat_requires_documents_and_answers_from_them(client, users, sample_document):
    u1 = users["user1"]
    before = client.get("/api/chat/sessions", headers=u1["headers"]).json()["total"]
    no_docs = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Doc Question Test", "selected_document_ids": []},
    )
    assert no_docs.status_code == 422
    assert client.get("/api/chat/sessions", headers=u1["headers"]).json()["total"] == before

    sess_id = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Doc Question Test", "selected_document_ids": [sample_document.id]},
    ).json()["id"]

    retrieved_chunk = {
        "chunk_id": "chunk_q2_1",
        "document_id": sample_document.id,
        "filename": sample_document.filename,
        "page_number": 2,
        "text": "Q2 revenue was $50 million.",
        "version": 1,
    }
    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[retrieved_chunk]
    ), patch.object(
        rag_engine.generator,
        "generate",
        return_value="Q2 revenue was $50M [Citation: chunk_q2_1].",
    ):
        res_ask = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "help me understand revenue"},
        )
    assert res_ask.status_code == 200
    chat_data = res_ask.json()
    assert len(chat_data["citations"]) == 1
    assert chat_data["citations"][0]["chunk_id"] == "chunk_q2_1"
    assert chat_data["citations"][0]["page"] == 2


def test_missing_or_invalid_citations_causes_explicit_abstention(
    client, users, sample_document
):
    u1 = users["user1"]
    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Abstain Citation Test", "selected_document_ids": [sample_document.id]},
    )
    sess_id = res_create.json()["id"]

    chunk = {
        "chunk_id": "valid_chunk_1",
        "document_id": sample_document.id,
        "filename": sample_document.filename,
        "page_number": 1,
        "text": "Operational metrics.",
        "version": 1,
    }

    # Model returns text citing an UNKNOWN chunk ID
    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ), patch.object(
        rag_engine.generator,
        "generate",
        return_value="Unsupported statement [Citation: fabricated_chunk_xyz].",
    ):
        res = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "Explain operations"},
        )
        assert res.status_code == 200
        data = res.json()
        # Must abstain explicitly rather than releasing unsupported answer
        assert "could not find sufficient information" in data["answer"].lower()
        assert data["citations"] == []
        assert data["chunks_used"] == 0

    # Model returns text with NO citations
    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ), patch.object(
        rag_engine.generator,
        "generate",
        return_value="Uncited arbitrary claims about profit margins.",
    ):
        res_no_cite = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "Explain profit"},
        )
        assert res_no_cite.status_code == 200
        data_no_cite = res_no_cite.json()
        assert "could not find sufficient information" in data_no_cite["answer"].lower()
        assert data_no_cite["citations"] == []
        assert data_no_cite["chunks_used"] == 0


def test_reauthorize_all_selected_sources_before_generation(
    client, users, sample_document, db_session
):
    u1 = users["user1"]
    # Create second document
    doc2 = Document(
        id=f"doc-{uuid.uuid4().hex[:8]}",
        filename="Q2_Other.pdf",
        source="Q2_Other.pdf",
        uploaded_by_id=u1["id"],
        owner_id=u1["id"],
        access_list=[],
        storage_path="storage_doc2.pdf",
        status="searchable",
        version=1,
        parser="docling",
        embedding_model=settings.EMBEDDING_MODEL,
        embedding_dims=settings.EMBEDDING_DIMS,
    )
    db_session.add(doc2)
    db_session.commit()

    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={
            "title": "Multi-Source Selection",
            "selected_document_ids": [sample_document.id, doc2.id],
        },
    )
    sess_id = res_create.json()["id"]

    # Revoke doc2 before search
    doc2.status = "failed"
    db_session.commit()

    chunk = {
        "chunk_id": "c1",
        "document_id": sample_document.id,
        "filename": sample_document.filename,
        "page_number": 1,
        "text": "Data.",
        "version": 1,
    }
    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ):
        res = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "Analyze revenue"},
        )
        # Even though sample_document was searchable, doc2 was in selection and unavailable
        assert res.status_code == 409
        assert "unavailable" in res.json()["detail"].lower()


def test_chat_documents_are_fixed_at_creation(client, users, sample_document):
    u1 = users["user1"]
    sess = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "New chat", "selected_document_ids": [sample_document.id]},
    ).json()

    res_mod = client.put(
        f"/api/chat/sessions/{sess['id']}/selection",
        headers=u1["headers"],
        json={"selected_document_ids": [], "revision": sess["revision"]},
    )
    assert res_mod.status_code in (404, 405)
    reloaded = client.get(f"/api/chat/sessions/{sess['id']}", headers=u1["headers"]).json()
    assert reloaded["selected_document_ids"] == [sample_document.id]


def _ask(client, headers, sess_id, message, sample_document):
    chunk = {
        "chunk_id": "chunk_title_1",
        "document_id": sample_document.id,
        "filename": sample_document.filename,
        "page_number": 1,
        "text": "Revenue was $50 million.",
        "version": 1,
    }
    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ), patch.object(
        rag_engine.generator, "generate", return_value="Revenue was $50M [Citation: chunk_title_1]."
    ):
        return client.post(
            f"/api/chat/sessions/{sess_id}/messages", headers=headers, json={"message": message}
        )


def test_first_document_question_names_an_untitled_chat(client, users, sample_document):
    u1 = users["user1"]
    untitled = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "New chat", "selected_document_ids": [sample_document.id]},
    ).json()
    long_question = "What was total revenue for the quarter, and how did it compare with the prior year period overall?"
    assert _ask(client, u1["headers"], untitled["id"], long_question, sample_document).status_code == 200
    title = client.get(f"/api/chat/sessions/{untitled['id']}", headers=u1["headers"]).json()["title"]
    assert title.startswith("What was total revenue for the quarter")
    assert len(title) <= 60

    assert _ask(client, u1["headers"], untitled["id"], "And net income?", sample_document).status_code == 200
    again = client.get(f"/api/chat/sessions/{untitled['id']}", headers=u1["headers"]).json()["title"]
    assert again == title

    named = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Board pack review", "selected_document_ids": [sample_document.id]},
    ).json()
    assert _ask(client, u1["headers"], named["id"], "What was revenue?", sample_document).status_code == 200
    kept = client.get(f"/api/chat/sessions/{named['id']}", headers=u1["headers"]).json()["title"]
    assert kept == "Board pack review"


def test_regeneration_replaces_latest_assistant_only(client, users, sample_document):
    u1 = users["user1"]
    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Regen Test", "selected_document_ids": [sample_document.id]},
    )
    sess_id = res_create.json()["id"]

    chunk = {
        "chunk_id": "chunk_1",
        "document_id": sample_document.id,
        "filename": sample_document.filename,
        "page_number": 1,
        "text": "EBITDA was $12M.",
        "version": 1,
    }

    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ), patch.object(
        rag_engine.generator, "generate", return_value="EBITDA was $12M [Citation: chunk_1]."
    ):
        res1 = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "What was EBITDA?"},
        )
        assert res1.status_code == 200
        asst1_id = res1.json()["message_id"]

        res2 = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "Confirm EBITDA again"},
        )
        assert res2.status_code == 200
        asst2_id = res2.json()["message_id"]

    # Attempting to regenerate earlier assistant turn (not latest) is rejected with 409
    res_early = client.post(
        f"/api/chat/sessions/{sess_id}/regenerate",
        headers=u1["headers"],
        json={"message_id": asst1_id},
    )
    assert res_early.status_code == 409
    assert "latest assistant turn" in res_early.json()["detail"].lower()

    # Regenerating latest assistant turn succeeds in-place without destroying prior turns
    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ), patch.object(
        rag_engine.generator,
        "generate",
        return_value="Confirmed EBITDA is $12M [Citation: chunk_1].",
    ):
        regen_res = client.post(
            f"/api/chat/sessions/{sess_id}/regenerate",
            headers=u1["headers"],
            json={"message_id": asst2_id},
        )
        assert regen_res.status_code == 200
        assert regen_res.json()["message_id"] == asst2_id

    # Verify all 4 messages remain intact
    sess_after = client.get(
        f"/api/chat/sessions/{sess_id}", headers=u1["headers"]
    ).json()
    assert len(sess_after["messages"]) == 4
    assert sess_after["messages"][3]["content"] == "Confirmed EBITDA is $12M [Citation: chunk_1]."


def test_clear_chat_preserves_documents(client, users, sample_document):
    u1 = users["user1"]
    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Clear Test", "selected_document_ids": [sample_document.id]},
    )
    sess_id = res_create.json()["id"]

    chunk = {
        "chunk_id": "chunk_1",
        "document_id": sample_document.id,
        "filename": sample_document.filename,
        "page_number": 1,
        "text": "Data.",
        "version": 1,
    }

    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ), patch.object(
        rag_engine.generator, "generate", return_value="Data answer [Citation: chunk_1]."
    ):
        client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "Analyze revenue"},
        )

    clear_res = client.delete(f"/api/chat/sessions/{sess_id}/messages", headers=u1["headers"]
    )
    assert clear_res.status_code == 204

    sess_after = client.get(
        f"/api/chat/sessions/{sess_id}", headers=u1["headers"]
    ).json()
    assert sess_after["messages"] == []
    assert sess_after["selected_document_ids"] == [sample_document.id]


def test_delete_chat_preserves_documents(client, users, sample_document, db_session):
    u1 = users["user1"]
    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Delete Test", "selected_document_ids": [sample_document.id]},
    )
    sess_id = res_create.json()["id"]

    del_res = client.delete(f"/api/chat/sessions/{sess_id}", headers=u1["headers"]
    )
    assert del_res.status_code == 204

    assert (
        client.get(
            f"/api/chat/sessions/{sess_id}", headers=u1["headers"]
        ).status_code
        == 404
    )

    doc = db_session.get(Document, sample_document.id)
    assert doc is not None
    assert doc.id == sample_document.id


def test_unavailable_answer_masking_on_access_revocation(
    client, users, sample_document, db_session
):
    u1 = users["user1"]
    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={
            "title": "Revocation Test",
            "selected_document_ids": [sample_document.id],
        },
    )
    sess_id = res_create.json()["id"]

    chunk = {
        "chunk_id": "c1",
        "document_id": sample_document.id,
        "filename": sample_document.filename,
        "page_number": 1,
        "text": "Confidential financial data.",
        "version": 1,
    }

    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client, "hybrid_search", return_value=[chunk]
    ), patch.object(
        rag_engine.generator,
        "generate",
        return_value="Secret answer [Citation: c1].",
    ):
        res = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "Reveal data"},
        )
        assert res.status_code == 200

    doc = db_session.get(Document, sample_document.id)
    doc.status = "deleting"
    db_session.commit()

    sess_res = client.get(
        f"/api/chat/sessions/{sess_id}", headers=u1["headers"]
    ).json()
    asst_msg = sess_res["messages"][1]
    assert asst_msg["unavailable"] is True
    assert asst_msg["citations"] == []
    assert asst_msg["chunks_used"] == 0
    assert "Secret answer" not in asst_msg["content"]
    assert "no longer available" in asst_msg["content"].lower()


def test_provider_failure_returns_503_truthfully(client, users, sample_document):
    u1 = users["user1"]
    res_create = client.post(
        "/api/chat/sessions",
        headers=u1["headers"],
        json={"title": "Fail 503 Test", "selected_document_ids": [sample_document.id]},
    )
    sess_id = res_create.json()["id"]

    with patch.object(
        rag_engine.embedder, "embed_query", return_value=[0.1] * settings.EMBEDDING_DIMS
    ), patch.object(
        rag_engine.es_client,
        "hybrid_search",
        side_effect=DependencyUnavailable("Search node down"),
    ):
        res = client.post(
            f"/api/chat/sessions/{sess_id}/messages",
            headers=u1["headers"],
            json={"message": "What is Q2 revenue?"},
        )
        assert res.status_code == 503
        assert "unavailable" in res.json()["detail"].lower()


def test_tiktoken_bounding_and_no_oversized_first_chunk():
    q = "What is the capital expenditure?"
    # Chunks: first chunk exceeds small token budget
    oversized_chunk = {
        "chunk_id": "c_huge",
        "document_id": "d1",
        "text": "word " * 500,
        "page_number": 1,
    }
    small_chunk = {
        "chunk_id": "c_small",
        "document_id": "d1",
        "text": "Small snippet.",
        "page_number": 1,
    }
    # Budget smaller than oversized chunk
    budgeted_chunks, budgeted_history = bound_context_and_history(
        question=q,
        chunks=[oversized_chunk, small_chunk],
        history=[],
        max_tokens=400,
    )
    # Oversized first chunk must not be included
    assert oversized_chunk not in budgeted_chunks




def test_grouped_citation_tags_are_accepted_only_when_every_reference_is_retrieved():
    """Models often group references in one tag; each must still be retrieved evidence."""
    chunks = [
        {"chunk_id": "doc-a_v1_p1_tab_1", "document_id": "doc-a", "filename": "a.pdf", "page_number": 1},
        {"chunk_id": "doc-a_v1_p1_par_2", "document_id": "doc-a", "filename": "a.pdf", "page_number": 1},
    ]
    parser = CitationParser()
    for answer in (
        "Net loss was (2,940) [Citation: doc-a_v1_p1_tab_1, doc-a_v1_p1_par_2].",
        "Net loss was (2,940) [Citation: doc-a_v1_p1_tab_1, Citation: doc-a_v1_p1_par_2].",
        "Net loss was (2,940) [Citation: doc-a_v1_p1_tab_1; doc-a_v1_p1_par_2].",
    ):
        citations, valid = parser.parse_citations(answer, chunks)
        assert valid
        assert [c.chunk_id for c in citations] == ["doc-a_v1_p1_tab_1", "doc-a_v1_p1_par_2"]

    for answer in (
        "Net loss was (2,940) [Citation: doc-a_v1_p1_tab_1, doc-b_v1_p1_tab_9].",
        "Net loss was (2,940) [Citation: doc-a_v1_p1_tab_1, see page 1].",
        "Net loss was (2,940) [Citation: ].",
    ):
        assert parser.parse_citations(answer, chunks) == ([], False)


def test_chat_list_is_paged_newest_first_without_messages(client, users, sample_document):
    u1 = users["user1"]
    created = [
        client.post(
            "/api/chat/sessions",
            headers=u1["headers"],
            json={"title": f"Paging {i}", "selected_document_ids": [sample_document.id]},
        ).json()["id"]
        for i in range(3)
    ]
    total = client.get("/api/chat/sessions", headers=u1["headers"]).json()["total"]

    first = client.get("/api/chat/sessions?limit=2", headers=u1["headers"]).json()
    assert first["limit"] == 2 and first["offset"] == 0 and first["total"] == total
    assert [item["id"] for item in first["items"]] == created[::-1][:2]
    assert "messages" not in first["items"][0]
    assert first["items"][0]["message_count"] == 0

    rest = client.get(f"/api/chat/sessions?limit=2&offset={total - 1}", headers=u1["headers"]).json()
    assert len(rest["items"]) == 1

    for bad in ("limit=0", "limit=201", "offset=-1"):
        assert client.get(f"/api/chat/sessions?{bad}", headers=u1["headers"]).status_code == 422
