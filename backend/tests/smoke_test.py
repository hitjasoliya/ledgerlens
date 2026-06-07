from __future__ import annotations

import sys
import time

from rag.utils.config import ES_INDEX, EMBEDDING_DIMS


def generate_fake_embedding(seed: float = 0.1) -> list:
    import math
    return [math.sin(seed * (i + 1)) * 0.1 for i in range(EMBEDDING_DIMS)]


def run_smoke_test() -> bool:
    passed = 0
    failed = 0
    total = 6

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ✅ PASS: {name}")
        else:
            failed += 1
            print(f"  ❌ FAIL: {name}" + (f" — {detail}" if detail else ""))

    print("=" * 60)
    print("  RAG — Smoke Test")
    print("=" * 60)
    print()

    print("Test 1: Connecting to Elasticsearch...")
    try:
        from rag.storage.es_client import ESClient
        es_client = ESClient()
        check("ES connection", True)
    except Exception as exc:
        check("ES connection", False, str(exc))
        print("\n⚠️  Cannot continue without Elasticsearch. "
              "Run: docker compose up -d")
        return False

    print("\nTest 2: Creating index...")
    try:
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
                "owner_id": "guest",
                "session_id": "default_session",
                "is_persistent": True,
                "allowed_users": ["guest"]
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
                "owner_id": "guest",
                "session_id": "default_session",
                "is_persistent": True,
                "allowed_users": ["guest"]
            },
        },
    ]

    try:
        count = es_client.upsert_chunks(dummy_chunks)
        check("Upsert chunks", count == 2, f"Expected 2, got {count}")
    except Exception as exc:
        check("Upsert chunks", False, str(exc))
        return False

    time.sleep(1)

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

    print("\nTest 5: Running page renderer and layout detector...")
    try:
        import os
        from rag.ingestion.page_renderer import PageRenderer
        from rag.ingestion.layout_detector import LayoutDetector

        pdf_path = os.path.join(
            os.path.dirname(__file__),
            "../sample_pdfs/Document-Grounded Conversational AI using RAG.pdf"
        )
        pdf_path = os.path.abspath(pdf_path)

        renderer = PageRenderer()
        detector = LayoutDetector()

        pages = renderer.render(pdf_path)
        check("Page rendering", len(pages) > 0, f"Expected >0 pages, got {len(pages)}")

        if len(pages) > 0:
            regions = detector.detect(pages[0]["image"], pages[0]["page"])
            check("Layout region detection", len(regions) > 0, f"Expected >0 regions, got {len(regions)}")
    except Exception as exc:
        check("Layout rendering and detection", False, str(exc))

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
