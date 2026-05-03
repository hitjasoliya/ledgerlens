"""
ingestion/parser.py — Layer 3: PDF parsing with pdfplumber + unstructured fallback.

Uses pdfplumber for standard text extraction. When a page contains tables
(detected via page.extract_tables()), that page is re-parsed using
unstructured.io for better table-aware extraction.
"""
from __future__ import annotations

import os
from typing import Dict, List

import pdfplumber


class PDFParser:
    """Parses PDF files into a list of page-level text blocks."""

    def parse(self, pdf_path: str) -> List[Dict]:
        """
        Parse a PDF file and return text content per page.

        Args:
            pdf_path: Absolute or relative path to the PDF file.

        Returns:
            List of dicts, each with:
                - "page": int (1-indexed page number)
                - "text": str (extracted text content)
        """
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(f"[Parser] PDF not found: {pdf_path}")

        pages: List[Dict] = []
        table_pages: List[int] = []  # 0-indexed pages needing unstructured

        # ── First pass: pdfplumber for all pages ────────────────────
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1  # 1-indexed for output

                # Detect tables on this page
                tables = page.extract_tables()
                has_tables = tables is not None and len(tables) > 0

                if has_tables:
                    # Flag for re-parsing with unstructured
                    table_pages.append(page_idx)
                    print(f"[Parser] Page {page_num}: table detected → "
                          f"will use unstructured")
                else:
                    text = page.extract_text() or ""
                    pages.append({"page": page_num, "text": text.strip()})

        # ── Second pass: unstructured for table pages ───────────────
        if table_pages:
            pages = self._parse_table_pages(pdf_path, pages, table_pages)

        # Sort by page number (unstructured pages may be out of order)
        pages.sort(key=lambda p: p["page"])

        # Filter out empty pages
        pages = [p for p in pages if p["text"]]

        print(f"[Parser] Extracted {len(pages)} non-empty page(s) from "
              f"'{os.path.basename(pdf_path)}'")
        return pages

    def _parse_table_pages(
        self,
        pdf_path: str,
        existing_pages: List[Dict],
        table_page_indices: List[int],
    ) -> List[Dict]:
        """
        Re-parse specific pages using unstructured.io for better table handling.

        Args:
            pdf_path: Path to the PDF file.
            existing_pages: Already-parsed pages from pdfplumber.
            table_page_indices: 0-indexed page numbers to re-parse.

        Returns:
            Updated pages list with unstructured results for table pages.
        """
        try:
            from unstructured.partition.pdf import partition_pdf
        except Exception:
            print("[Parser] WARNING: 'unstructured' unavailable. "
                  "Falling back to pdfplumber for table pages.")
            return self._fallback_pdfplumber(pdf_path, existing_pages,
                                             table_page_indices)

        try:
            elements = partition_pdf(
                filename=pdf_path,
                strategy="hi_res",
                infer_table_structure=True,
            )

            # Group element text by page number
            page_texts: Dict[int, List[str]] = {}
            for elem in elements:
                meta = elem.metadata
                # unstructured page numbers are 1-indexed
                elem_page = getattr(meta, "page_number", None)
                if elem_page is None:
                    continue
                # Only keep pages we flagged as table pages (convert to 0-indexed)
                if (elem_page - 1) in table_page_indices:
                    page_texts.setdefault(elem_page, []).append(str(elem))

            for page_num, texts in page_texts.items():
                combined = "\n".join(texts).strip()
                if combined:
                    existing_pages.append({"page": page_num, "text": combined})
                    print(f"[Parser] Page {page_num}: parsed with unstructured "
                          f"({len(combined)} chars)")

        except Exception as exc:
            print(f"[Parser] WARNING: unstructured parsing failed: {exc}")
            print("[Parser] Falling back to pdfplumber for table pages.")
            existing_pages = self._fallback_pdfplumber(
                pdf_path, existing_pages, table_page_indices
            )

        return existing_pages

    def _fallback_pdfplumber(
        self,
        pdf_path: str,
        existing_pages: List[Dict],
        table_page_indices: List[int],
    ) -> List[Dict]:
        """Fallback: extract table pages with pdfplumber if unstructured fails."""
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx in table_page_indices:
                page = pdf.pages[page_idx]
                page_num = page_idx + 1

                # Extract text + table text combined
                text_parts: List[str] = []
                main_text = page.extract_text() or ""
                if main_text.strip():
                    text_parts.append(main_text.strip())

                # Also extract tables as formatted text
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        for row in table:
                            cleaned = [cell or "" for cell in row]
                            text_parts.append(" | ".join(cleaned))

                combined = "\n".join(text_parts).strip()
                if combined:
                    existing_pages.append({"page": page_num, "text": combined})

        return existing_pages


# ── Quick self-test ─────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m ingestion.parser <path/to/file.pdf>")
        sys.exit(1)
    parser = PDFParser()
    result = parser.parse(sys.argv[1])
    for p in result[:3]:  # show first 3 pages
        preview = p["text"][:200].replace("\n", " ")
        print(f"  Page {p['page']}: {preview}...")
