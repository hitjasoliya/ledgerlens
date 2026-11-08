from __future__ import annotations

import datetime
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import Session

from common.access import (
    _active_user,
    answer_available,
    can_read,
    require_document,
    require_selection,
)
from common.config import settings
from common.models import (
    ChatMessageModel,
    ChatSessionModel,
    Document,
    User,
    utcnow,
)
from common.schemas import (
    ChatMessageResponse,
    ChatResponse,
    ChatSessionResponse,
    ChatSessionSummary,
    Page,
    Citation,
    ClearChatResponse,
)
from common.search import DependencyUnavailable, Embedder, ESClient

try:
    from components import (
        CitationParser,
        DeterministicEvaluationGenerator,
        GeminiGenerator,
        QueryRouter,
        bound_context_and_history,
    )
except ImportError:
    from services.rag.components import (
        CitationParser,
        DeterministicEvaluationGenerator,
        GeminiGenerator,
        QueryRouter,
        bound_context_and_history,
    )

logger = logging.getLogger(__name__)


def _to_epoch_ms(dt: datetime.datetime | None) -> int:
    if dt is None:
        return 0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return int(dt.timestamp() * 1000)


def _serialize_message(
    db: Session, msg: ChatMessageModel, current_user: User
) -> ChatMessageResponse:
    if msg.role == "assistant":
        if not answer_available(db, msg, current_user):
            return ChatMessageResponse(
                id=msg.id,
                role="assistant",
                content="This answer is no longer available because access to one or more supporting documents has changed or been removed.",
                citations=[],
                chunks_used=0,
                unavailable=True,
                created_at=_to_epoch_ms(msg.created_at),
            )
    return ChatMessageResponse(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        citations=[Citation(**c) for c in (msg.citations or [])],
        chunks_used=msg.chunks_used,
        unavailable=msg.unavailable,
        created_at=_to_epoch_ms(msg.created_at),
    )


_UNTITLED = {"", "new chat"}
_TITLE_LIMIT = 60


def _is_untitled(title: Optional[str]) -> bool:
    return (title or "").strip().lower() in _UNTITLED


def _title_from_question(question: str) -> str:
    text = " ".join(question.split())
    if len(text) <= _TITLE_LIMIT:
        return text
    cut = text[: _TITLE_LIMIT - 1].rsplit(" ", 1)[0].rstrip(" ,;:")
    return f"{cut}…"


def _serialize_session(
    db: Session, sess: ChatSessionModel, current_user: User
) -> ChatSessionResponse:
    ordered = sorted(sess.messages, key=lambda m: (m.created_at, m.id))
    serialized_messages = [_serialize_message(db, m, current_user) for m in ordered]
    return ChatSessionResponse(
        id=sess.id,
        title=sess.title,
        user_id=sess.user_id,
        created_at=_to_epoch_ms(sess.created_at),
        updated_at=_to_epoch_ms(sess.updated_at),
        selected_document_ids=list(sess.selected_document_ids or []),
        revision=int(sess.revision),
        messages=serialized_messages,
    )


@contextmanager
def session_lock(
    db: Session,
    session_id: str,
    user_id: str,
    expected_revision: Optional[int] = None,
):
    now = utcnow()
    lease_until = now + datetime.timedelta(seconds=settings.CONVERSATION_LEASE_SECONDS)
    req_id = str(uuid.uuid4())

    sess = db.get(ChatSessionModel, session_id, populate_existing=True)
    if sess is None:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if sess.user_id != user_id:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if sess.busy_until is not None and sess.busy_until > now:
        raise HTTPException(
            status_code=409,
            detail="Conversation is currently processing another request",
        )
    if expected_revision is not None and sess.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail="Conflict: conversation has been modified",
        )

    conditions = [
        ChatSessionModel.id == session_id,
        ChatSessionModel.user_id == user_id,
        or_(ChatSessionModel.busy_until == None, ChatSessionModel.busy_until <= now),
    ]
    if expected_revision is not None:
        conditions.append(ChatSessionModel.revision == expected_revision)

    res = db.execute(
        update(ChatSessionModel)
        .where(and_(*conditions))
        .values(busy_until=lease_until, request_id=req_id)
    )
    db.commit()
    if res.rowcount == 0:
        raise HTTPException(
            status_code=409,
            detail="Conversation is currently processing another request",
        )
    db.refresh(sess)

    try:
        yield (sess, req_id)
    except Exception:
        db.rollback()
        raise
    finally:
        try:
            db.execute(
                update(ChatSessionModel)
                .where(
                    ChatSessionModel.id == session_id,
                    ChatSessionModel.request_id == req_id,
                )
                .values(busy_until=None, request_id=None)
            )
            db.commit()
        except Exception:
            db.rollback()


def _lock_active_owner(db: Session, user_id: str) -> None:
    # A real write also acquires SQLite's writer lock; PostgreSQL locks this
    # account row. Account deletion uses the same account-before-conversation order.
    active = db.execute(
        update(User).where(User.id == user_id, User.role.in_(("admin", "employee")))
        .values(role=User.role)
    )
    if active.rowcount != 1:
        raise HTTPException(status_code=401, detail="Account is not active")


def _assert_lease_holder(db: Session, session_id: str, req_id: str) -> None:
    user_id = db.scalar(select(ChatSessionModel.user_id).where(ChatSessionModel.id == session_id))
    if user_id is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    _lock_active_owner(db, user_id)
    held = db.execute(
        update(ChatSessionModel).where(
            ChatSessionModel.id == session_id,
            ChatSessionModel.request_id == req_id,
            ChatSessionModel.busy_until > utcnow(),
        ).values(request_id=req_id)
    )
    if held.rowcount != 1:
        raise HTTPException(status_code=409, detail="Conversation lease expired or claimed by another request")


def _reauthorize_all_selected(
    db: Session,
    session: ChatSessionModel,
    current_user: User,
    expected_versions: Dict[str, int],
) -> None:
    db.rollback()
    _active_user(db, current_user)
    selected_ids = session.selected_document_ids or []
    if not selected_ids:
        raise HTTPException(
            status_code=409,
            detail="Select at least one source document",
        )
    for doc_id in selected_ids:
        doc = db.get(Document, doc_id, populate_existing=True)
        if (
            doc is None
            or not can_read(current_user, doc)
            or doc.status != "searchable"
            or doc.version != expected_versions.get(doc_id)
        ):
            raise HTTPException(
                status_code=409,
                detail="A selected source is unavailable; restore access or start a new conversation",
            )


class RAGEngine:
    def __init__(self) -> None:
        self.embedder = Embedder()
        self.es_client = ESClient()
        self.router = QueryRouter()
        self.citation_parser = CitationParser()
        if settings.RAG_GENERATOR_ADAPTER == "deterministic":
            self.generator = DeterministicEvaluationGenerator()
        else:
            self.generator = GeminiGenerator()

    def close(self) -> None:
        try:
            self.embedder.close()
        except Exception as exc:
            logger.warning("Error closing embedder: %s", type(exc).__name__)
        try:
            self.es_client.close()
        except Exception as exc:
            logger.warning("Error closing es_client: %s", type(exc).__name__)
        try:
            self.generator.close()
        except Exception as exc:
            logger.warning("Error closing generator: %s", type(exc).__name__)

    def _build_sanitized_history(
        self,
        db: Session,
        sess: ChatSessionModel,
        current_user: User,
        exclude_message_ids: Optional[set] = None,
    ) -> List[Dict[str, Any]]:
        exclude_ids = exclude_message_ids or set()
        ordered = sorted(sess.messages, key=lambda m: (m.created_at, m.id))
        history: List[Dict[str, Any]] = []

        for msg in ordered:
            if msg.id in exclude_ids:
                continue
            if msg.role == "user":
                history.append({"role": "user", "content": msg.content})
            elif msg.role == "assistant":
                if answer_available(db, msg, current_user):
                    history.append({
                        "role": "assistant", "content": msg.content,
                        "source_document_ids": msg.source_document_ids or [],
                    })

        return history

    def chat(
        self,
        db: Session,
        question: str,
        current_user: User,
        session_id: str,
    ) -> ChatResponse:
        with session_lock(db, session_id, current_user.id) as (sess, req_id):
            route = self.router.classify(question)
            if route in ("greeting", "smalltalk"):
                try:
                    answer = self.generator.generate_greeting()
                except DependencyUnavailable as exc:
                    raise HTTPException(
                        status_code=503, detail="AI generation service is unavailable"
                    ) from exc

                _assert_lease_holder(db, sess.id, req_id)
                user_msg = ChatMessageModel(
                    id=str(uuid.uuid4()),
                    session_id=sess.id,
                    role="user",
                    content=question,
                    created_at=utcnow(),
                )
                asst_msg = ChatMessageModel(
                    id=str(uuid.uuid4()),
                    session_id=sess.id,
                    role="assistant",
                    content=answer,
                    citations=[],
                    source_document_ids=[],
                    unavailable=False,
                    chunks_used=0,
                    created_at=utcnow(),
                )
                db.add(user_msg)
                db.add(asst_msg)
                sess.updated_at = utcnow()
                sess.revision += 1
                db.commit()
                return ChatResponse(
                    answer=answer,
                    citations=[],
                    chunks_used=0,
                    message_id=asst_msg.id,
                    user_message_id=user_msg.id,
                )

            # Document question
            selected_docs = require_selection(db, sess, current_user)
            expected_versions = {doc.id: doc.version for doc in selected_docs}

            # Name an untitled chat after its first document question.
            if _is_untitled(sess.title):
                _assert_lease_holder(db, sess.id, req_id)
                sess.title = _title_from_question(question)
                sess.revision += 1
                sess.updated_at = utcnow()
                db.commit()

            try:
                query_vector = self.embedder.embed_query(question)
                chunks = self.es_client.hybrid_search(
                    query=question,
                    query_vector=query_vector,
                    document_versions=expected_versions,
                    top_k=5,
                )
            except DependencyUnavailable as exc:
                raise HTTPException(
                    status_code=503, detail="Search service is unavailable"
                ) from exc

            if not chunks:
                answer = (
                    "I could not find sufficient information in the selected "
                    "documents to answer your question."
                )
                citations: List[Citation] = []
                chunks_used = 0
                source_doc_ids: List[str] = []
            else:
                raw_history = self._build_sanitized_history(
                    db, sess, current_user
                )
                bounded_chunks, budgeted_history = bound_context_and_history(
                    question=question,
                    chunks=chunks,
                    history=raw_history,
                    max_tokens=settings.GENERATION_CONTEXT_TOKENS,
                )
                if not bounded_chunks:
                    answer = (
                        "I could not find sufficient information in the selected "
                        "documents to answer your question."
                    )
                    citations = []
                    chunks_used = 0
                    source_doc_ids = []
                else:
                    # Union current chunk documents with retained assistant history provenance
                    current_doc_ids = set(c["document_id"] for c in bounded_chunks)
                    all_provenance = current_doc_ids.union(
                        identifier for turn in budgeted_history
                        for identifier in turn.get("source_document_ids", [])
                    )
                    source_doc_ids = sorted(list(all_provenance))

                    # Recheck ALL selected documents immediately before calling model
                    _reauthorize_all_selected(
                        db, sess, current_user, expected_versions
                    )

                    try:
                        raw_answer = self.generator.generate(
                            question=question,
                            context_chunks=bounded_chunks,
                            conversation_history=budgeted_history,
                        )
                    except DependencyUnavailable as exc:
                        raise HTTPException(
                            status_code=503,
                            detail="AI generation service is unavailable",
                        ) from exc

                    parsed_citations, is_valid = self.citation_parser.parse_citations(
                        raw_answer, bounded_chunks
                    )
                    if not is_valid or not parsed_citations:
                        # Missing or invalid citations -> explicit abstention
                        answer = (
                            "I could not find sufficient information in the selected "
                            "documents to answer your question."
                        )
                        citations = []
                        chunks_used = 0
                        source_doc_ids = []
                    else:
                        answer = raw_answer
                        citations = parsed_citations
                        chunks_used = len(bounded_chunks)

                        # Recheck ALL selected documents immediately before release
                        _reauthorize_all_selected(
                            db, sess, current_user, expected_versions
                        )

            _assert_lease_holder(db, sess.id, req_id)
            user_msg = ChatMessageModel(
                id=str(uuid.uuid4()),
                session_id=sess.id,
                role="user",
                content=question,
                created_at=utcnow(),
            )
            asst_msg = ChatMessageModel(
                id=str(uuid.uuid4()),
                session_id=sess.id,
                role="assistant",
                content=answer,
                citations=[c.model_dump() for c in citations],
                source_document_ids=source_doc_ids,
                unavailable=False,
                chunks_used=chunks_used,
                created_at=utcnow(),
            )
            db.add(user_msg)
            db.add(asst_msg)
            sess.updated_at = utcnow()
            sess.revision += 1
            db.commit()

            return ChatResponse(
                answer=answer,
                citations=citations,
                chunks_used=chunks_used,
                message_id=asst_msg.id,
                user_message_id=user_msg.id,
            )

    def regenerate(
        self,
        db: Session,
        session_id: str,
        message_id: str,
        current_user: User,
    ) -> ChatResponse:
        with session_lock(db, session_id, current_user.id) as (sess, req_id):
            ordered_msgs = sorted(sess.messages, key=lambda m: (m.created_at, m.id))
            asst_msgs = [m for m in ordered_msgs if m.role == "assistant"]
            if not asst_msgs:
                raise HTTPException(
                    status_code=404, detail="Assistant message not found"
                )

            latest_asst = asst_msgs[-1]
            if latest_asst.id != message_id:
                raise HTTPException(
                    status_code=409,
                    detail="Only the latest assistant turn can be regenerated",
                )

            target_idx = ordered_msgs.index(latest_asst)
            user_msg = None
            user_idx = -1
            for i in range(target_idx - 1, -1, -1):
                if ordered_msgs[i].role == "user":
                    user_msg = ordered_msgs[i]
                    user_idx = i
                    break

            if user_msg is None:
                raise HTTPException(
                    status_code=400,
                    detail="No preceding user message to regenerate",
                )

            # Exclude user_msg, target_msg, and all trailing turns from history
            exclude_ids = {m.id for m in ordered_msgs[user_idx:]}
            raw_history = self._build_sanitized_history(
                db, sess, current_user, exclude_message_ids=exclude_ids
            )

            route = self.router.classify(user_msg.content)
            if route in ("greeting", "smalltalk"):
                try:
                    answer = self.generator.generate_greeting()
                except DependencyUnavailable as exc:
                    raise HTTPException(
                        status_code=503, detail="AI generation service is unavailable"
                    ) from exc
                citations = []
                chunks_used = 0
                source_doc_ids = []
            else:
                selected_docs = require_selection(db, sess, current_user)
                expected_versions = {doc.id: doc.version for doc in selected_docs}

                try:
                    query_vector = self.embedder.embed_query(user_msg.content)
                    chunks = self.es_client.hybrid_search(
                        query=user_msg.content,
                        query_vector=query_vector,
                        document_versions=expected_versions,
                        top_k=5,
                    )
                except DependencyUnavailable as exc:
                    raise HTTPException(
                        status_code=503, detail="Search service is unavailable"
                    ) from exc

                if not chunks:
                    answer = (
                        "I could not find sufficient information in the selected "
                        "documents to answer your question."
                    )
                    citations = []
                    chunks_used = 0
                    source_doc_ids = []
                else:
                    bounded_chunks, budgeted_history = bound_context_and_history(
                        question=user_msg.content,
                        chunks=chunks,
                        history=raw_history,
                        max_tokens=settings.GENERATION_CONTEXT_TOKENS,
                    )
                    if not bounded_chunks:
                        answer = (
                            "I could not find sufficient information in the selected "
                            "documents to answer your question."
                        )
                        citations = []
                        chunks_used = 0
                        source_doc_ids = []
                    else:
                        current_doc_ids = set(c["document_id"] for c in bounded_chunks)
                        all_provenance = current_doc_ids.union(
                            identifier for turn in budgeted_history
                            for identifier in turn.get("source_document_ids", [])
                        )
                        source_doc_ids = sorted(list(all_provenance))

                        # Recheck ALL selected documents immediately before calling model
                        _reauthorize_all_selected(
                            db, sess, current_user, expected_versions
                        )

                        try:
                            raw_answer = self.generator.generate(
                                question=user_msg.content,
                                context_chunks=bounded_chunks,
                                conversation_history=budgeted_history,
                            )
                        except DependencyUnavailable as exc:
                            raise HTTPException(
                                status_code=503,
                                detail="AI generation service is unavailable",
                            ) from exc

                        parsed_citations, is_valid = self.citation_parser.parse_citations(
                            raw_answer, bounded_chunks
                        )
                        if not is_valid or not parsed_citations:
                            answer = (
                                "I could not find sufficient information in the selected "
                                "documents to answer your question."
                            )
                            citations = []
                            chunks_used = 0
                            source_doc_ids = []
                        else:
                            answer = raw_answer
                            citations = parsed_citations
                            chunks_used = len(bounded_chunks)

                            # Recheck ALL selected documents immediately before release
                            _reauthorize_all_selected(
                                db, sess, current_user, expected_versions
                            )

            _assert_lease_holder(db, sess.id, req_id)
            latest_asst.content = answer
            latest_asst.citations = [c.model_dump() for c in citations]
            latest_asst.source_document_ids = source_doc_ids
            latest_asst.chunks_used = chunks_used
            latest_asst.unavailable = False

            sess.updated_at = utcnow()
            sess.revision += 1
            db.commit()

            return ChatResponse(
                answer=answer,
                citations=citations,
                chunks_used=chunks_used,
                message_id=latest_asst.id,
                user_message_id=user_msg.id,
            )

    def get_session(
        self,
        db: Session,
        session_id: str,
        current_user: User,
    ) -> ChatSessionResponse:
        sess = (
            db.query(ChatSessionModel)
            .filter(
                ChatSessionModel.id == session_id,
                ChatSessionModel.user_id == current_user.id,
            )
            .first()
        )
        if sess is None:
            raise HTTPException(status_code=404, detail="Chat session not found")
        return _serialize_session(db, sess, current_user)

    def list_sessions(
        self,
        db: Session,
        current_user: User,
        limit: int,
        offset: int,
    ) -> Page[ChatSessionSummary]:
        owned = ChatSessionModel.user_id == current_user.id
        total = db.scalar(select(func.count()).select_from(ChatSessionModel).where(owned)) or 0
        sessions = db.scalars(
            select(ChatSessionModel)
            .where(owned)
            .order_by(ChatSessionModel.updated_at.desc(), ChatSessionModel.id)
            .limit(limit)
            .offset(offset)
        ).all()
        counts = dict(
            db.execute(
                select(ChatMessageModel.session_id, func.count())
                .where(ChatMessageModel.session_id.in_([s.id for s in sessions]))
                .group_by(ChatMessageModel.session_id)
            ).all()
        ) if sessions else {}
        items = [
            ChatSessionSummary(
                id=s.id,
                title=s.title,
                created_at=_to_epoch_ms(s.created_at),
                updated_at=_to_epoch_ms(s.updated_at),
                selected_document_ids=s.selected_document_ids,
                message_count=counts.get(s.id, 0),
            )
            for s in sessions
        ]
        return Page[ChatSessionSummary](items=items, total=total, limit=limit, offset=offset)

    def create_session(
        self,
        db: Session,
        title: str,
        selected_document_ids: List[str],
        current_user: User,
    ) -> ChatSessionResponse:
        for doc_id in selected_document_ids:
            doc = require_document(db, doc_id, current_user, searchable=True)
            if (
                doc.embedding_model != settings.EMBEDDING_MODEL
                or doc.embedding_dims != settings.EMBEDDING_DIMS
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Selected source requires reindexing for the configured embedding model",
                )

        _lock_active_owner(db, current_user.id)
        now = utcnow()
        sess_id = str(uuid.uuid4())
        sess = ChatSessionModel(
            id=sess_id,
            user_id=current_user.id,
            title=title or "New Chat",
            selected_document_ids=list(selected_document_ids),
            revision=0,
            created_at=now,
            updated_at=now,
        )
        db.add(sess)
        db.commit()
        db.refresh(sess)
        return _serialize_session(db, sess, current_user)

    def clear_chat(
        self,
        db: Session,
        session_id: str,
        current_user: User,
    ) -> ClearChatResponse:
        with session_lock(db, session_id, current_user.id) as (sess, req_id):
            _assert_lease_holder(db, sess.id, req_id)
            db.query(ChatMessageModel).filter(
                ChatMessageModel.session_id == session_id
            ).delete()
            sess.updated_at = utcnow()
            sess.revision += 1
            db.commit()
            return ClearChatResponse(ok=True)

    def delete_chat(
        self,
        db: Session,
        session_id: str,
        current_user: User,
    ) -> ClearChatResponse:
        with session_lock(db, session_id, current_user.id) as (sess, req_id):
            _assert_lease_holder(db, sess.id, req_id)
            db.delete(sess)
            db.commit()
            return ClearChatResponse(ok=True)
