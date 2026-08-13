from __future__ import annotations
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from common.search import Embedder, ESClient

logger = logging.getLogger(__name__)

# Try importing IBM Docling for layout-aware PDF parsing
_docling_available = False
try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.datamodel.base_models import InputFormat
    _docling_available = True
except ImportError:
    _docling_available = False

try:
    import fitz  # PyMuPDF
    _fitz_available = True
except ImportError:
    _fitz_available = False

try:
    import pdfplumber
    _pdfplumber_available = True
except ImportError:
    _pdfplumber_available = False


class DoclingChunker:
    """Chunks DoclingDocument items into indexable chunks.

    Strategies:
    - Tables: atomic chunk (markdown layout preserved)
    - Pictures: caption text as figure chunk
    - Section headers: prepended as context to next text chunk
    - List items: merge contiguous list items
    - Body text: token-bounded sliding window via tiktoken / word split
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk_items(
        self,
        items: List[Dict[str, Any]],
        filename: str,
        document_id: str,
        allowed_users: List[str],
        scope: str,
        is_persistent: bool,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        i = 0
        while i < len(items):
            item = items[i]
            page_number = item.get("page_number", 1)
            item_type = item.get("item_type", "paragraph")
            text = (item.get("text") or "").strip()

            if not text:
                i += 1
                continue

            if item_type == "table":
                chunk_id = f"{document_id}_p{page_number}_t{uuid.uuid4().hex[:6]}"
                chunks.append(
                    self._build_chunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        item_type="table",
                        text=text,
                        allowed_users=allowed_users,
                        scope=scope,
                        is_persistent=is_persistent,
                        session_id=session_id,
                    )
                )
                i += 1

            elif item_type in ("picture", "figure"):
                chunk_id = f"{document_id}_p{page_number}_f{uuid.uuid4().hex[:6]}"
                chunks.append(
                    self._build_chunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        item_type="figure",
                        text=text,
                        allowed_users=allowed_users,
                        scope=scope,
                        is_persistent=is_persistent,
                        session_id=session_id,
                    )
                )
                i += 1

            elif item_type == "section_header":
                header_text = text
                j = i + 1
                while j < len(items) and items[j].get("item_type") == "section_header":
                    header_text += " | " + (items[j].get("text") or "").strip()
                    j += 1
                if j < len(items):
                    next_text = (items[j].get("text") or "").strip()
                    items[j]["text"] = f"[{header_text}] {next_text}"
                else:
                    # Trailing header standalone chunk
                    chunk_id = f"{document_id}_p{page_number}_h{uuid.uuid4().hex[:6]}"
                    chunks.append(
                        self._build_chunk(
                            chunk_id=chunk_id,
                            document_id=document_id,
                            filename=filename,
                            page_number=page_number,
                            item_type="section_header",
                            text=header_text,
                            allowed_users=allowed_users,
                            scope=scope,
                            is_persistent=is_persistent,
                            session_id=session_id,
                        )
                    )
                i = j

            elif item_type == "list_item":
                merged = text
                j = i + 1
                while (
                    j < len(items)
                    and items[j].get("item_type") == "list_item"
                    and items[j].get("page_number") == page_number
                ):
                    merged += "; " + (items[j].get("text") or "").strip()
                    j += 1
                chunk_id = f"{document_id}_p{page_number}_l{uuid.uuid4().hex[:6]}"
                chunks.append(
                    self._build_chunk(
                        chunk_id=chunk_id,
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        item_type="list",
                        text=merged,
                        allowed_users=allowed_users,
                        scope=scope,
                        is_persistent=is_persistent,
                        session_id=session_id,
                    )
                )
                i = j

            else:
                # Body text - sliding window chunking
                split_chunks = self._split_text(
                    text=text,
                    page_number=page_number,
                    document_id=document_id,
                    filename=filename,
                    allowed_users=allowed_users,
                    scope=scope,
                    is_persistent=is_persistent,
                    session_id=session_id,
                )
                chunks.extend(split_chunks)
                i += 1

        return chunks

    def _build_chunk(
        self,
        chunk_id: str,
        document_id: str,
        filename: str,
        page_number: int,
        item_type: str,
        text: str,
        allowed_users: List[str],
        scope: str,
        is_persistent: bool,
        session_id: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "filename": filename,
            "page_number": page_number,
            "item_type": item_type,
            "text": text,
            "allowed_users": allowed_users,
            "scope": scope,
            "is_persistent": is_persistent,
            "session_id": session_id or "",
        }

    def _split_text(
        self,
        text: str,
        page_number: int,
        document_id: str,
        filename: str,
        allowed_users: List[str],
        scope: str,
        is_persistent: bool,
        session_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        chunks: List[Dict[str, Any]] = []
        try:
            import tiktoken
            encoder = tiktoken.get_encoding("cl100k_base")
            tokens = encoder.encode(text)

            if len(tokens) <= self.chunk_size:
                cid = f"{document_id}_p{page_number}_c{uuid.uuid4().hex[:6]}"
                return [
                    self._build_chunk(
                        chunk_id=cid,
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        item_type="paragraph",
                        text=text,
                        allowed_users=allowed_users,
                        scope=scope,
                        is_persistent=is_persistent,
                        session_id=session_id,
                    )
                ]

            start = 0
            step = max(1, self.chunk_size - self.chunk_overlap)
            while start < len(tokens):
                chunk_tokens = tokens[start : start + self.chunk_size]
                chunk_text = encoder.decode(chunk_tokens).strip()
                if chunk_text:
                    cid = f"{document_id}_p{page_number}_c{uuid.uuid4().hex[:6]}"
                    chunks.append(
                        self._build_chunk(
                            chunk_id=cid,
                            document_id=document_id,
                            filename=filename,
                            page_number=page_number,
                            item_type="paragraph",
                            text=chunk_text,
                            allowed_users=allowed_users,
                            scope=scope,
                            is_persistent=is_persistent,
                            session_id=session_id,
                        )
                    )
                start += step
        except Exception:
            # Word-based fallback if tiktoken unavailable
            words = text.split()
            if len(words) <= self.chunk_size:
                cid = f"{document_id}_p{page_number}_c{uuid.uuid4().hex[:6]}"
                return [
                    self._build_chunk(
                        chunk_id=cid,
                        document_id=document_id,
                        filename=filename,
                        page_number=page_number,
                        item_type="paragraph",
                        text=text,
                        allowed_users=allowed_users,
                        scope=scope,
                        is_persistent=is_persistent,
                        session_id=session_id,
                    )
                ]
            step = max(1, self.chunk_size - self.chunk_overlap)
            for start_idx in range(0, len(words), step):
                sub_words = words[start_idx : start_idx + self.chunk_size]
                sub_text = " ".join(sub_words).strip()
                if sub_text:
                    cid = f"{document_id}_p{page_number}_c{uuid.uuid4().hex[:6]}"
                    chunks.append(
                        self._build_chunk(
                            chunk_id=cid,
                            document_id=document_id,
                            filename=filename,
                            page_number=page_number,
                            item_type="paragraph",
                            text=sub_text,
                            allowed_users=allowed_users,
                            scope=scope,
                            is_persistent=is_persistent,
                            session_id=session_id,
                        )
                    )

        return chunks


class IngestionPipeline:
    def __init__(self) -> None:
        self.embedder = Embedder()
        self.es_client = ESClient()
        self.chunker = DoclingChunker()
        self._converter = None

    def _get_converter(self):
        if self._converter is None and _docling_available:
            try:
                # Docling's ONNX/torch models are wrapped in torch.compile; newer
                # torch releases (>= 2.7) can emit invalid kernel code on macOS,
                # which aborts conversion. Fall back to eager execution instead.
                import torch

                torch._dynamo.config.suppress_errors = True

                pipeline_options = PdfPipelineOptions()
                pipeline_options.do_ocr = True
                pipeline_options.do_table_structure = True

                try:
                    from docling.datamodel.pipeline_options import EasyOcrOptions
                    pipeline_options.ocr_options = EasyOcrOptions()
                except Exception:
                    pass

                self._converter = DocumentConverter(
                    format_options={
                        InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                    }
                )
                logger.info("Initialized IBM Docling DocumentConverter successfully")
            except Exception as exc:
                logger.warning(f"Could not initialize Docling DocumentConverter: {exc}")
                self._converter = None
        return self._converter

    def parse_pdf(self, pdf_path: str) -> List[Dict[str, Any]]:
        converter = self._get_converter()
        items: List[Dict[str, Any]] = []

        # Attempt IBM Docling Layout Parsing
        if converter is not None:
            try:
                result = converter.convert(pdf_path)
                doc = result.document
                for item, _level in doc.iterate_items():
                    page = item.prov[0].page_no if item.prov else 1
                    label = getattr(item, "label", "text")

                    if label == "table":
                        text = item.export_to_markdown(doc=doc) or ""
                        if text.strip():
                            items.append({
                                "page_number": page,
                                "item_type": "table",
                                "text": text.strip(),
                            })
                    elif label == "picture":
                        caption = ""
                        if hasattr(item, "caption_text") and callable(item.caption_text):
                            caption = item.caption_text(doc)
                        if not caption:
                            caption = f"Figure on page {page}"
                        items.append({
                            "page_number": page,
                            "item_type": "picture",
                            "text": str(caption).strip(),
                        })
                    elif label in ("section_header", "section-header", "heading"):
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            items.append({
                                "page_number": page,
                                "item_type": "section_header",
                                "text": t,
                            })
                    elif label in ("list_item", "list-item"):
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            items.append({
                                "page_number": page,
                                "item_type": "list_item",
                                "text": t,
                            })
                    else:
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            items.append({
                                "page_number": page,
                                "item_type": "paragraph",
                                "text": t,
                            })

                if items:
                    logger.info("Docling extracted %d item(s) from %s", len(items), pdf_path)
                    return items
            except Exception as exc:
                logger.warning("Docling conversion failed on %s: %s. Falling back to PDF text extract.", pdf_path, exc)

        # Fallback 1: pdfplumber
        if _pdfplumber_available:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for idx, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        if text and text.strip():
                            for block in text.split("\n\n"):
                                btext = block.strip()
                                if btext:
                                    items.append({
                                        "page_number": idx + 1,
                                        "item_type": "paragraph",
                                        "text": btext,
                                    })
                if items:
                    logger.info("pdfplumber extracted %d item(s) from %s", len(items), pdf_path)
                    return items
            except Exception as exc:
                logger.warning("pdfplumber failed on %s: %s", pdf_path, exc)

        # Fallback 2: PyMuPDF (fitz)
        if _fitz_available:
            try:
                doc = fitz.open(pdf_path)
                for idx in range(len(doc)):
                    page = doc[idx]
                    text = page.get_text("text")
                    if text and text.strip():
                        for block in text.split("\n\n"):
                            btext = block.strip()
                            if btext:
                                items.append({
                                    "page_number": idx + 1,
                                    "item_type": "paragraph",
                                    "text": btext,
                                })
                doc.close()
                if items:
                    logger.info("PyMuPDF extracted %d item(s) from %s", len(items), pdf_path)
                    return items
            except Exception as exc:
                logger.warning("PyMuPDF failed on %s: %s", pdf_path, exc)

        return items

    def process(
        self,
        pdf_path: str,
        filename: str,
        document_id: str,
        allowed_users: List[str],
        scope: str = "employee",
        is_persistent: bool = True,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        items = self.parse_pdf(pdf_path)
        pages_parsed = max([item["page_number"] for item in items], default=0)

        chunks = self.chunker.chunk_items(
            items=items,
            filename=filename,
            document_id=document_id,
            allowed_users=allowed_users,
            scope=scope,
            is_persistent=is_persistent,
            session_id=session_id,
        )

        texts = [c["text"] for c in chunks]
        embeddings = self.embedder.embed_batch(texts) if texts else []

        for chunk, emb in zip(chunks, embeddings):
            chunk["vector"] = emb

        dims = len(embeddings[0]) if embeddings else None
        indexed_count = self.es_client.upsert_chunks(chunks, dims=dims) if chunks else 0

        return {
            "source": filename,
            "document_id": document_id,
            "pages_parsed": pages_parsed,
            "chunks_created": len(chunks),
            "chunks_indexed": indexed_count,
        }
