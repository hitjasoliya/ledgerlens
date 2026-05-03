from __future__ import annotations

from typing import List

import google.generativeai as genai

from rag.utils.config import GEMINI_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIMS


class Embedder:

    BATCH_SIZE: int = 100

    def __init__(self) -> None:
        if not GEMINI_API_KEY:
            raise ValueError(
                "[Embedder] GEMINI_API_KEY is not set. "
                "Please add it to your .env file."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = EMBEDDING_MODEL
        self.dims = EMBEDDING_DIMS

    def embed_text(self, text: str) -> List[float]:
        try:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="retrieval_document",
                output_dimensionality=self.dims,
            )
            return result["embedding"]
        except Exception as exc:
            raise RuntimeError(
                f"[Embedder] Failed to embed text: {exc}"
            ) from exc

    def embed_query(self, text: str) -> List[float]:
        try:
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type="retrieval_query",
                output_dimensionality=self.dims,
            )
            return result["embedding"]
        except Exception as exc:
            raise RuntimeError(
                f"[Embedder] Failed to embed query: {exc}"
            ) from exc

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        all_embeddings: List[List[float]] = []

        for start in range(0, len(texts), self.BATCH_SIZE):
            batch = texts[start : start + self.BATCH_SIZE]
            try:
                result = genai.embed_content(
                    model=self.model,
                    content=batch,
                    task_type="retrieval_document",
                    output_dimensionality=self.dims,
                )
                all_embeddings.extend(result["embedding"])
            except Exception as exc:
                raise RuntimeError(
                    f"[Embedder] Failed to embed batch "
                    f"(items {start}–{start + len(batch) - 1}): {exc}"
                ) from exc

        return all_embeddings


if __name__ == "__main__":
    embedder = Embedder()
    vec = embedder.embed_text("Hello, world!")
    print(f"✅ Embedder working — vector dimension: {len(vec)}")
    print(f"   First 5 values: {vec[:5]}")
