from __future__ import annotations

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.ingestion.ingest_pipeline import IngestPipeline
from rag.storage.es_client import ESClient


def run_layout_test() -> bool:
    print("=" * 60)
    print("  RAG — Layout Ingestion Pipeline Test")
    print("=" * 60)
    print()

    pdf_path = os.path.join(
        os.path.dirname(__file__),
        "../sample_pdfs/Document-Grounded Conversational AI using RAG.pdf"
    )
    pdf_path = os.path.abspath(pdf_path)

    if not os.path.exists(pdf_path):
        print(f"❌ ERROR: Test file not found: {pdf_path}")
        return False

    print(f"Ingesting file: {pdf_path}")

    # Clean ES index first for deterministic check
    try:
        es_client = ESClient()
        if es_client.es.indices.exists(index=es_client.index_name):
            es_client.es.indices.delete(index=es_client.index_name)
            print("  (Deleted existing index for clean test)")
    except Exception as e:
        print(f"⚠️ Warning: Could not reset ES index: {e}")

    pipeline = IngestPipeline()
    try:
        result = pipeline.run(
            pdf_path=pdf_path,
            owner_id="test_owner",
            session_id="test_session",
            is_persistent=True,
            allowed_users=["test_user"]
        )
        print()
        print("Pipeline execution summary:")
        for k, v in result.items():
            print(f"  {k}: {v}")
        print()

        # Assertions
        assert result["pages_parsed"] > 0, "No pages parsed"
        assert result["chunks_created"] > 0, "No chunks created"
        assert result["chunks_indexed"] > 0, "No chunks indexed"
        assert result["pages_failed"] == 0, f"Some pages failed: {result['pages_failed']}"

        print("Checking indexed chunks in Elasticsearch...")
        es_client.es.indices.refresh(index=es_client.index_name)
        res = es_client.es.search(
            index=es_client.index_name,
            body={"query": {"match_all": {}}},
            size=100
        )
        hits = res["hits"]["hits"]
        print(f"  Total chunks found in ES: {len(hits)}")
        
        chunk_types = set()
        for hit in hits:
            source = hit["_source"]
            metadata = source.get("metadata", {})
            chunk_type = metadata.get("chunk_type")
            if chunk_type:
                chunk_types.add(chunk_type)
            
            assert "page" in metadata, "Missing 'page' in metadata"
            assert "chunk_id" in metadata, "Missing 'chunk_id' in metadata"
            assert "chunk_type" in metadata, "Missing 'chunk_type' in metadata"
            assert metadata["owner_id"] == "test_owner", "owner_id mismatch"
            assert metadata["session_id"] == "test_session", "session_id mismatch"
            assert metadata["is_persistent"] is True, "is_persistent mismatch"
            assert "test_user" in metadata["allowed_users"], "allowed_users mismatch"

        print(f"  Chunk types found in index: {chunk_types}")
        print("\n✅ PASS: Layout ingestion pipeline verified successfully.")
        return True

    except Exception as e:
        print(f"\n❌ FAIL: layout_test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_layout_test()
    sys.exit(0 if success else 1)
