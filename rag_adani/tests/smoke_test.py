"""
tests/smoke_test.py — Integration smoke test for the RAG system.

Tests the Elasticsearch storage layer (Layer 5) by:
  1. Connecting to Elasticsearch
  2. Creating the index
  3. Inserting 2 dummy chunks with fake 768-dim embeddings (Gemini)
  4. Running hybrid_search and verifying results are returned
  5. Cleaning up the test data

Run with:  python -m tests.smoke_test
"""
from __future__ import annotations

import sys
import time

from utils.config import ES_INDEX, EMBEDDING_DIMS


def generate_fake_embedding(seed: float = 0.1) -> list:
    """Generate a deterministic fake embedding vector for testing."""
    import math
    return [math.sin(seed * (i + 1)) * 0.1 for i in range(EMBEDDING_DIMS)]


def run_smoke_test() -> bool:
    """
    Run the full smoke test suite.

    Returns True if all tests pass, False otherwise.
    """
    passed = 0
    failed = 0
    total = 4

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✅ PASS: {name}")
        else:
            failed += 1
            print(f"  ❌ FAIL: {name}" + (f" — {detail}" if detail else ""))

    print("=" * 60)
    print("  RAG Adani — Smoke Test")
    print("=" * 60)
    print()

    # ── Test 1: Connect to Elasticsearch ────────────────────────────
    print("Test 1: Connecting to Elasticsearch...")
    try:
        from storage.es_client import ESClient
        es_client = ESClient()
        check("ES connection", True)
    except Exception as exc:
        check("ES connection", False, str(exc))
        print("\n⚠️  Cannot continue without Elasticsearch. "
              "Run: docker-compose up -d")
        return False

    # ── Test 2: Create index ────────────────────────────────────────
    print("\nTest 2: Creating index...")
    try:
        # Delete if exists (clean slate for test)
        test_index = ES_INDEX
        if es_client.es.indices.exists(index=test_index):
            es_client.es.indices.delete(index=test_index)
            print(f"  (Deleted existing index '{test_index}' for clean test)")

        es_client.create_index_if_not_exists()
        exists = es_client.es.indices.exists(index=test_index)
        check("Index creation", exists, f"Index '{test_index}' not found")
    except Exception as exc:
        check("Index creation", False, str(exc))
        return False

    # ── Test 3: Upsert dummy chunks ─────────────────────────────────
    print("\nTest 3: Upserting 2 dummy chunks...")
    dummy_chunks = [
        {
            "text": "Total revenue for fiscal year 2024 was $45.2 billion, "
                    "representing a 12% increase compared to the prior year.",
            "embedding": generate_fake_embedding(seed=0.1),
            "metadata": {
                "page": 3,
                "chunk_id": "p3_c0",
                "source": "smoke_test.pdf",
                "chunk_type": "body",
            },
        },
        {
            "text": "Operating expenses rose to $28.1 billion, driven primarily "
                    "by increased investment in research and development.",
            "embedding": generate_fake_embedding(seed=0.2),
            "metadata": {
                "page": 7,
                "chunk_id": "p7_c0",
                "source": "smoke_test.pdf",
                "chunk_type": "body",
            },
        },
    ]

    try:
        count = es_client.upsert_chunks(dummy_chunks)
        check("Upsert chunks", count == 2, f"Expected 2, got {count}")
    except Exception as exc:
        check("Upsert chunks", False, str(exc))
        return False

    # Give ES a moment to index
    time.sleep(1)

    # ── Test 4: Hybrid search ───────────────────────────────────────
    print("\nTest 4: Running hybrid search...")
    try:
        query_embedding = generate_fake_embedding(seed=0.15)
        results = es_client.hybrid_search(
            query_embedding=query_embedding,
            query_text="revenue fiscal year",
            top_k=5,
        )

        has_results = len(results) >= 1
        check(
            "Hybrid search",
            has_results,
            f"Expected ≥1 result, got {len(results)}",
        )

        if has_results:
            print(f"\n  Search returned {len(results)} result(s):")
            for r in results:
                print(f"    • Page {r['page']} ({r['chunk_id']}): "
                      f"score={r['score']:.4f}")
                print(f"      \"{r['text'][:80]}...\"")
    except Exception as exc:
        check("Hybrid search", False, str(exc))

    # ── Summary ─────────────────────────────────────────────────────
    print()
    print("=" * 60)
    if failed == 0:
        print(f"  ✅ ALL {passed}/{total} TESTS PASSED")
    else:
        print(f"  ❌ {failed}/{total} TESTS FAILED ({passed} passed)")
    print("=" * 60)
    print()

    return failed == 0


if __name__ == "__main__":
    success = run_smoke_test()
    sys.exit(0 if success else 1)
