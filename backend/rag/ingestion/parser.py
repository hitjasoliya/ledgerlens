from __future__ import annotations

import os
from typing import Dict, List

import pdfplumber


class PDFParser:
    @staticmethod
    def _pdfplumber_page_content(page: pdfplumber.page.Page, merge_tables: bool) -> str:
        text_parts: List[str] = []
        main_text = page.extract_text() or ""
        if main_text.strip():
            text_parts.append(main_text.strip())
        if merge_tables:
            tables = page.extract_tables()
            if tables:
                for table in tables:
                    for row in table:
                        cleaned = [cell or "" for cell in row]
                        text_parts.append(" | ".join(cleaned))
        return "\n".join(text_parts).strip()

    def parse(self, pdf_path: str) -> List[Dict]:
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"[Parser] PDF not found: {pdf_path}")

        pages_by_num: Dict[int, str] = {}

        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                tables = page.extract_tables()
                has_tables = tables is not None and len(tables) > 0
                if has_tables:
                    print(f"[Parser] Page {page_num}: table detected → merging table text")
                raw = self._pdfplumber_page_content(page, merge_tables=has_tables)
                pages_by_num[page_num] = raw

        pages: List[Dict] = [
            {"page": n, "text": t} for n, t in sorted(pages_by_num.items())
        ]

        pages.sort(key=lambda p: p["page"])
        pages = [p for p in pages if p["text"]]

        print(
            f"[Parser] Extracted {len(pages)} non-empty page(s) from "
            f"'{os.path.basename(pdf_path)}'"
        )
        return pages


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m rag.ingestion.parser <path/to/file.pdf>")
        sys.exit(1)
    parser = PDFParser()
    result = parser.parse(sys.argv[1])
    for p in result[:3]:
        preview = p["text"][:200].replace("\n", " ")
        print(f"  Page {p['page']}: {preview}...")
