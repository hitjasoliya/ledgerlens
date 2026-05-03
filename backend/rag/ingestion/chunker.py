from __future__ import annotations

from typing import Dict, List

import tiktoken

from rag.utils.config import CHUNK_SIZE, CHUNK_OVERLAP


class Chunker:
    def __init__(self) -> None:
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.chunk_size = CHUNK_SIZE
        self.chunk_overlap = CHUNK_OVERLAP

    def chunk(
        self, pages: List[Dict], source_filename: str = ""
    ) -> List[Dict]:
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
        tokens = self.encoder.encode(text)
        chunks: List[Dict] = []
        chunk_index = 0
        start = 0

        while start < len(tokens):
            end = start + self.chunk_size
            chunk_tokens = tokens[start:end]

            chunk_text = self.encoder.decode(chunk_tokens).strip()

            if chunk_text:
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

            step = self.chunk_size - self.chunk_overlap
            if step <= 0:
                step = 1
            start += step

        return chunks

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))


if __name__ == "__main__":
    chunker = Chunker()

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
