import sys
import unittest
from pathlib import Path

# Add backend directory to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rag.orchestrator.router import QueryRouter
from rag.orchestrator.citation import CitationParser


class TestOrchestratorComponents(unittest.TestCase):
    def test_query_router_greetings(self):
        router = QueryRouter()
        
        # Positive greeting matches
        self.assertTrue(router.is_greeting("hi"))
        self.assertTrue(router.is_greeting("Hello"))
        self.assertTrue(router.is_greeting("hey there!"))
        self.assertTrue(router.is_greeting("good morning"))
        self.assertTrue(router.is_greeting("how are you doing?"))
        self.assertTrue(router.is_greeting("thanks"))
        
        # Negative matches (RAG business queries)
        self.assertFalse(router.is_greeting("What was the net income for Q1?"))
        self.assertFalse(router.is_greeting("Check table 3 for operating expenses."))
        self.assertFalse(router.is_greeting("hi, can you calculate the YoY revenue growth?"))

    def test_citation_parser(self):
        parser = CitationParser()
        chunks = [
            {"chunk_id": "c1", "page": 1, "text": "Page 1 context"},
            {"chunk_id": "c2", "page": 2, "text": "Page 2 context"},
            {"chunk_id": "c3", "page": 3, "text": "Page 3 context"},
        ]

        # Case 1: Simple bracketed source citation
        citations = parser.parse_citations(
            answer="The revenue grew by 10% [Source: p2].",
            retrieved_chunks=chunks,
        )
        self.assertEqual(len(citations), 1)
        self.assertEqual(citations[0]["page"], 2)
        self.assertEqual(citations[0]["chunk_id"], "c2")

        # Case 2: Multi-source citations
        citations_multi = parser.parse_citations(
            answer="Expenses increased YoY [Sources: p1, p3].",
            retrieved_chunks=chunks,
        )
        self.assertEqual(len(citations_multi), 2)
        self.assertEqual(citations_multi[0]["page"], 1)
        self.assertEqual(citations_multi[0]["chunk_id"], "c1")
        self.assertEqual(citations_multi[1]["page"], 3)
        self.assertEqual(citations_multi[1]["chunk_id"], "c3")

        # Case 3: No source citations (falls back to mapping all retrieved chunks)
        citations_none = parser.parse_citations(
            answer="Operating income remained flat.",
            retrieved_chunks=chunks,
        )
        self.assertEqual(len(citations_none), 3)
        self.assertEqual([c["page"] for c in citations_none], [1, 2, 3])

        # Case 4: Extraneous cited page not in retrieved chunks (resolves to unknown)
        citations_unknown = parser.parse_citations(
            answer="Operating margin was 15% [Source: p5].",
            retrieved_chunks=chunks,
        )
        self.assertEqual(len(citations_unknown), 1)
        self.assertEqual(citations_unknown[0]["page"], 5)
        self.assertEqual(citations_unknown[0]["chunk_id"], "unknown")


if __name__ == "__main__":
    unittest.main()
