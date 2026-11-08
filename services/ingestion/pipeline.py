from __future__ import annotations

import hashlib
from importlib.util import find_spec
import logging
import multiprocessing as mp
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

root_dir = Path(__file__).resolve().parent.parent.parent
common_path = str(root_dir / "packages" / "common" / "src")
if common_path not in sys.path:
    sys.path.insert(0, common_path)
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import tiktoken

from common.config import settings
from common.search import Embedder, ESClient


class DocumentRejected(ValueError):
    """The document's content can't be indexed safely; the message is shown to users."""


logger = logging.getLogger(__name__)

# Model imports and initialization belong only to the bounded parser process.
_docling_available = find_spec("docling") is not None


def _docling_parse_worker(pdf_path: str, conn: Any) -> None:
    """Isolated child worker process for Docling PDF parsing."""
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.pipeline_options import PdfPipelineOptions, AcceleratorOptions, AcceleratorDevice
        from docling.datamodel.base_models import InputFormat

        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.accelerator_options = AcceleratorOptions(
            device=AcceleratorDevice(settings.DOCLING_DEVICE)
        )

        converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
            }
        )
        result = converter.convert(pdf_path)
        doc = result.document

        if not hasattr(doc, "pages") or not doc.pages:
            conn.send({"error": "Docling document missing pages structure; cannot determine true page count"})
            return

        total_pages = len(doc.pages)
        if total_pages == 0:
            conn.send({"error": "Docling document contains zero pages"})
            return

        items = []
        known_pages = set(doc.pages)
        for item, _level in doc.iterate_items():
            label = getattr(item, "label", "text")
            if not item.prov:
                if label == "table" or (getattr(item, "text", "") or "").strip():
                    raise ValueError("Extracted evidence has no page provenance")
                continue
            pages = {int(provenance.page_no) for provenance in item.prov}
            if not pages.issubset(known_pages) or min(pages) < 1:
                raise ValueError("Extracted evidence references an invalid page")
            if len(pages) != 1:
                if label in ("table", "picture", "figure"):
                    raise ValueError("Merged multi-page element has no unambiguous page-local evidence")
                text = getattr(item, "text", "") or ""
                offset = 0
                kind = "section_header" if label in ("section_header", "heading") else "list_item" if label == "list_item" else "paragraph"
                for provenance in sorted(item.prov, key=lambda value: value.charspan):
                    start, end = provenance.charspan
                    if start < offset or end > len(text) or text[offset:start].strip():
                        raise ValueError("Multi-page text has incomplete or overlapping provenance")
                    fragment = text[start:end].strip()
                    if fragment:
                        items.append({"page_number": int(provenance.page_no), "item_type": kind, "text": fragment})
                    offset = end
                if text[offset:].strip():
                    raise ValueError("Multi-page text has unattributed content")
                continue
            page = next(iter(pages))

            if label == "table":
                text = item.export_to_markdown(doc=doc) or ""
                if text.strip():
                    items.append({"page_number": page, "item_type": "table", "text": text.strip()})
            elif label in ("picture", "figure"):
                caption = ""
                if hasattr(item, "caption_text") and callable(item.caption_text):
                    caption = item.caption_text(doc)
                elif hasattr(item, "text"):
                    caption = getattr(item, "text", "")
                if caption and str(caption).strip():
                    items.append({"page_number": page, "item_type": "figure", "text": str(caption).strip()})
            elif label in ("section_header", "section-header", "heading"):
                t = (getattr(item, "text", "") or "").strip()
                if t:
                    items.append({"page_number": page, "item_type": "section_header", "text": t})
            elif label in ("list_item", "list-item"):
                t = (getattr(item, "text", "") or "").strip()
                if t:
                    items.append({"page_number": page, "item_type": "list_item", "text": t})
            else:
                t = (getattr(item, "text", "") or "").strip()
                if t:
                    items.append({"page_number": page, "item_type": "paragraph", "text": t})

        conn.send({"items": items, "total_pages": total_pages})
    except Exception as exc:
        conn.send({"error": str(exc)})
    finally:
        try:
            conn.close()
        except Exception:
            pass


class DoclingChunker:
    """Chunks DoclingDocument items into deterministic, versioned, indexable chunks.

    Strategies:
    - Tables: atomic if within token budget; oversized financial tables split into row groups
      retaining column headers, unit, period, and section context. Indivisible oversized rows or
      unstructured non-standard tables reject explicitly.
    - Pictures / Figures: only real caption text is emitted; no fabricated placeholders.
    - Section headers: prepended as context to subsequent text/tables without mutating input.
    - List items: merge contiguous list items on the same page up to chunk token limit.
    - Body text: real token-bounded sliding window via tiktoken.
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> None:
        self.chunk_size = chunk_size or settings.CHUNK_TOKENS
        self.chunk_overlap = chunk_overlap or settings.CHUNK_OVERLAP
        try:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._tokenizer = tiktoken.encoding_for_model("gpt-4")

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._tokenizer.encode(text))

    def chunk_items(
        self,
        items: List[Dict[str, Any]],
        filename: str,
        document_id: str,
        version: int = 1,
    ) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        id_counts: Dict[str, int] = {}

        def build_chunk(page_number: int, item_type: str, text: str) -> Dict[str, Any]:
            cleaned_text = text.strip()
            content_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()[:12]
            base_id = f"{document_id}_v{version}_p{page_number}_{item_type[:3]}_{content_hash}"
            count = id_counts.get(base_id, 0)
            id_counts[base_id] = count + 1
            chunk_id = base_id if count == 0 else f"{base_id}_{count}"
            return {
                "chunk_id": chunk_id,
                "document_id": document_id,
                "version": version,
                "filename": filename,
                "page_number": page_number,
                "item_type": item_type,
                "text": cleaned_text,
            }

        active_section_context: Optional[str] = None
        i = 0
        while i < len(items):
            item = items[i]
            page_number = item.get("page_number")
            if page_number is None or page_number < 1:
                i += 1
                continue

            item_type = item.get("item_type", "paragraph")
            raw_text = (item.get("text") or "").strip()

            if not raw_text:
                i += 1
                continue

            if item_type == "section_header":
                header_parts = [raw_text]
                j = i + 1
                while j < len(items) and items[j].get("item_type") == "section_header":
                    part = (items[j].get("text") or "").strip()
                    if part:
                        header_parts.append(part)
                    j += 1
                active_section_context = " | ".join(header_parts)
                # Standalone section header chunk if at the end of the document
                if j >= len(items):
                    chunks.append(build_chunk(page_number, "section_header", active_section_context))
                i = j
                continue

            if item_type == "table":
                table_chunks = self._chunk_table(
                    text=raw_text,
                    page_number=page_number,
                    section_context=active_section_context,
                    build_fn=build_chunk,
                )
                chunks.extend(table_chunks)
                i += 1

            elif item_type in ("picture", "figure"):
                if raw_text:
                    prefix = f"[{active_section_context}] " if active_section_context else ""
                    chunks.append(build_chunk(page_number, "figure", f"{prefix}{raw_text}"))
                i += 1

            elif item_type == "list_item":
                list_items = [raw_text]
                j = i + 1
                while (
                    j < len(items)
                    and items[j].get("item_type") == "list_item"
                    and items[j].get("page_number") == page_number
                ):
                    candidate_text = (items[j].get("text") or "").strip()
                    if candidate_text:
                        combined = "; ".join(list_items + [candidate_text])
                        if self.count_tokens(combined) > self.chunk_size:
                            break
                        list_items.append(candidate_text)
                    j += 1

                merged_list = "; ".join(list_items)
                prefix = f"[{active_section_context}] " if active_section_context else ""
                chunks.append(build_chunk(page_number, "list", f"{prefix}{merged_list}"))
                i = j

            else:
                prefix = f"[{active_section_context}] " if active_section_context else ""
                text_with_context = f"{prefix}{raw_text}" if prefix else raw_text
                split_chunks = self._split_text(
                    text=text_with_context,
                    page_number=page_number,
                    build_fn=build_chunk,
                )
                chunks.extend(split_chunks)
                i += 1

        return chunks

    def _chunk_table(
        self,
        text: str,
        page_number: int,
        section_context: Optional[str],
        build_fn: Any,
    ) -> List[Dict[str, Any]]:
        prefix = f"[{section_context}]\n" if section_context else ""
        full_text = f"{prefix}{text}"

        if self.count_tokens(full_text) <= self.chunk_size:
            return [build_fn(page_number, "table", full_text)]

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if len(lines) >= 3 and lines[0].startswith("|") and ("---" in lines[1] or "|-" in lines[1]):
            # Docling can place unit legends below Markdown's separator.
            # Repeat those leading qualifier rows with every data group.
            context_end = 2
            unit_context_pattern = (
                r"\b(?:[A-Z]{3}|(?i:thousands?|millions?|billions?|percent(?:age)?s?"
                r"|basis\s+points?|per[\s-]+share))\b|[$€£¥₹]"
            )
            while context_end < len(lines):
                row = lines[context_end]
                if re.search(r"\d", row) or not re.search(unit_context_pattern, row):
                    break
                context_end += 1
            header_block = prefix + "\n".join(lines[:context_end])
            if self.count_tokens(header_block) >= self.chunk_size:
                raise DocumentRejected("A table header is too large to index without losing its column labels")

            table_chunks = []
            current_text = header_block
            has_rows = False
            for row in lines[context_end:]:
                candidate = f"{current_text}\n{row}"
                candidate_tokens = self.count_tokens(candidate)
                if candidate_tokens > self.chunk_size:
                    if has_rows:
                        table_chunks.append(build_fn(page_number, "table", current_text))
                        candidate = f"{header_block}\n{row}"
                        candidate_tokens = self.count_tokens(candidate)
                    if candidate_tokens > self.chunk_size:
                        raise DocumentRejected("A table row is too large to index without splitting it")
                current_text = candidate
                has_rows = True

            if has_rows:
                table_chunks.append(build_fn(page_number, "table", current_text))
            return table_chunks

        # Reject unstructured oversized tables instead of flattening into misleading text fragments
        raise DocumentRejected(
            "A large table has no recognizable header row, so it can't be indexed safely"
        )

    def _split_text(
        self,
        text: str,
        page_number: int,
        build_fn: Any,
        item_type: str = "paragraph",
    ) -> List[Dict[str, Any]]:
        token_ids = self._tokenizer.encode(text)
        if not token_ids:
            return []

        if len(token_ids) <= self.chunk_size:
            return [build_fn(page_number, item_type, text)]

        chunks: List[Dict[str, Any]] = []
        step = max(1, self.chunk_size - self.chunk_overlap)
        start = 0

        while start < len(token_ids):
            end = min(start + self.chunk_size, len(token_ids))
            window_text = self._tokenizer.decode(token_ids[start:end])
            chunks.append(build_fn(page_number, item_type, window_text))
            if end >= len(token_ids):
                break
            start += step

        return chunks


class IngestionPipeline:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        es_client: Optional[ESClient] = None,
        parser_worker_fn: Any = None,
    ) -> None:
        self.embedder = embedder or Embedder()
        self.es_client = es_client or ESClient()
        self.chunker = DoclingChunker()
        self._parser_worker_fn = parser_worker_fn or _docling_parse_worker

    def is_converter_available(self) -> bool:
        if not _docling_available:
            return False
        if sys.platform != "linux":
            return True
        matcher = shutil.which("fc-match")
        if matcher is None:
            return False
        try:
            result = subprocess.run(
                [matcher, "-f", "%{file}", "Helvetica"],
                capture_output=True, text=True, check=True,
                timeout=settings.READINESS_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        font = result.stdout.strip()
        return bool(font) and Path(font).is_file()

    def parse_pdf(self, pdf_path: str) -> Tuple[List[Dict[str, Any]], int]:
        if self._parser_worker_fn == _docling_parse_worker and not self.is_converter_available():
            raise RuntimeError("Docling or its native rendering fonts are unavailable")

        timeout_seconds = settings.PARSER_TIMEOUT_SECONDS
        start_time = time.monotonic()

        # API-worker threads may hold native-library locks; never inherit them.
        ctx = mp.get_context("spawn")
        parent_conn, child_conn = ctx.Pipe(duplex=False)

        proc = ctx.Process(
            target=self._parser_worker_fn,
            args=(pdf_path, child_conn),
        )
        proc.start()
        child_conn.close()

        has_data = parent_conn.poll(timeout_seconds)
        if not has_data:
            proc.terminate()
            proc.join(timeout=2.0)
            if proc.is_alive():
                proc.kill()
                proc.join(timeout=1.0)
            parent_conn.close()
            elapsed = time.monotonic() - start_time
            raise TimeoutError(
                f"Docling PDF parsing process exceeded configured limit of {timeout_seconds}s (elapsed: {elapsed:.2f}s)"
            )

        try:
            payload = parent_conn.recv()
        except EOFError:
            proc.join(timeout=1.0)
            raise ValueError("Docling parser process terminated unexpectedly without output")
        finally:
            parent_conn.close()
            proc.join(timeout=2.0)

        if not isinstance(payload, dict):
            raise ValueError("Invalid output payload received from Docling parser process")

        if "error" in payload:
            raise ValueError(f"Docling PDF conversion failed: {payload['error']}")

        items = payload.get("items", [])
        total_pages = payload.get("total_pages", 0)

        if total_pages == 0:
            raise DocumentRejected("The PDF has no readable pages")

        if not items:
            raise DocumentRejected("No text could be extracted; scanned PDFs without a text layer are not supported")

        logger.info("Docling extracted %d item(s) across %d page(s) from %s", len(items), total_pages, pdf_path)
        return items, total_pages

    def close(self) -> None:
        try:
            self.embedder.close()
        except Exception as exc:
            logger.warning("Error closing embedder: %s", type(exc).__name__)
        try:
            self.es_client.close()
        except Exception as exc:
            logger.warning("Error closing ES client: %s", type(exc).__name__)
