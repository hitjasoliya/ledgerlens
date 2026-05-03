from __future__ import annotations

from typing import Any, Dict, List

from elasticsearch import Elasticsearch, helpers

from rag.utils.config import ES_HOST, ES_INDEX, EMBEDDING_DIMS

_RRF_K: int = 60
_CANDIDATE_MULT: int = 10


class ESClient:
    def __init__(self) -> None:
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
                            "chunk_type": {"type": "keyword"},
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

    @staticmethod
    def _rrf_merge(
        ranked_ids: List[List[str]],
        id_to_row: Dict[str, Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        scores: Dict[str, float] = {}
        for ranked in ranked_ids:
            for rank, doc_id in enumerate(ranked, start=1):
                scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (_RRF_K + rank)
        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        out: List[Dict[str, Any]] = []
        for doc_id, score in ordered:
            row = id_to_row.get(doc_id)
            if row:
                row = dict(row)
                row["score"] = score
                out.append(row)
        return out

    def hybrid_search(
        self,
        query_embedding: List[float],
        query_text: str,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        window = max(top_k * _CANDIDATE_MULT, 50)
        knn_body: Dict[str, Any] = {
            "size": window,
            "knn": {
                "field": "embedding",
                "query_vector": query_embedding,
                "k": window,
                "num_candidates": min(10000, window * 10),
            },
            "_source": ["text", "metadata"],
        }
        match_body: Dict[str, Any] = {
            "size": window,
            "query": {"match": {"text": {"query": query_text}}},
            "_source": ["text", "metadata"],
        }
        try:
            r_knn = self.es.search(index=self.index_name, body=knn_body)
            r_txt = self.es.search(index=self.index_name, body=match_body)
        except Exception as exc:
            raise RuntimeError(f"[ES] Hybrid search failed: {exc}") from exc

        id_to_row: Dict[str, Dict[str, Any]] = {}
        knn_order: List[str] = []
        txt_order: List[str] = []

        for hit in r_knn["hits"]["hits"]:
            cid = hit["_id"]
            src = hit["_source"]
            knn_order.append(cid)
            if cid not in id_to_row:
                meta = src["metadata"]
                id_to_row[cid] = {
                    "text": src["text"],
                    "page": meta["page"],
                    "chunk_id": meta["chunk_id"],
                    "source": meta.get("source", ""),
                    "chunk_type": meta.get("chunk_type", "body"),
                    "score": 0.0,
                }

        for hit in r_txt["hits"]["hits"]:
            cid = hit["_id"]
            src = hit["_source"]
            txt_order.append(cid)
            if cid not in id_to_row:
                meta = src["metadata"]
                id_to_row[cid] = {
                    "text": src["text"],
                    "page": meta["page"],
                    "chunk_id": meta["chunk_id"],
                    "source": meta.get("source", ""),
                    "chunk_type": meta.get("chunk_type", "body"),
                    "score": 0.0,
                }

        if not knn_order and not txt_order:
            return []
        if not knn_order:
            return self._rrf_merge([txt_order], id_to_row, top_k)
        if not txt_order:
            return self._rrf_merge([knn_order], id_to_row, top_k)
        return self._rrf_merge([knn_order, txt_order], id_to_row, top_k)


if __name__ == "__main__":
    client = ESClient()
    client.create_index_if_not_exists()
    print("\n✅ Index ready — Layer 5 is operational.")
