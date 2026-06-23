from __future__ import annotations

import re
from typing import Any, Dict, List


class CitationParser:
    """Parses text answers to extract document page citations and map them to vector chunks."""

    def parse_citations(
        self,
        answer: str,
        retrieved_chunks: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []

        match = re.search(r"\[Sources?:\s*(.*?)\]", answer, re.IGNORECASE)
        if match:
            sources_str = match.group(1)
            page_numbers = re.findall(r"p(\d+)", sources_str, re.IGNORECASE)
            cited_pages = {int(p) for p in page_numbers}

            for chunk in retrieved_chunks:
                p = int(chunk["page"])
                if p in cited_pages:
                    citations.append({
                        "page": p,
                        "chunk_id": chunk["chunk_id"],
                    })
                    cited_pages.discard(p)

            for page in cited_pages:
                citations.append({"page": page, "chunk_id": "unknown"})
        else:
            for chunk in retrieved_chunks:
                citations.append({
                    "page": int(chunk["page"]),
                    "chunk_id": chunk["chunk_id"],
                })

        citations.sort(key=lambda c: int(c["page"]))
        return citations
