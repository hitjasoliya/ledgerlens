"""SQL authorization shared by document, retrieval, and saved-answer operations."""
from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from common.config import settings
from common.models import ChatMessageModel, ChatSessionModel, Document, User


def can_read(user: User, document: Document) -> bool:
    if document.status in ("deleting", "cleanup_pending"):
        return False
    return (
        user.role == "admin"
        or document.owner_id == user.id
        or user.id in (document.access_list or [])
    )


def _active_user(db: Session, user: User) -> User:
    identity = inspect(user).identity
    current = db.get(User, identity[0] if identity else user.id, populate_existing=True)
    if current is None or current.role not in ("admin", "employee"):
        raise HTTPException(status_code=401, detail="Account is not active")
    return current


def require_document(
    db: Session, document_id: str, user: User, searchable: bool = False
) -> Document:
    current = _active_user(db, user)
    document = db.get(Document, document_id, populate_existing=True)
    if document is None or not can_read(current, document):
        raise HTTPException(status_code=404, detail="Document not found")
    if searchable and document.status != "searchable":
        raise HTTPException(status_code=409, detail="Document is not searchable")
    return document


def require_selection(
    db: Session, conversation: ChatSessionModel, user: User
) -> list[Document]:
    current = _active_user(db, user)
    if conversation.user_id != current.id:
        raise HTTPException(status_code=404, detail="Conversation not found")
    identifiers = conversation.selected_document_ids or []
    if not identifiers:
        raise HTTPException(status_code=409, detail="Select at least one source document")
    documents = {
        document.id: document
        for document in db.scalars(
            select(Document).where(Document.id.in_(identifiers)).execution_options(populate_existing=True)
        )
    }
    for identifier in identifiers:
        document = documents.get(identifier)
        if document is None or not can_read(current, document) or document.status != "searchable":
            raise HTTPException(
                status_code=409,
                detail="A selected source is unavailable; restore access or start a new conversation",
            )
        if (
            document.embedding_model != settings.EMBEDDING_MODEL
            or document.embedding_dims != settings.EMBEDDING_DIMS
        ):
            raise HTTPException(status_code=409, detail="Selected source requires reindexing for the configured embedding model")
    return [documents[identifier] for identifier in identifiers]


def answer_available(db: Session, message: ChatMessageModel, user: User) -> bool:
    if message.role != "assistant":
        return True
    if message.unavailable:
        return False
    current = _active_user(db, user)
    identifiers = message.source_document_ids or []
    if not identifiers:
        # Greetings and abstentions have no sources.
        return not message.citations and not message.chunks_used
    documents = list(db.scalars(
        select(Document).where(Document.id.in_(identifiers)).execution_options(populate_existing=True)
    ))
    return len(documents) == len(set(identifiers)) and all(
        can_read(current, document) and document.status == "searchable" for document in documents
    )
