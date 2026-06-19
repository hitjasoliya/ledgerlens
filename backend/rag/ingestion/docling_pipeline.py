from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from rag.intelligence.embedder import Embedder
from rag.storage.es_client import ESClient

console = Console()
logger = logging.getLogger(__name__)


class DoclingChunker:
    """Chunks DoclingDocument items into indexable chunks.

    Strategies:
    - Tables: single atomic chunk (markdown)
    - Pictures: caption text as chunk
    - Section headers: prepend to next chunk as context
    - List items: merge contiguous list items
    - Body text: token-bounded sliding window
    """

    def __init__(
        self,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_items(
        self,
        items: List[Dict[str, Any]],
        source_filename: str = "",
    ) -> List[Dict[str, Any]]:
        all_chunks: List[Dict[str, Any]] = []
        source = source_filename or "unknown"
        counters: Dict[int, Dict[str, int]] = {}

        def _next_id(page: int, prefix: str) -> str:
            if page not in counters:
                counters[page] = {}
            idx = counters[page].get(prefix, 0)
            counters[page][prefix] = idx + 1
            return f"p{page}_{prefix}{idx}"

        i = 0
        while i < len(items):
            item = items[i]
            page = item["page"]
            itype = item["type"]
            text = item["text"]

            if itype == "table":
                chunk_id = _next_id(page, "t")
                all_chunks.append({
                    "text": text,
                    "metadata": {
                        "page": page,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "table",
                        "image_path": None,
                    },
                })
                i += 1

            elif itype == "picture":
                chunk_id = _next_id(page, "f")
                all_chunks.append({
                    "text": text,
                    "metadata": {
                        "page": page,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "figure",
                        "image_path": item.get("image_path"),
                    },
                })
                i += 1

            elif itype == "section_header":
                # Merge section header as context prefix for the next non-header item
                header_text = text
                j = i + 1
                while j < len(items) and items[j]["type"] == "section_header":
                    header_text += " | " + items[j]["text"]
                    j += 1
                if j < len(items):
                    # Prepend header to next item's text and fall through to normal handling
                    items[j]["text"] = f"[{header_text}] {items[j]['text']}"
                i = j  # skip past consumed headers

            elif itype == "list_item":
                # Merge contiguous list items
                merged = text
                j = i + 1
                while j < len(items) and items[j]["type"] == "list_item":
                    merged += "; " + items[j]["text"]
                    j += 1
                chunk_id = _next_id(page, "c")
                all_chunks.append({
                    "text": merged,
                    "metadata": {
                        "page": page,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "list",
                        "image_path": None,
                    },
                })
                i = j

            else:
                # body text — token-bounded sliding window
                chunks = self._split_text(text, page, source, _next_id)
                all_chunks.extend(chunks)
                i += 1

        logger.info(
            "Created %d chunk(s) from %d item(s) in '%s'",
            len(all_chunks), len(items), source,
        )
        return all_chunks

    def _split_text(
        self,
        text: str,
        page: int,
        source: str,
        next_id,
    ) -> List[Dict[str, Any]]:
        """Token-bounded sliding window for body text."""
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")
        tokens = encoder.encode(text)
        chunks: List[Dict[str, Any]] = []

        start = 0
        while start < len(tokens):
            end = start + self.chunk_size
            chunk_tokens = tokens[start:end]
            chunk_text = encoder.decode(chunk_tokens).strip()

            if chunk_text:
                chunk_id = next_id(page, "c")
                chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "page": page,
                        "chunk_id": chunk_id,
                        "source": source,
                        "chunk_type": "body",
                        "image_path": None,
                    },
                })

            step = self.chunk_size - self.chunk_overlap
            if step <= 0:
                step = 1
            start += step

        return chunks


class DoclingPipeline:
    """Single-pass PDF ingestion using IBM Docling.

    Replaces: PageRenderer, LayoutDetector, TableRecognizer,
              RegionExtractor, PDFParser, Chunker.

    Docling handles text, tables (with merged cells), figures,
    reading order, and hierarchical structure in one call.
    """

    def __init__(self) -> None:
        self.embedder = Embedder()
        self.es_client = ESClient()
        self.chunker = DoclingChunker()
        self._converter = None

    def _get_converter(self):
        if self._converter is None:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption

            pipeline_options = PdfPipelineOptions()
            pipeline_options.do_ocr = False
            pipeline_options.do_table_structure = True

            self._converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
        return self._converter

    def preview(self, pdf_path: str, cache_dir: Any) -> List[Dict[str, Any]]:
        """Extract layout regions and render page images for admin preview."""
        import fitz
        import hashlib
        from pathlib import Path

        cache_dir_path = Path(cache_dir)

        # 1. Render pages with PyMuPDF and calculate cache hash
        pdf_doc = fitz.open(pdf_path)
        dpi = 200
        scale = dpi / 72.0

        with open(pdf_path, "rb") as f:
            raw_bytes = f.read()
        file_hash = hashlib.md5(raw_bytes).hexdigest()

        response_pages = []
        page_heights = {}

        for page_idx in range(len(pdf_doc)):
            page_num = page_idx + 1
            page = pdf_doc[page_idx]
            page_heights[page_num] = page.rect.height

            pix = page.get_pixmap(dpi=dpi)
            cache_path = cache_dir_path / f"{file_hash}_p{page_num}_dpi{dpi}.png"
            cache_path.write_bytes(pix.tobytes("png"))

            response_pages.append({
                "page_num": page_num,
                "image_url": f"/api/cache/{file_hash}_p{page_num}_dpi{dpi}.png",
                "width": int(page.rect.width),
                "height": int(page.rect.height),
                "regions": [],
            })
        pdf_doc.close()

        # 2. Detect layout regions with Docling
        try:
            converter = self._get_converter()
            result = converter.convert(pdf_path)
            doc = result.document

            for item, _ in doc.iterate_items():
                if not item.prov:
                    continue
                prov = item.prov[0]
                page_no = prov.page_no
                bbox = prov.bbox
                if not bbox:
                    continue

                h = page_heights.get(page_no, 792.0)
                region = {
                    "type": item.label,
                    "bbox": [
                        int(bbox.l * scale),
                        int((h - bbox.t) * scale),
                        int(bbox.r * scale),
                        int((h - bbox.b) * scale),
                    ],
                    "score": 0.95,
                    "page": page_no,
                }
                for rp in response_pages:
                    if rp["page_num"] == page_no:
                        rp["regions"].append(region)
                        break
        except Exception as e:
            logger.warning("Docling layout detection failed in preview: %s", e)

        return response_pages

    def _convert_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        """Convert PDF to list of typed item dicts using Docling."""
        converter = self._get_converter()
        result = converter.convert(pdf_path)
        doc = result.document

        items: List[Dict[str, Any]] = []
        for item, _level in doc.iterate_items():
            page = item.prov[0].page_no if item.prov else 1
            label = item.label

            if label == "table":
                text = item.export_to_markdown(doc=doc) or ""
                items.append({
                    "page": page,
                    "type": "table",
                    "text": text.strip(),
                    "image_path": None,
                })

            elif label == "picture":
                caption = item.caption_text(doc) if item.caption_text else ""
                if not caption:
                    caption = "Figure on page {}".format(page)
                items.append({
                    "page": page,
                    "type": "picture",
                    "text": caption if isinstance(caption, str) else str(caption),
                    "image_path": None,
                })

            elif label in ("section_header", "section-header", "heading"):
                items.append({
                    "page": page,
                    "type": "section_header",
                    "text": (item.text or "").strip(),
                    "image_path": None,
                })

            elif label == "list_item" or label == "list-item":
                items.append({
                    "page": page,
                    "type": "list_item",
                    "text": (item.text or "").strip(),
                    "image_path": None,
                })

            else:
                # text, paragraph, caption, footnote, etc.
                items.append({
                    "page": page,
                    "type": "text",
                    "text": (item.text or "").strip(),
                    "image_path": None,
                })

        return items

    def run(
        self,
        pdf_path: str,
        owner_id: str = "guest",
        session_id: str = "default_session",
        is_persistent: bool = False,
        allowed_users: List[str] | None = None,
    ) -> Dict[str, Any]:
        if allowed_users is None:
            allowed_users = []

        source_filename = os.path.basename(pdf_path)
        console.rule(f"[bold blue]Docling Ingestion: {source_filename}")

        # Step 1: Convert PDF with Docling
        console.print("[bold]Step 1/3:[/bold] Converting PDF with Docling...")
        try:
            items = self._convert_pdf(pdf_path)
        except Exception as e:
            logger.exception("Docling conversion failed")
            raise RuntimeError(f"Docling PDF conversion failed: {e}") from e

        pages = sorted(set(it["page"] for it in items))
        tables = sum(1 for it in items if it["type"] == "table")
        pictures = sum(1 for it in items if it["type"] == "picture")
        console.print(
            f"  [green]Done[/green] — {len(pages)} page(s), {len(items)} item(s) "
            f"({tables} table(s), {pictures} picture(s))"
        )

        # Step 2: Chunk
        console.print("[bold]Step 2/3:[/bold] Chunking document...")
        chunks = self.chunker.chunk_items(items, source_filename=source_filename)
        console.print(f"  [green]Done[/green] — {len(chunks)} chunk(s) created")

        if not chunks:
            console.print(
                "[yellow]WARNING: No chunks created. "
                "The PDF may be empty or image-only.[/yellow]"
            )
            return {
                "source": source_filename,
                "pages_parsed": len(pages),
                "chunks_created": 0,
                "chunks_indexed": 0,
                "pages_failed": 0,
            }

        # Step 3: Embed + Index
        console.print("[bold]Step 3/3:[/bold] Embedding and indexing...")
        texts = [chunk["text"] for chunk in chunks]

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Embedding chunks", total=len(texts))

            all_embeddings: List[List[float]] = []
            batch_size = self.embedder.BATCH_SIZE

            for start in range(0, len(texts), batch_size):
                batch = texts[start : start + batch_size]
                batch_embeddings = self.embedder.embed_batch(batch)
                all_embeddings.extend(batch_embeddings)
                progress.update(task, advance=len(batch))

        for chunk, embedding in zip(chunks, all_embeddings):
            chunk["embedding"] = embedding
            chunk["metadata"]["owner_id"] = owner_id
            chunk["metadata"]["session_id"] = session_id
            chunk["metadata"]["is_persistent"] = is_persistent
            chunk["metadata"]["allowed_users"] = allowed_users

        console.print(
            f"  [green]Done[/green] — {len(all_embeddings)} embedding(s) generated"
        )

        self.es_client.create_index_if_not_exists()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Indexing chunks", total=len(chunks))

            indexed_count = 0
            upsert_batch_size = 200

            for start in range(0, len(chunks), upsert_batch_size):
                batch = chunks[start : start + upsert_batch_size]
                count = self.es_client.upsert_chunks(batch)
                indexed_count += count
                progress.update(task, advance=len(batch))

        summary = {
            "source": source_filename,
            "pages_parsed": len(pages),
            "chunks_created": len(chunks),
            "chunks_indexed": indexed_count,
            "pages_failed": 0,
        }

        console.rule("[bold green]Docling Ingestion Complete")
        console.print(f"  Source:   {summary['source']}")
        console.print(f"  Pages:    {summary['pages_parsed']}")
        console.print(f"  Chunks:   {summary['chunks_created']}")
        console.print(f"  Indexed:  {summary['chunks_indexed']}")
        console.print()

        return summary


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m rag.ingestion.docling_pipeline <path/to/file.pdf>")
        sys.exit(1)

    pipeline = DoclingPipeline()
    result = pipeline.run(sys.argv[1])
    print(f"\nPipeline complete: {result}")
