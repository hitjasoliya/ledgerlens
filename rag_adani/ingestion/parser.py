"""
ingestion/parser.py — Layer 3: PDF parsing with pdfplumber + unstructured fallback.

Uses pdfplumber for all pages so nothing is dropped when unstructured omits pages.
Pages that contain tables get richer pdfplumber extraction (text + normalized table
rows); unstructured may replace those pages when it returns usable content.
"""
from __future__ import annotations

import os
from typing import Dict, List

import pdfplumber

from utils.config import UNSTRUCTURED_PDF_STRATEGY


class PDFParser:
    """Parses PDF files into a list of page-level text blocks."""

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

        table_pages: List[int] = []
        pages_by_num: Dict[int, str] = {}

        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                tables = page.extract_tables()
                has_tables = tables is not None and len(tables) > 0
                if has_tables:
                    table_pages.append(page_idx)
                    print(
                        f"[Parser] Page {page_num}: table detected → "
                        "will try unstructured overlay"
                    )
                raw = self._pdfplumber_page_content(page, merge_tables=has_tables)
                pages_by_num[page_num] = raw

        pages: List[Dict] = [
            {"page": n, "text": t} for n, t in sorted(pages_by_num.items())
        ]

        if table_pages:
            pages = self._merge_unstructured_table_pages(pdf_path, pages, table_pages)

        pages.sort(key=lambda p: p["page"])
        pages = [p for p in pages if p["text"]]

        print(
            f"[Parser] Extracted {len(pages)} non-empty page(s) from "
            f"'{os.path.basename(pdf_path)}'"
        )
        return pages

    def _merge_unstructured_table_pages(
        self,
        pdf_path: str,
        pages: List[Dict],
        table_page_indices: List[int],
    ) -> List[Dict]:
        by_page: Dict[int, str] = {p["page"]: p["text"] for p in pages}

        try:
            from unstructured.partition.pdf import partition_pdf
        except Exception:
            print(
                "[Parser] WARNING: 'unstructured' unavailable. "
                "Using pdfplumber-only text for table pages."
            )
            return [{"page": n, "text": t} for n, t in sorted(by_page.items())]

        try:
            elements = partition_pdf(
                filename=pdf_path,
                strategy=UNSTRUCTURED_PDF_STRATEGY,
                infer_table_structure=True,
                languages=["eng"],
                detect_language_per_element=False,
            )

            page_texts: Dict[int, List[str]] = {}
            for elem in elements:
                meta = elem.metadata
                elem_page = getattr(meta, "page_number", None)
                if elem_page is None:
                    continue
                if (elem_page - 1) not in table_page_indices:
                    continue
                page_texts.setdefault(elem_page, []).append(str(elem))

            for page_num, texts in page_texts.items():
                combined = "\n".join(texts).strip()
                if combined:
                    by_page[page_num] = combined
                    print(
                        f"[Parser] Page {page_num}: unstructured overlay applied "
                        f"({len(combined)} chars)"
                    )

        except Exception as exc:
            print(f"[Parser] WARNING: unstructured parsing failed: {exc}")
            print("[Parser] Keeping pdfplumber extraction for table pages.")

        return [{"page": n, "text": t} for n, t in sorted(by_page.items())]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m ingestion.parser <path/to/file.pdf>")
        sys.exit(1)
    parser = PDFParser()
    result = parser.parse(sys.argv[1])
    for p in result[:3]:
        preview = p["text"][:200].replace("\n", " ")
        print(f"  Page {p['page']}: {preview}...")
