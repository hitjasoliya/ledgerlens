from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from common.search import Embedder, ESClient
from common.models import ChatSessionModel, ChatMessageModel
try:
    from components import QueryRouter, CitationParser, GeminiGenerator, StubGenerator
except ImportError:
    from services.rag.components import QueryRouter, CitationParser, GeminiGenerator, StubGenerator

logger = logging.getLogger(__name__)


class RAGEngine:
    def __init__(self) -> None:
        self.embedder = Embedder()
        self.es_client = ESClient()
        self.router = QueryRouter()
        self.citation_parser = CitationParser()

        try:
            self.generator = GeminiGenerator()
            logger.info("Using GeminiGenerator for LLM responses")
        except Exception as exc:
            logger.warning(f"Using StubGenerator fallback: {exc}")
            self.generator = StubGenerator()

    def _get_or_create_session(
        self, db: Session, session_id: str, user_id: str
    ) -> ChatSessionModel:
        sess = db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()
        if not sess:
            sess = ChatSessionModel(id=session_id, user_id=user_id, title="New Chat")
            db.add(sess)
            db.commit()
            db.refresh(sess)
        return sess

    def chat(
        self,
        db: Session,
        question: str,
        user_id: str = "guest",
        user_role: str = "employee",
        session_id: str = "default_session",
    ) -> Dict[str, Any]:
        session_model = self._get_or_create_session(db, session_id, user_id)

        # Retrieve recent message history from DB
        recent_messages = (
            db.query(ChatMessageModel)
            .filter(ChatMessageModel.session_id == session_id)
            .order_by(ChatMessageModel.created_at.desc())
            .limit(6)
            .all()
        )
        recent_messages.reverse()
        history = [
            {"role": msg.role, "content": msg.content} for msg in recent_messages
        ]

        # Record User Message
        user_msg = ChatMessageModel(
            session_id=session_id,
            role="user",
            content=question,
        )
        db.add(user_msg)
        db.commit()

        # Route greetings and small talk away from the RAG pipeline
        route = self.router.classify(question)
        if route in ("greeting", "smalltalk"):
            answer = self.generator.generate_greeting(history)
            assistant_msg = ChatMessageModel(
                session_id=session_id,
                role="assistant",
                content=answer,
                citations=[],
                chunks_used=0,
            )
            db.add(assistant_msg)
            db.commit()
            return {"answer": answer, "citations": [], "chunks_used": 0}

        # Embed query and perform hybrid search
        if not self.es_client.is_available():
            answer = (
                "I'm sorry, but the document search index is currently unavailable, "
                "so I can't look up your documents right now. Please start "
                "Elasticsearch (e.g. `docker compose up -d elasticsearch`) and try again."
            )
            assistant_msg = ChatMessageModel(
                session_id=session_id,
                role="assistant",
                content=answer,
                citations=[],
                chunks_used=0,
            )
            db.add(assistant_msg)
            db.commit()
            return {"answer": answer, "citations": [], "chunks_used": 0}

        query_vector = self.embedder.embed_query(question)
        chunks = self.es_client.hybrid_search(
            query=question,
            query_vector=query_vector,
            user_id=user_id,
            role=user_role,
            session_id=session_id,
            top_k=5,
        )

        answer = self.generator.generate(
            question=question,
            context_chunks=chunks,
            conversation_history=history,
        )

        citations = self.citation_parser.parse_citations(answer, chunks)

        assistant_msg = ChatMessageModel(
            session_id=session_id,
            role="assistant",
            content=answer,
            citations=citations,
            chunks_used=len(chunks),
        )
        db.add(assistant_msg)
        db.commit()

        return {
            "answer": answer,
            "citations": citations,
            "chunks_used": len(chunks),
        }
