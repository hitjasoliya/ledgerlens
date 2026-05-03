"""
storage/es_client.py — Layer 5: Elasticsearch index management and hybrid search.

Handles index creation (BM25 + dense_vector), bulk upserts, and
hybrid search via RRF (Reciprocal Rank Fusion) over kNN + BM25.
"""
from __future__ import annotations

from typing import Any, Dict, List

from elasticsearch import Elasticsearch, helpers
from utils.config import ES_HOST, ES_INDEX, EMBEDDING_DIMS


class ESClient:
    """Elasticsearch client for storing and retrieving RAG chunks."""

    def __init__(self) -> None:
        """Connect to the Elasticsearch cluster using config values."""
        try:
            self.es = Elasticsearch(hosts=[ES_HOST])
            info = self.es.info()
            print(f"[ES] Connected to Elasticsearch {info['version']['number']}")
        except Exception as exc:
            raise ConnectionError(
                f"[ES] Failed to connect to Elasticsearch at {ES_HOST}: {exc}"
            ) from exc
        self.index_name: str = ES_INDEX

    def create_index_if_not_exists(self) -> None:
        """Create the RAG chunks index with keyword + dense_vector mappings."""
        if self.es.indices.exists(index=self.index_name):
            print(f"[ES] Index '{self.index_name}' already exists — skipping.")
            return
        body: Dict[str, Any] = {
            "mappings": {
                "properties": {
                    "text": {"type": "text"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": EMBEDDING_DIMS,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "metadata": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer"},
                            "chunk_id": {"type": "keyword"},
                            "source": {"type": "keyword"},
                        },
                    },
                }
            },
            "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        }
        try:
            self.es.indices.create(index=self.index_name, body=body)
            print(f"[ES] Index '{self.index_name}' created successfully.")
        except Exception as exc:
            raise RuntimeError(
                f"[ES] Failed to create index '{self.index_name}': {exc}"
            ) from exc

    def upsert_chunks(self, chunks: List[Dict[str, Any]]) -> int:
        """Bulk-index chunks. Uses chunk_id as _id for idempotent upserts.

        Returns the number of successfully indexed documents.
        """
        actions = [
            {
                "_index": self.index_name,
                "_id": chunk["metadata"]["chunk_id"],
                "_source": {
                    "text": chunk["text"],
                    "embedding": chunk["embedding"],
                    "metadata": chunk["metadata"],
                },
            }
            for chunk in chunks
        ]
        try:
            success_count, errors = helpers.bulk(
                self.es, actions, raise_on_error=False
            )
            if errors:
                print(f"[ES] Bulk upsert had {len(errors)} error(s).")
                for err in errors[:3]:
                    print(f"     → {err}")
            print(f"[ES] Upserted {success_count} chunk(s).")
            return success_count
        except Exception as exc:
            raise RuntimeError(f"[ES] Bulk upsert failed: {exc}") from exc

    def hybrid_search(
        self,
        query_embedding: List[float],
        query_text: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """Hybrid kNN + BM25 search fused with RRF. Returns top_k results."""
        body: Dict[str, Any] = {
            "size": top_k,
            "sub_searches": [
                {
                    "query": {
                        "knn": {
                            "field": "embedding",
                            "query_vector": query_embedding,
                            "num_candidates": top_k * 10,
                        }
                    }
                },
                {
                    "query": {
                        "match": {"text": {"query": query_text}}
                    }
                },
            ],
            "rank": {
                "rrf": {"rank_constant": 60, "window_size": top_k * 10}
            },
        }
        try:
            response = self.es.search(index=self.index_name, body=body)
        except Exception as exc:
            raise RuntimeError(f"[ES] Hybrid search failed: {exc}") from exc

        results: List[Dict[str, Any]] = []
        for hit in response["hits"]["hits"]:
            src = hit["_source"]
            results.append({
                "text": src["text"],
                "page": src["metadata"]["page"],
                "chunk_id": src["metadata"]["chunk_id"],
                "score": hit.get("_score", 0.0),
            })
        return results


# ── Quick self-test ─────────────────────────────────────────────────
if __name__ == "__main__":
    client = ESClient()
    client.create_index_if_not_exists()
    print("\n✅ Index ready — Layer 5 is operational.")
