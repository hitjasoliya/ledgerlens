from __future__ import annotations

import time
from typing import List

import google.generativeai as genai

from rag.utils.config import GEMINI_API_KEY, EMBEDDING_MODEL, EMBEDDING_DIMS


class Embedder:

    # Reduced batch size to 10 to avoid Free Tier rate limits (429 errors)
    BATCH_SIZE: int = 10

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
            
            # Retry logic for 429 Quota Exceeded
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = genai.embed_content(
                        model=self.model,
                        content=batch,
                        task_type="retrieval_document",
                        output_dimensionality=self.dims,
                    )
                    all_embeddings.extend(result["embedding"])
                    # Small delay to not overwhelm the API
                    time.sleep(1.5)
                    break # Success, move to next batch
                except Exception as exc:
                    error_msg = str(exc)
                    if "429" in error_msg or "Quota" in error_msg or "exhausted" in error_msg.lower():
                        if attempt < max_retries - 1:
                            print(f"\n[Embedder] Rate limit hit. Waiting 60 seconds for quota to reset (Attempt {attempt+1}/{max_retries})...")
                            time.sleep(60)
                            continue
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
