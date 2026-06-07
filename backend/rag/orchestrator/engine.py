from __future__ import annotations

import re
from typing import Any, Dict, List

from rag.intelligence.embedder import Embedder
from rag.intelligence.generator import Generator
from rag.storage.es_client import ESClient
from rag.utils.config import TOP_K


class RAGEngine:
    MAX_HISTORY_TURNS: int = 6

    def __init__(self) -> None:
        self.embedder = Embedder()
        self.generator = Generator()
        self.es_client = ESClient()
        self.conversation_history: List[Dict[str, str]] = []

    def chat(self, question: str, current_user_id: str = "guest", current_session_id: str = "default_session") -> Dict[str, Any]:
        self._append_to_history("user", question.strip())

        if self._is_greeting_or_pleasantry(question):
            try:
                history_for_gen = self.conversation_history[:-1]
                answer = self.generator.generate_greeting(
                    question=question,
                    conversation_history=history_for_gen if history_for_gen else None,
                )
            except Exception:
                answer = "Hello! How can I help you today? You can ask me questions about your financial documents."
            
            self._append_to_history("assistant", answer)
            return {
                "answer": answer,
                "citations": [],
                "chunks_used": 0,
            }

        try:
            query_embedding = self.embedder.embed_query(question)
        except Exception as exc:
            return self._error_response(
                f"Failed to embed question: {exc}"
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
                f"Failed to search Elasticsearch: {exc}"
            )

        if not retrieved_chunks:
            answer = "Not found in the document."
            self._append_to_history("assistant", answer)
            return {
                "answer": answer,
                "citations": [],
                "chunks_used": 0,
            }

        try:
            history_for_gen = self.conversation_history[:-1]
            answer = self.generator.generate(
                question=question,
                context_chunks=retrieved_chunks,
                conversation_history=history_for_gen if history_for_gen else None,
            )
        except Exception as exc:
            return self._error_response(
                f"Failed to generate answer: {exc}"
            )

        citations = self._parse_citations(answer, retrieved_chunks)

        self._append_to_history("assistant", answer)

        chunks_used = len(retrieved_chunks)
        if "not found in the document" in answer.lower() or not citations:
            citations = []
            chunks_used = 0

        return {
            "answer": answer,
            "citations": citations,
            "chunks_used": chunks_used,
        }

    def _append_to_history(self, role: str, content: str) -> None:
        self.conversation_history.append({"role": role, "content": content})

        if len(self.conversation_history) > self.MAX_HISTORY_TURNS:
            self.conversation_history = self.conversation_history[
                -self.MAX_HISTORY_TURNS :
            ]

    def clear_history(self) -> None:
        self.conversation_history.clear()

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

    def _error_response(self, message: str) -> Dict[str, Any]:
        error_answer = f"⚠️  Error: {message}"
        self._append_to_history("assistant", error_answer)
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
    print("Initialising RAG Engine...")
    engine = RAGEngine()
    print("✅ RAGEngine initialised successfully.")
    print(f"   Conversation history length: {len(engine.conversation_history)}")
    print(f"   TOP_K: {TOP_K}")
    print("\nReady for chat(). Use: python -m rag --chat")
