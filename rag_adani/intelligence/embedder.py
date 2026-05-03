"""
intelligence/embedder.py — Layer 4: Google Gemini embedding wrapper.

Wraps the Gemini Embeddings API (text-embedding-004) with:
  - Single-text embedding via embed_text()
  - Batch embedding via embed_batch() with automatic chunking into groups of 100
"""
from __future__ import annotations

from typing import List

import google.generativeai as genai

from utils.config import GEMINI_API_KEY, EMBEDDING_MODEL


class Embedder:
    """Generates vector embeddings using Google's text-embedding-004 model."""

    BATCH_SIZE: int = 100  # process in manageable batches

    def __init__(self) -> None:
        """Initialise the Gemini client with the configured API key."""
        if not GEMINI_API_KEY:
            raise ValueError(
                "[Embedder] GEMINI_API_KEY is not set. "
                "Please add it to your .env file."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = EMBEDDING_MODEL

    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text string.

        Args:
            text: The input text to embed.

        Returns:
            A list of floats representing the 768-dimensional embedding vector.
        """
        try:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="retrieval_document",
            )
            return result["embedding"]
        except Exception as exc:
            raise RuntimeError(
                f"[Embedder] Failed to embed text: {exc}"
            ) from exc

    def embed_query(self, text: str) -> List[float]:
        """
        Embed a query string (uses retrieval_query task type for better search).

        Args:
            text: The query text to embed.

        Returns:
            A list of floats representing the 768-dimensional embedding vector.
        """
        try:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="retrieval_query",
            )
            return result["embedding"]
        except Exception as exc:
            raise RuntimeError(
                f"[Embedder] Failed to embed query: {exc}"
            ) from exc

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a list of texts in batches of 100.

        Args:
            texts: List of input texts to embed.

        Returns:
            A list of embedding vectors, one per input text, in the same order.
        """
        all_embeddings: List[List[float]] = []

        for start in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[start : start + self.BATCH_SIZE]
            try:
                result = genai.embed_content(
                    model=self.model,
                    content=batch,
                    task_type="retrieval_document",
                )
                all_embeddings.extend(result["embedding"])
            except Exception as exc:
                raise RuntimeError(
                    f"[Embedder] Failed to embed batch "
                    f"(items {start}–{start + len(batch) - 1}): {exc}"
                ) from exc

        return all_embeddings


# ── Quick self-test ─────────────────────────────────────────────────
if __name__ == "__main__":
    embedder = Embedder()
    vec = embedder.embed_text("Hello, world!")
    print(f"✅ Embedder working — vector dimension: {len(vec)}")
    print(f"   First 5 values: {vec[:5]}")
