from __future__ import annotations
import logging
import hashlib
import os
from typing import Any, Dict, List, Optional
import requests
from elasticsearch import Elasticsearch

from common.config import settings

logger = logging.getLogger(__name__)

_RRF_K: int = 60


class Embedder:
    def __init__(self) -> None:
        self.dims = settings.EMBEDDING_DIMS
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = os.getenv("EMBEDDING_MODEL", "embeddinggemma")

    def embedding_dims(self) -> int:
        """Probe the actual embedding dimensionality from Ollama; fall back to configured dims."""
        try:
            vec = self.embed_text("_probe")
            if vec:
                return len(vec)
        except Exception:
            pass
        return self.dims

    def _fallback_embedding(self, text: str) -> List[float]:
        # Hash-based deterministic fallback vector when Ollama/Gemini is unavailable
        h = hashlib.sha256(text.encode("utf-8")).digest()
        vec = []
        for i in range(self.dims):
            byte_val = h[i % len(h)]
            vec.append((byte_val / 255.0) * 2.0 - 1.0)
        return vec

    def embed_text(self, text: str) -> List[float]:
        try:
            res = requests.post(
                f"{self.ollama_host}/api/embed",
                json={"model": self.model, "input": text},
                timeout=5,
            )
            if res.status_code == 200:
                return res.json()["embeddings"][0]
        except Exception:
            pass
        return self._fallback_embedding(text)

    def embed_query(self, text: str) -> List[float]:
        return self.embed_text(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        embeddings = []
        for text in texts:
            embeddings.append(self.embed_text(text))
        return embeddings


_es_instance: Optional[Elasticsearch] = None


def get_es_client() -> Optional[Elasticsearch]:
    global _es_instance
    if _es_instance is None:
        try:
            kwargs: dict[str, Any] = {"hosts": [settings.ES_HOST]}
            if settings.ES_USERNAME and settings.ES_PASSWORD:
                kwargs["basic_auth"] = (settings.ES_USERNAME, settings.ES_PASSWORD)
            client = Elasticsearch(**kwargs)
            if client.ping():
                _es_instance = client
        except Exception as exc:
            logger.warning(f"Elasticsearch connection unavailable: {exc}")
            _es_instance = None
    return _es_instance


class ESClient:
    def __init__(self) -> None:
        self.index_name = settings.ES_INDEX
        self.es = get_es_client()

    def create_index_if_not_exists(self, dims: Optional[int] = None) -> None:
        if not self.es or not self.es.ping():
            return
        if self.es.indices.exists(index=self.index_name):
            return

        vector_dims = dims or settings.EMBEDDING_DIMS
        mapping = {
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "filename": {"type": "keyword"},
                    "page_number": {"type": "integer"},
                    "item_type": {"type": "keyword"},
                    "text": {"type": "text", "analyzer": "standard"},
                    "vector": {
                        "type": "dense_vector",
                        "dims": vector_dims,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "allowed_users": {"type": "keyword"},
                    "scope": {"type": "keyword"},
                    "is_persistent": {"type": "boolean"},
                    "session_id": {"type": "keyword"},
                }
            }
        }
        self.es.indices.create(index=self.index_name, body=mapping)

    def upsert_chunks(self, chunks: List[Dict[str, Any]], dims: Optional[int] = None) -> int:
        if not chunks:
            return 0
        if not self.es or not self.es.ping():
            logger.warning("Elasticsearch unavailable: %d chunk(s) NOT indexed", len(chunks))
            return 0
        self.create_index_if_not_exists(dims=dims)
        actions = []
        for chunk in chunks:
            actions.append(
                {
                    "_op_type": "index",
                    "_index": self.index_name,
                    "_id": chunk["chunk_id"],
                    "_source": chunk,
                }
            )
        from elasticsearch.helpers import bulk
        success_count, _ = bulk(self.es, actions)
        return success_count

    def is_available(self) -> bool:
        return bool(self.es and self.es.ping())

    def hybrid_search(
        self,
        query: str,
        query_vector: List[float],
        user_id: str = "guest",
        role: str = "employee",
        session_id: str = "default_session",
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        # RBAC Filter: User has access if admin OR (scope=='employee' or user_id in allowed_users or session_id matches)
        if role == "admin":
            filter_clause = {"match_all": {}}
        else:
            filter_clause = {
                "bool": {
                    "should": [
                        {"term": {"scope": "employee"}},
                        {"term": {"allowed_users": user_id}},
                        {"term": {"session_id": session_id}},
                    ],
                    "minimum_should_match": 1,
                }
            }

        # Vector search
        knn_query = {
            "field": "vector",
            "query_vector": query_vector,
            "k": top_k * 5,
            "num_candidates": top_k * 10,
            "filter": filter_clause,
        }

        # Text search
        text_query = {
            "bool": {
                "must": [{"match": {"text": query}}],
                "filter": [filter_clause],
            }
        }

        try:
            knn_res = self.es.search(index=self.index_name, knn=knn_query, size=top_k * 5)
            knn_hits = knn_res["hits"]["hits"]
        except Exception:
            knn_hits = []

        try:
            txt_res = self.es.search(index=self.index_name, query=text_query, size=top_k * 5)
            txt_hits = txt_res["hits"]["hits"]
        except Exception:
            txt_hits = []

        # RRF Merge
        rrf_scores: Dict[str, float] = {}
        id_to_doc: Dict[str, Dict[str, Any]] = {}

        for rank, hit in enumerate(knn_hits):
            cid = hit["_id"]
            id_to_doc[cid] = hit["_source"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (_RRF_K + rank + 1))

        for rank, hit in enumerate(txt_hits):
            cid = hit["_id"]
            id_to_doc[cid] = hit["_source"]
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + (1.0 / (_RRF_K + rank + 1))

        sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]
        return [id_to_doc[cid] for cid in sorted_ids]

    def delete_document_chunks(self, document_id: str) -> int:
        """Delete all indexed chunks for a document.

        Keyed by document_id, not filename: multiple uploads may share a
        filename, and deleting one must not remove the other's chunks.
        """
        if not self.es or not self.es.ping():
            return 0
        res = self.es.delete_by_query(
            index=self.index_name,
            body={"query": {"term": {"document_id": document_id}}},
            refresh=True,
        )
        return res.get("deleted", 0)

    def delete_all_chunks(self) -> int:
        """Delete every chunk in the index, returning how many were removed."""
        if not self.is_available():
            return 0
        if not self.es.indices.exists(index=self.index_name):
            return 0
        res = self.es.delete_by_query(
            index=self.index_name,
            body={"query": {"match_all": {}}},
            refresh=True,
        )
        return res.get("deleted", 0)
