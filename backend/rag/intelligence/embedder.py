from __future__ import annotations

import time
from typing import List
import requests

from rag.utils.config import (
    EMBEDDING_MODEL,
    EMBEDDING_DIMS,
    OLLAMA_HOST,
)


class Embedder:
    BATCH_SIZE: int = 32

    def __init__(self) -> None:
        self.model = EMBEDDING_MODEL
        self.dims = EMBEDDING_DIMS
        self.host = OLLAMA_HOST

        # Verify connection to Ollama
        try:
            response = requests.get(f"{self.host}/api/tags", timeout=5)
            if response.status_code != 200:
                raise RuntimeError(f"Ollama returned status code {response.status_code}")
        except Exception as exc:
            raise RuntimeError(
                f"[Embedder] Failed to connect to Ollama at {self.host}: {exc}. "
                "Is Ollama running?"
            ) from exc

    def embed_text(self, text: str) -> List[float]:
        try:
            response = requests.post(
                f"{self.host}/api/embed",
                json={"model": self.model, "input": text},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result["embeddings"][0]
        except Exception as exc:
            raise RuntimeError(
                f"[Embedder] Failed to embed text via Ollama: {exc}"
            ) from exc

    def embed_query(self, text: str) -> List[float]:
        try:
            response = requests.post(
                f"{self.host}/api/embed",
                json={"model": self.model, "input": text},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            return result["embeddings"][0]
        except Exception as exc:
            raise RuntimeError(
                f"[Embedder] Failed to embed query via Ollama: {exc}"
            ) from exc

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        all_embeddings: List[List[float]] = []
        batch_size = 32
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            try:
                response = requests.post(
                    f"{self.host}/api/embed",
                    json={"model": self.model, "input": batch},
                    timeout=120
                )
                response.raise_for_status()
                result = response.json()
                all_embeddings.extend(result["embeddings"])
            except Exception as exc:
                raise RuntimeError(
                    f"[Embedder] Failed to embed batch via Ollama "
                    f"(items {start}–{start + len(batch) - 1}): {exc}"
                    f"\nMake sure the model '{self.model}' is pulled and Ollama is running."
                ) from exc
        return all_embeddings


if __name__ == "__main__":
    embedder = Embedder()
    vec = embedder.embed_text("Hello, world!")
    print(f"✅ Embedder working (Ollama) — vector dimension: {len(vec)}")
    print(f"   First 5 values: {vec[:5]}")
