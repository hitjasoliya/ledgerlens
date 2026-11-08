from __future__ import annotations

import math
from functools import wraps
from typing import Any

import requests
from elasticsearch import ApiError, Elasticsearch, NotFoundError
from elasticsearch.helpers import bulk
from elastic_transport import TransportError

from common.config import settings

_RRF_K = 60


class DependencyUnavailable(RuntimeError):
    """An external provider failed; this is not an empty evidence result."""


def _search_operation(method):
    @wraps(method)
    def perform(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (ApiError, TransportError) as exc:
            raise DependencyUnavailable("Search service unavailable") from exc
    return perform


class Embedder:
    def __init__(self) -> None:
        self.dims = settings.EMBEDDING_DIMS
        self.model = settings.EMBEDDING_MODEL
        self.ollama_host = settings.OLLAMA_HOST.rstrip("/")
        self._session = requests.Session()

    def _validate(self, vector: Any) -> list[float]:
        if (
            not isinstance(vector, list)
            or len(vector) != self.dims
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in vector
            )
            or not any(vector)
        ):
            raise DependencyUnavailable("Embedding provider returned an incompatible vector")
        return vector

    def embedding_dims(self) -> int:
        self.embed_query("embedding compatibility probe")
        return self.dims

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), settings.EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + settings.EMBEDDING_BATCH_SIZE]
            try:
                response = self._session.post(
                    f"{self.ollama_host}/api/embed",
                    json={"model": self.model, "input": batch, "truncate": False},
                    timeout=settings.AI_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                embeddings = response.json().get("embeddings")
            except (requests.RequestException, ValueError, AttributeError) as exc:
                raise DependencyUnavailable("Embedding provider unavailable") from exc
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise DependencyUnavailable("Embedding provider returned an incomplete batch")
            vectors.extend(self._validate(vector) for vector in embeddings)
        return vectors

    def embed_text(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)

    def is_available(self) -> bool:
        try:
            response = self._session.post(
                f"{self.ollama_host}/api/show", json={"model": self.model},
                timeout=settings.READINESS_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            info = response.json().get("model_info", {})
            dimensions = [value for key, value in info.items() if key.endswith(".embedding_length")]
            return all(value == self.dims for value in dimensions)
        except (requests.RequestException, ValueError, AttributeError):
            return False

    def close(self) -> None:
        self._session.close()


class ESClient:
    def __init__(self) -> None:
        self.index_name = settings.ES_INDEX
        self._es: Elasticsearch | None = None

    @property
    def es(self) -> Elasticsearch:
        if self._es is None:
            options: dict[str, Any] = {
                "hosts": [settings.ES_HOST],
                "request_timeout": settings.AI_TIMEOUT_SECONDS,
                "max_retries": 0,
            }
            if settings.ES_USERNAME:
                options["basic_auth"] = (settings.ES_USERNAME, settings.ES_PASSWORD)
            self._es = Elasticsearch(**options)
        return self._es

    def is_available(self) -> bool:
        try:
            client = self.es.options(request_timeout=settings.READINESS_TIMEOUT_SECONDS)
            if not client.ping():
                return False
            if not client.indices.exists(index=self.index_name):
                return True
            mapping = client.indices.get_mapping(index=self.index_name)[self.index_name]["mappings"]
            metadata = mapping.get("_meta", {})
            return (
                metadata.get("embedding_model") == settings.EMBEDDING_MODEL
                and metadata.get("embedding_dims") == settings.EMBEDDING_DIMS
                and mapping.get("properties", {}).get("vector", {}).get("dims") == settings.EMBEDDING_DIMS
            )
        except Exception:
            return False

    @_search_operation
    def create_index_if_not_exists(self, dims: int | None = None) -> None:
        dimensions = dims or settings.EMBEDDING_DIMS
        if dimensions != settings.EMBEDDING_DIMS:
            raise DependencyUnavailable("Configured index embedding dimensions are incompatible")
        expected = {"embedding_model": settings.EMBEDDING_MODEL, "embedding_dims": dimensions}
        if not self.es.indices.exists(index=self.index_name):
            try:
                self.es.indices.create(index=self.index_name, mappings={
                    "_meta": expected,
                    "dynamic": "strict",
                    "properties": {
                        "chunk_id": {"type": "keyword"},
                        "document_id": {"type": "keyword"},
                        "version": {"type": "integer"},
                        "embedding_model": {"type": "keyword"},
                        "filename": {"type": "keyword"},
                        "page_number": {"type": "integer"},
                        "item_type": {"type": "keyword"},
                        "text": {"type": "text", "analyzer": "standard"},
                        "vector": {
                            "type": "dense_vector", "dims": dimensions,
                            "index": True, "similarity": "cosine",
                        },
                    },
                })
            except Exception:
                # Another ingestion process may have created the same index.
                if not self.es.indices.exists(index=self.index_name):
                    raise
        mapping = self.es.indices.get_mapping(index=self.index_name)[self.index_name]["mappings"]
        if (
            mapping.get("_meta") != expected
            or mapping.get("properties", {}).get("vector", {}).get("dims") != dimensions
        ):
            raise DependencyUnavailable("Index embedding model/dimensions are incompatible; reindex explicitly")

    @_search_operation
    def upsert_chunks(self, chunks: list[dict[str, Any]], dims: int | None = None) -> int:
        if not chunks:
            raise ValueError("Cannot index an empty document")
        self.create_index_if_not_exists(dims)
        for chunk in chunks:
            if chunk.get("embedding_model") != settings.EMBEDDING_MODEL:
                raise ValueError("Chunk embedding model is incompatible")
            if len(chunk.get("vector", [])) != settings.EMBEDDING_DIMS:
                raise ValueError("Chunk embedding dimensions are incompatible")
        count, errors = bulk(
            self.es,
            (
                {"_op_type": "index", "_index": self.index_name,
                 "_id": chunk["chunk_id"], "_source": chunk}
                for chunk in chunks
            ),
            refresh="wait_for",
            raise_on_error=True,
        )
        if errors or count != len(chunks):
            raise DependencyUnavailable("Not all document chunks were indexed")
        return count

    @_search_operation
    def hybrid_search(
        self, query: str, query_vector: list[float],
        document_versions: dict[str, int], top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if not document_versions:
            return []
        if len(query_vector) != settings.EMBEDDING_DIMS:
            raise ValueError("Query embedding dimensions are incompatible")
        self.create_index_if_not_exists()
        selected = {
            "bool": {
                "should": [
                    {"bool": {"filter": [
                        {"term": {"document_id": identifier}}, {"term": {"version": version}},
                    ]}}
                    for identifier, version in document_versions.items()
                ],
                "minimum_should_match": 1,
                "filter": [{"term": {"embedding_model": settings.EMBEDDING_MODEL}}],
            }
        }
        # Both paths use the exact current SQL-authorized document versions.
        # Any provider failure propagates, rather than becoming empty evidence.
        knn = self.es.search(index=self.index_name, size=top_k * 5, knn={
            "field": "vector", "query_vector": query_vector,
            "k": top_k * 5, "num_candidates": top_k * 10, "filter": selected,
        })
        text = self.es.search(index=self.index_name, size=top_k * 5, query={
            "bool": {"must": [{"match": {"text": query}}], "filter": [selected]},
        })
        scores: dict[str, float] = {}
        documents: dict[str, dict[str, Any]] = {}
        for response in (knn, text):
            if response.get("timed_out") or response.get("_shards", {}).get("failed", 0):
                raise DependencyUnavailable("Search did not complete")
            for rank, hit in enumerate(response["hits"]["hits"], start=1):
                identifier = hit["_id"]
                source = hit["_source"]
                if document_versions.get(source["document_id"]) != source.get("version"):
                    raise DependencyUnavailable("Search returned evidence outside the selected version")
                documents[identifier] = source
                scores[identifier] = scores.get(identifier, 0.0) + 1.0 / (_RRF_K + rank)
        ordered = sorted(scores, key=lambda identifier: (-scores[identifier], identifier))[:top_k]
        return [documents[identifier] for identifier in ordered]

    def delete_document_chunks(self, document_id: str, version: int | None = None) -> int:
        filters = [{"term": {"document_id": document_id}}]
        if version is not None:
            filters.append({"term": {"version": version}})
        return self._delete({"bool": {"filter": filters}})

    def delete_all_chunks(self) -> int:
        return self._delete({"match_all": {}})

    @_search_operation
    def _delete(self, query: dict[str, Any]) -> int:
        try:
            result = self.es.delete_by_query(
                index=self.index_name, query=query, refresh=True, conflicts="proceed",
            )
        except NotFoundError:
            return 0
        if result.get("failures") or result.get("timed_out") or result.get("version_conflicts", 0):
            raise DependencyUnavailable("Search cleanup is incomplete")
        return result.get("deleted", 0)

    def close(self) -> None:
        if self._es is not None:
            self._es.close()
            self._es = None
