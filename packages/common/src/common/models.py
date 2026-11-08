"""Database schema.

Every timestamp is a timezone-aware UTC datetime in Python. Enumerated text
columns are guarded by CHECK constraints, and relationships that the database
can enforce are foreign keys.
"""
import datetime
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    TypeDecorator,
)
from sqlalchemy.orm import relationship

from common.database import Base

USER_ROLES = ("admin", "employee")
DOCUMENT_STATUSES = ("queued", "processing", "searchable", "failed", "deleting", "cleanup_pending")
JOB_STATUSES = ("queued", "processing", "completed", "failed")
JOB_STAGES = (
    "queued", "claimed", "parsing", "chunking", "embedding", "indexing",
    "completed", "failed", "cancelled", "superseded",
)
MESSAGE_ROLES = ("user", "assistant")


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _one_of(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    allowed = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({allowed})", name=name)


class UTCDateTime(TypeDecorator):
    """Stores UTC instants; always returns aware UTC datetimes.

    PostgreSQL keeps `timestamptz`. SQLite (tests) has no time zones, so values
    are stored as naive UTC and re-tagged on the way out. Naive input is
    rejected rather than guessed at.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetimes are not allowed; use common.models.utcnow()")
        value = value.astimezone(datetime.timezone.utc)
        return value.replace(tzinfo=None) if dialect.name == "sqlite" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=datetime.timezone.utc)
        return value.astimezone(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (_one_of("role", USER_ROLES, "ck_users_role"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="employee")
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)
    # Attribution only: the creating admin may be deleted later.
    created_by = Column(String, nullable=True)


class DocumentGrant(Base):
    """An employee who may read and query a document they don't own."""

    __tablename__ = "document_access"

    document_id = Column(String, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True)
    position = Column(Integer, nullable=False, default=0)
    granted_at = Column(UTCDateTime, default=utcnow, nullable=False)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        _one_of("status", DOCUMENT_STATUSES, "ck_documents_status"),
        CheckConstraint("version >= 1", name="ck_documents_version"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String, nullable=False)
    source = Column(String, nullable=False)
    # Attribution only: survives the uploader's account being deleted.
    uploaded_by_id = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    uploaded_at = Column(UTCDateTime, default=utcnow, nullable=False)
    storage_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued", index=True)
    version = Column(Integer, nullable=False, default=1)
    parser = Column(String, nullable=True)
    embedding_model = Column(String, nullable=True)
    embedding_dims = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    pages_parsed = Column(Integer, nullable=False, default=0)
    chunks_created = Column(Integer, nullable=False, default=0)
    chunks_indexed = Column(Integer, nullable=False, default=0)

    grants = relationship(
        DocumentGrant,
        cascade="all, delete-orphan",
        order_by=DocumentGrant.position,
        lazy="selectin",
        passive_deletes=True,
    )

    @property
    def access_list(self) -> list[str]:
        return [grant.user_id for grant in self.grants]

    @access_list.setter
    def access_list(self, user_ids) -> None:
        # Reuse existing rows so an unchanged grant is never deleted and re-inserted.
        existing = {grant.user_id: grant for grant in self.grants}
        updated = []
        for position, user_id in enumerate(dict.fromkeys(user_ids or [])):
            grant = existing.get(user_id) or DocumentGrant(user_id=user_id)
            grant.position = position
            updated.append(grant)
        self.grants = updated


class ChatSessionDocument(Base):
    """A document a chat answers from, fixed when the chat is created.

    `document_id` is deliberately not a foreign key: deleting a document must not
    silently shrink a chat's evidence set. The chat instead stops answering
    because a selected source is missing.
    """

    __tablename__ = "chat_session_documents"

    session_id = Column(String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), primary_key=True)
    document_id = Column(String, primary_key=True, index=True)
    position = Column(Integer, nullable=False, default=0)


class ChatSessionModel(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (CheckConstraint("revision >= 0", name="ck_chat_sessions_revision"),)

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title = Column(String, nullable=False, default="New chat")
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True)
    revision = Column(Integer, nullable=False, default=0)
    # Per-chat request lease: one mutation at a time.
    busy_until = Column(UTCDateTime, nullable=True)
    request_id = Column(String, nullable=True)

    documents = relationship(
        ChatSessionDocument,
        cascade="all, delete-orphan",
        order_by=ChatSessionDocument.position,
        lazy="selectin",
        passive_deletes=True,
    )
    messages = relationship(
        "ChatMessageModel", back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def selected_document_ids(self) -> list[str]:
        return [link.document_id for link in self.documents]

    @selected_document_ids.setter
    def selected_document_ids(self, document_ids) -> None:
        if self.documents:
            raise ValueError("A chat's documents are fixed when it is created")
        self.documents = [
            ChatSessionDocument(document_id=document_id, position=position)
            for position, document_id in enumerate(dict.fromkeys(document_ids or []))
        ]


class ChatMessageModel(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        _one_of("role", MESSAGE_ROLES, "ck_chat_messages_role"),
        CheckConstraint("chunks_used >= 0", name="ck_chat_messages_chunks_used"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(
        String, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    # Provenance snapshots of an answer, read and written as a whole.
    citations = Column(JSON, nullable=False, default=list)
    source_document_ids = Column(JSON, nullable=False, default=list)
    unavailable = Column(Boolean, nullable=False, default=False)
    chunks_used = Column(Integer, nullable=False, default=0)
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)
    session = relationship("ChatSessionModel", back_populates="messages")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        _one_of("status", JOB_STATUSES, "ck_ingestion_jobs_status"),
        _one_of("stage", JOB_STAGES, "ck_ingestion_jobs_stage"),
        CheckConstraint("attempts >= 0", name="ck_ingestion_jobs_attempts"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(
        String, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued", index=True)
    stage = Column(String, nullable=False, default="queued")
    worker_id = Column(String, nullable=True)
    lease_until = Column(UTCDateTime, nullable=True)
    document_version = Column(Integer, nullable=False, default=1)
    attempts = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)
    pages_parsed = Column(Integer, nullable=False, default=0)
    chunks_created = Column(Integer, nullable=False, default=0)
    chunks_indexed = Column(Integer, nullable=False, default=0)
    created_at = Column(UTCDateTime, default=utcnow, nullable=False)
    updated_at = Column(UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False)
