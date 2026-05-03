"""
orchestrator/engine.py — Layer 2: RAG query engine with conversation memory.

Provides the RAGEngine class that orchestrates the full query flow:
  1. Embed the user's question (Layer 4 — Embedder)
  2. Hybrid search for relevant chunks (Layer 5 — ESClient)
  3. Generate an answer from context (Layer 4 — Generator)
  4. Parse citations from the [Sources: ...] footer
  5. Maintain a sliding conversation history (last 6 turns)
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from intelligence.embedder import Embedder
from intelligence.generator import Generator
from storage.es_client import ESClient
from utils.config import TOP_K


class RAGEngine:
    """
    Central RAG orchestrator.

    Connects the Embedder, ESClient, and Generator into a single
    chat() interface that accepts a question and returns an answer
    with page-number citations.
    """

    MAX_HISTORY_TURNS: int = 6

    def __init__(self) -> None:
        self.embedder = Embedder()
        self.generator = Generator()
        self.es_client = ESClient()
        self.conversation_history: List[Dict[str, str]] = []

    # ── Public API ──────────────────────────────────────────────────

    def chat(self, question: str) -> Dict[str, Any]:
        self._append_to_history("user", question.strip())

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

        return {
            "answer": answer,
            "citations": citations,
            "chunks_used": len(retrieved_chunks),
        }

    # ── History management ──────────────────────────────────────────

    def _append_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history, trimming to MAX_HISTORY_TURNS."""
        self.conversation_history.append({"role": role, "content": content})

        # Keep only the last N messages
        if len(self.conversation_history) > self.MAX_HISTORY_TURNS:
            self.conversation_history = self.conversation_history[
                -self.MAX_HISTORY_TURNS :
            ]

    def clear_history(self) -> None:
        self.conversation_history.clear()

    # ── Citation parsing ────────────────────────────────────────────

    def _parse_citations(
        self,
        answer: str,
        retrieved_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        """
        Extract page citations from the [Sources: p3, p7] footer in the answer.

        Falls back to using the retrieved chunks' metadata if the pattern
        is not found in the answer.

        Returns:
            List of {"page": int, "chunk_id": str} dicts.
        """
        citations: List[Dict[str, str]] = []

        # Try to parse [Sources: p3, p7, p12] from the answer
        match = re.search(r"\[Sources?:\s*(.*?)\]", answer, re.IGNORECASE)
        if match:
            sources_str = match.group(1)
            # Extract page numbers: "p3, p7" → [3, 7]
            page_numbers = re.findall(r"p(\d+)", sources_str, re.IGNORECASE)
            cited_pages = {int(p) for p in page_numbers}

            # Match cited pages to retrieved chunks for chunk_ids
            for chunk in retrieved_chunks:
                p = int(chunk["page"])
                if p in cited_pages:
                    citations.append({
                        "page": p,
                        "chunk_id": chunk["chunk_id"],
                    })
                    cited_pages.discard(p)

            # Add any cited pages without matching chunks
            for page in cited_pages:
                citations.append({"page": page, "chunk_id": "unknown"})
        else:
            # Fallback: cite all retrieved chunks
            for chunk in retrieved_chunks:
                citations.append({
                    "page": int(chunk["page"]),
                    "chunk_id": chunk["chunk_id"],
                })

        # Sort by page number
        citations.sort(key=lambda c: c["page"])
        return citations

    # ── Error helper ────────────────────────────────────────────────

    def _error_response(self, message: str) -> Dict[str, Any]:
        error_answer = f"⚠️  Error: {message}"
        self._append_to_history("assistant", error_answer)
        return {
            "answer": error_answer,
            "citations": [],
            "chunks_used": 0,
        }


# ── Quick self-test ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("Initialising RAG Engine...")
    engine = RAGEngine()
    print("✅ RAGEngine initialised successfully.")
    print(f"   Conversation history length: {len(engine.conversation_history)}")
    print(f"   TOP_K: {TOP_K}")
    print("\nReady for chat(). Use main.py --chat for interactive mode.")
