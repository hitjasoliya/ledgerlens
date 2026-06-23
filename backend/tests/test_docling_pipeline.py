import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.ingestion.docling_pipeline import DoclingPipeline


class StubEmbedder:
    BATCH_SIZE = 32

    def embed_batch(self, texts):
        return [[0.1] * 768 for _ in texts]


class StubESClient:
    def create_index_if_not_exists(self):
        pass

    def upsert_chunks(self, chunks):
        return len(chunks)


class StubDoclingPipeline(DoclingPipeline):
    def __init__(self, embedder, es_client):
        super().__init__(embedder=embedder, es_client=es_client)

    def _convert_pdf(self, pdf_path):
        return [
            {"page": 1, "type": "section_header", "text": "Q1 2026 Earnings"},
            {"page": 1, "type": "text", "text": "Net income was $1.2 billion, up 10% YoY."},
            {"page": 2, "type": "table", "text": "| Metric | Value |\n|---|---|\n| Revenue | $4.5B |"},
            {"page": 3, "type": "list_item", "text": "Operating margin expanded to 28%."},
            {"page": 3, "type": "picture", "text": "Figure: Margin trend diagram."},
        ]


class TestDoclingPipeline(unittest.TestCase):
    def test_pipeline_ingestion_flow(self):
        embedder = StubEmbedder()
        es_client = StubESClient()
        pipeline = StubDoclingPipeline(embedder, es_client)

        progress_calls = []

        def progress_cb(stage, completed, total):
            progress_calls.append((stage, completed, total))

        summary = pipeline.run(
            pdf_path="dummy_report.pdf",
            owner_id="test_admin",
            session_id="test_session",
            is_persistent=True,
            allowed_users=["user1", "user2"],
            progress_callback=progress_cb,
        )

        self.assertEqual(summary["source"], "dummy_report.pdf")
        self.assertEqual(summary["pages_parsed"], 3)
        self.assertEqual(summary["chunks_created"], 4)
        self.assertEqual(summary["chunks_indexed"], 4)

        # Verify progress callback tracking
        self.assertTrue(len(progress_calls) > 0)
        self.assertEqual(progress_calls[-1], ("indexing", 4, 4))


if __name__ == "__main__":
    unittest.main()
