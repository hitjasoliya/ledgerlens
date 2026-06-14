from __future__ import annotations

import logging
from typing import Dict, List
import tiktoken
from rag.utils.config import CHUNK_SIZE, CHUNK_OVERLAP

logger = logging.getLogger(__name__)


class Chunker:
    def __init__(self) -> None:
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.chunk_size = CHUNK_SIZE
        self.chunk_overlap = CHUNK_OVERLAP

    def chunk(self, regions: List[Dict], source_filename: str = "") -> List[Dict]:
        all_chunks: List[Dict] = []
        source = source_filename or "unknown"
        
        # Keep track of indices per page to generate clean chunk_ids
        counters = {}  # {page_num: {"t": 0, "f": 0, "c": 0}}
        
        for region in regions:
            text = region["text"]
            metadata = region["metadata"]
            page_num = metadata["page"]
            chunk_type = metadata["chunk_type"]
            image_path = metadata.get("image_path")
            
            if page_num not in counters:
                counters[page_num] = {"t": 0, "f": 0, "c": 0}
                
            if not text.strip():
                continue
                
            if chunk_type == "table":
                idx = counters[page_num]["t"]
                counters[page_num]["t"] += 1
                chunk_id = f"p{page_num}_t{idx}"
                all_chunks.append({
                    "text": text,
                    "metadata": {
                        "page": page_num,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "table",
                        "image_path": None,
                    }
                })
            elif chunk_type == "figure":
                idx = counters[page_num]["f"]
                counters[page_num]["f"] += 1
                chunk_id = f"p{page_num}_f{idx}"
                all_chunks.append({
                    "text": text,
                    "metadata": {
                        "page": page_num,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "figure",
                        "image_path": image_path,
                    }
                })
            elif chunk_type == "title":
                # Titles don't get split; keep them atomic
                idx = counters[page_num]["c"]
                counters[page_num]["c"] += 1
                chunk_id = f"p{page_num}_c{idx}"
                all_chunks.append({
                    "text": text,
                    "metadata": {
                        "page": page_num,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "title",
                        "image_path": None,
                    }
                })
            else:  # "body" or "list"
                # Split using token-bounded windowing
                tokens = self.encoder.encode(text)
                start = 0
                while start < len(tokens):
                    end = start + self.chunk_size
                    chunk_tokens = tokens[start:end]
                    chunk_text = self.encoder.decode(chunk_tokens).strip()
                    
                    if chunk_text:
                        idx = counters[page_num]["c"]
                        counters[page_num]["c"] += 1
                        chunk_id = f"p{page_num}_c{idx}"
                        
                        all_chunks.append({
                            "text": chunk_text,
                            "metadata": {
                                "page": page_num,
                                "chunk_id": chunk_id,
                                "source": source,
                                "chunk_type": chunk_type,
                                "image_path": None,
                            }
                        })
                    
                    step = self.chunk_size - self.chunk_overlap
                    if step <= 0:
                        step = 1
                    start += step

        logger.info("Created %d chunk(s) from %d region(s)", len(all_chunks), len(regions))
        return all_chunks

    def count_tokens(self, text: str) -> int:
        return len(self.encoder.encode(text))


if __name__ == "__main__":
    chunker = Chunker()
    sample_regions = [
        {
            "text": "Header of Title",
            "metadata": {"page": 1, "chunk_type": "title"}
        },
        {
            "text": "Body paragraph content text. " * 50,
            "metadata": {"page": 1, "chunk_type": "body"}
        },
        {
            "text": "| col1 | col2 |\n|---|---|\n| val1 | val2 |",
            "metadata": {"page": 1, "chunk_type": "table"}
        }
    ]
    result = chunker.chunk(sample_regions, source_filename="test_report.pdf")
    print(f"\n✅ Chunker working — {len(result)} chunks created")
    for c in result:
        print(f"  {c['metadata']['chunk_id']} ({c['metadata']['chunk_type']}): "
              f"{chunker.count_tokens(c['text'])} tokens")
