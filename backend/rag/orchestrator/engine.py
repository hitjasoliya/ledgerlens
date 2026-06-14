from __future__ import annotations

import logging
import re
from typing import Any, Dict, List

from rag.intelligence.embedder import Embedder
from rag.intelligence.generator import Generator
from rag.storage.es_client import ESClient
from rag.utils.config import TOP_K

logger = logging.getLogger(__name__)


class RAGEngine:
    MAX_HISTORY_TURNS: int = 6

    def __init__(self) -> None:
        self.embedder = Embedder()
        self.generator = Generator()
        self.es_client = ESClient()
        self._histories: Dict[str, List[Dict[str, str]]] = {}

    def _get_history(self, session_id: str) -> List[Dict[str, str]]:
        if session_id not in self._histories:
            self._histories[session_id] = []
        return self._histories[session_id]

    def _trim_history(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        if len(history) > self.MAX_HISTORY_TURNS:
            return history[-self.MAX_HISTORY_TURNS:]
        return history

    def chat(self, question: str, current_user_id: str = "guest", current_session_id: str = "default_session") -> Dict[str, Any]:
        conv_history = self._get_history(current_session_id)
        conv_history.append({"role": "user", "content": question.strip()})

        if self._is_greeting_or_pleasantry(question):
            try:
                history_for_gen = conv_history[:-1]
                answer = self.generator.generate_greeting(
                    question=question,
                    conversation_history=history_for_gen if history_for_gen else None,
                )
            except Exception:
                answer = "Hello! How can I help you today? You can ask me questions about your financial documents."

            conv_history.append({"role": "assistant", "content": answer})
            self._histories[current_session_id] = self._trim_history(conv_history)
            return {
                "answer": answer,
                "citations": [],
                "chunks_used": 0,
            }

        try:
            query_embedding = self.embedder.embed_query(question)
        except Exception as exc:
            return self._error_response(
                f"Failed to embed question: {exc}", current_session_id
            )

        try:
            retrieved_chunks = self.es_client.hybrid_search(
                query_embedding=query_embedding,
                query_text=question,
                top_k=TOP_K,
                current_user_id=current_user_id,
                current_session_id=current_session_id,
            )
        except Exception as exc:
            return self._error_response(
                f"Failed to search Elasticsearch: {exc}", current_session_id
            )

        if not retrieved_chunks:
            answer = "Not found in the document."
            conv_history.append({"role": "assistant", "content": answer})
            self._histories[current_session_id] = self._trim_history(conv_history)
            return {
                "answer": answer,
                "citations": [],
                "chunks_used": 0,
            }

        try:
            history_for_gen = conv_history[:-1]
            answer = self.generator.generate(
                question=question,
                context_chunks=retrieved_chunks,
                conversation_history=history_for_gen if history_for_gen else None,
            )
        except Exception as exc:
            return self._error_response(
                f"Failed to generate answer: {exc}", current_session_id
            )

        citations = self._parse_citations(answer, retrieved_chunks)

        conv_history.append({"role": "assistant", "content": answer})
        self._histories[current_session_id] = self._trim_history(conv_history)

        chunks_used = len(retrieved_chunks)
        if "not found in the document" in answer.lower() or not citations:
            citations = []
            chunks_used = 0

        return {
            "answer": answer,
            "citations": citations,
            "chunks_used": chunks_used,
        }

    def clear_history(self, session_id: str | None = None) -> None:
        if session_id:
            self._histories.pop(session_id, None)
        else:
            self._histories.clear()

    def _parse_citations(
        self,
        answer: str,
        retrieved_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        citations: List[Dict[str, str]] = []

        match = re.search(r"\[Sources?:\s*(.*?)\]", answer, re.IGNORECASE)
        if match:
            sources_str = match.group(1)
            page_numbers = re.findall(r"p(\d+)", sources_str, re.IGNORECASE)
            cited_pages = {int(p) for p in page_numbers}

            for chunk in retrieved_chunks:
                p = int(chunk["page"])
                if p in cited_pages:
                    citations.append({
                        "page": p,
                        "chunk_id": chunk["chunk_id"],
                    })
                    cited_pages.discard(p)

            for page in cited_pages:
                citations.append({"page": page, "chunk_id": "unknown"})
        else:
            for chunk in retrieved_chunks:
                citations.append({
                    "page": int(chunk["page"]),
                    "chunk_id": chunk["chunk_id"],
                })

        citations.sort(key=lambda c: c["page"])
        return citations

    def _error_response(self, message: str, session_id: str = "default_session") -> Dict[str, Any]:
        error_answer = f"⚠️  Error: {message}"
        conv_history = self._get_history(session_id)
        conv_history.append({"role": "assistant", "content": error_answer})
        self._histories[session_id] = self._trim_history(conv_history)
        return {
            "answer": error_answer,
            "citations": [],
            "chunks_used": 0,
        }

    def _is_greeting_or_pleasantry(self, query: str) -> bool:
        q = query.strip().lower().rstrip("?.!")
        
        common_phrases = {
            "hi", "hello", "hey", "hola", "greetings", "good morning", 
            "good afternoon", "good evening", "howdy", "yo", "sup",
            "how are you", "hows it going", "how are you doing", "whats up",
            "hi there", "hello there", "hey there", "thanks", "thank you",
            "thank you so much", "perfect", "awesome", "great", "ok", "okay",
            "bye", "goodbye", "good day"
        }
        
        if q in common_phrases:
            return True
            
        greeting_patterns = [
            r"^(hi|hello|hey|greetings|good\s+morning|good\s+afternoon|good\s+evening|howdy|yo)(\s+(there|buddy|friend|team|all))?$",
            r"^how\s+are\s+you(\s+doing)?$",
            r"^hows\s+it\s+going$",
            r"^whats\s+up$",
            r"^thank\s+you(\s+so\s+much)?$",
            r"^thanks(\s+a\s+lot)?$",
        ]
        
        for pattern in greeting_patterns:
            if re.match(pattern, q):
                return True
                
        return False


if __name__ == "__main__":
    import sys
    print("Initialising RAG Engine...")
    engine = RAGEngine()
    print("RAGEngine initialised successfully.")
    print(f"   TOP_K: {TOP_K}")
    sys.stdout.flush()
    print("\nReady for chat(). Use: python -m rag --chat")
