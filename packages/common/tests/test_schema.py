"""The schema enforces its own invariants instead of trusting every caller."""
import datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from common import migrate
from common.models import (
    ChatSessionModel,
    Document,
    DocumentGrant,
    IngestionJob,
    User,
    utcnow,
)


@pytest.fixture
def bind(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'schema.sqlite'}")

    @event.listens_for(engine, "connect")
    def _foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    migrate.ensure_current(engine)
    yield engine
    engine.dispose()


def _user(db, name, role="employee"):
    user = User(id=name, username=name, hashed_password="x", role=role)
    db.add(user)
    db.flush()
    return user


def _document(db, owner, **fields):
    document = Document(
        id=fields.pop("id", "doc-1"), filename="a.pdf", source="a.pdf",
        uploaded_by_id=owner.id, owner_id=owner.id, storage_path="a.pdf", **fields,
    )
    db.add(document)
    db.flush()
    return document


def test_bootstrap_is_idempotent_and_refuses_foreign_databases(tmp_path, bind):
    migrate.ensure_current(bind)  # second run is a no-op

    stale = sa.create_engine(f"sqlite:///{tmp_path / 'stale.sqlite'}")
    with stale.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE users (id VARCHAR PRIMARY KEY)")
    with pytest.raises(RuntimeError, match="wipe the database"):
        migrate.ensure_current(stale)
    stale.dispose()


def test_enumerated_columns_reject_unknown_values(bind):
    with Session(bind) as db:
        db.add(User(id="u", username="u", hashed_password="x", role="superuser"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

        owner = _user(db, "owner")
        db.add(Document(
            id="d", filename="a.pdf", source="a.pdf", uploaded_by_id=owner.id,
            owner_id=owner.id, storage_path="a.pdf", status="half-done",
        ))
        with pytest.raises(IntegrityError):
            db.flush()


def test_grants_are_rows_that_follow_users_and_documents(bind):
    with Session(bind) as db:
        owner, reader, other = _user(db, "owner"), _user(db, "reader"), _user(db, "other")
        document = _document(db, owner, access_list=[reader.id, other.id, reader.id])
        db.commit()
        assert document.access_list == [reader.id, other.id]

        document.access_list = [other.id, reader.id]  # reorder keeps the same rows
        db.commit()
        assert document.access_list == [other.id, reader.id]

        db.delete(db.get(User, other.id))
        db.commit()
        db.expire_all()
        assert db.get(Document, "doc-1").access_list == [reader.id]

        db.delete(db.get(Document, "doc-1"))
        db.commit()
        assert db.scalars(sa.select(DocumentGrant)).all() == []

        with pytest.raises(IntegrityError):
            _document(db, owner, id="doc-2", access_list=["no-such-user"])


def test_jobs_and_chats_belong_to_existing_rows(bind):
    with Session(bind) as db:
        owner = _user(db, "owner")
        db.add(IngestionJob(document_id="missing", filename="a.pdf"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

        db.add(ChatSessionModel(user_id="missing"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()

        owner = db.get(User, "owner") or _user(db, "owner")
        document = _document(db, owner)
        db.add(IngestionJob(document_id=document.id, filename="a.pdf"))
        chat = ChatSessionModel(user_id=owner.id, selected_document_ids=[document.id])
        db.add(chat)
        db.commit()

        db.delete(db.get(Document, document.id))
        db.commit()
        assert db.scalars(sa.select(IngestionJob)).all() == []
        # A deleted source stays in the chat, so it can't silently answer from less.
        db.expire_all()
        assert db.get(ChatSessionModel, chat.id).selected_document_ids == ["doc-1"]


def test_chat_documents_cannot_change_after_creation(bind):
    with Session(bind) as db:
        owner = _user(db, "owner")
        chat = ChatSessionModel(user_id=owner.id, selected_document_ids=["a", "b"])
        db.add(chat)
        db.commit()
        with pytest.raises(ValueError, match="fixed"):
            chat.selected_document_ids = ["c"]


def test_timestamps_are_aware_utc_and_naive_input_is_rejected(bind):
    with Session(bind) as db:
        user = _user(db, "owner")
        db.commit()
        db.expire_all()
        created = db.get(User, "owner").created_at
        assert created.tzinfo is not None and created.utcoffset() == datetime.timedelta(0)
        assert abs((utcnow() - created).total_seconds()) < 60

        user = db.get(User, "owner")
        user.created_at = datetime.datetime(2026, 1, 1)
        with pytest.raises(StatementError, match="Naive datetimes"):
            db.flush()
