"""
ingestion/chunker.py — Layer 3: Token-based text chunking with metadata.

Uses tiktoken (cl100k_base encoding) to split page texts into chunks
of CHUNK_SIZE tokens with CHUNK_OVERLAP token overlap. Each chunk gets
metadata: page number, chunk_id (p{page}_c{i}), and source filename.
"""
from __future__ import annotations

import os
from typing import Dict, List

import tiktoken

from utils.config import CHUNK_SIZE, CHUNK_OVERLAP


class Chunker:
    """Splits parsed page texts into token-based chunks with metadata."""

    def __init__(self) -> None:
        """Initialise the tiktoken encoder (cl100k_base — used by OpenAI models)."""
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.chunk_size = CHUNK_SIZE
        self.chunk_overlap = CHUNK_OVERLAP

    def chunk(
        self, pages: List[Dict], source_filename: str = ""
    ) -> List[Dict]:
        """
        Split a list of parsed pages into overlapping token-based chunks.

        Args:
            pages: List of dicts from PDFParser, each with "page" and "text".
            source_filename: Original PDF filename for metadata.

        Returns:
            List of chunk dicts, each with:
                - "text": str (chunk text)
                - "metadata": {
                    "page": int,
                    "chunk_id": "p{page}_c{i}",
                    "source": str
                  }
        """
        all_chunks: List[Dict] = []
        source = source_filename or "unknown"

        for page_data in pages:
            page_num = page_data["page"]
            text = page_data["text"]

            if not text.strip():
                continue

            page_chunks = self._split_text(text, page_num, source)
            all_chunks.extend(page_chunks)

        print(f"[Chunker] Created {len(all_chunks)} chunk(s) from "
              f"{len(pages)} page(s) "
              f"(size={self.chunk_size}, overlap={self.chunk_overlap})")
        return all_chunks

    def _split_text(
        self, text: str, page_num: int, source: str
    ) -> List[Dict]:
        """
        Split a single page's text into overlapping chunks using a sliding window.

        Uses token-level splitting for precise control over chunk sizes.
        """
        tokens = self.encoder.encode(text)
        chunks: List[Dict] = []
        chunk_index = 0
        start = 0

        while start < len(tokens):
            end = start + self.chunk_size
            chunk_tokens = tokens[start:end]

            # Decode tokens back to text
            chunk_text = self.encoder.decode(chunk_tokens).strip()

            if chunk_text:  # skip empty chunks
                chunk_id = f"p{page_num}_c{chunk_index}"
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "page": page_num,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "body",
                    },
                })
                chunk_index += 1

            # Slide forward by (chunk_size - overlap)
            step = self.chunk_size - self.chunk_overlap
            if step <= 0:
                step = 1  # safety: prevent infinite loop
            start += step

        return chunks

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text string (utility method)."""
        return len(self.encoder.encode(text))


# ── Quick self-test ─────────────────────────────────────────────────
if __name__ == "__main__":
    chunker = Chunker()

    # Test with a synthetic page
    sample_pages = [
        {"page": 1, "text": "Revenue grew 15% year-over-year. " * 100},
        {"page": 2, "text": "Operating costs declined by 3%. " * 50},
    ]
    result = chunker.chunk(sample_pages, source_filename="test_report.pdf")

    print(f"\n✅ Chunker working — {len(result)} chunks created")
    for c in result[:3]:
        tokens = chunker.count_tokens(c["text"])
        print(f"  {c['metadata']['chunk_id']}: {tokens} tokens, "
              f"page {c['metadata']['page']}")
