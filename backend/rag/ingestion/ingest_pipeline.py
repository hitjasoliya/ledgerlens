from __future__ import annotations

import os
from typing import Dict, List

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from rag.ingestion.parser import PDFParser
from rag.ingestion.chunker import Chunker
from rag.intelligence.embedder import Embedder
from rag.storage.es_client import ESClient

console = Console()


class IngestPipeline:
    def __init__(self) -> None:
        self.parser = PDFParser()
        self.chunker = Chunker()
        self.embedder = Embedder()
        self.es_client = ESClient()

    def run(self, pdf_path: str) -> Dict:
        source_filename = os.path.basename(pdf_path)

        console.rule(f"[bold blue]Ingesting: {source_filename}")

        console.print("\n[bold]Step 1/3:[/bold] Parsing PDF...")
        pages = self.parser.parse(pdf_path)
        console.print(f"  ✓ {len(pages)} page(s) extracted\n")

        console.print("[bold]Step 2/3:[/bold] Chunking text...")
        chunks = self.chunker.chunk(pages, source_filename=source_filename)
        console.print(f"  ✓ {len(chunks)} chunk(s) created\n")

        if not chunks:
            console.print("[yellow]WARNING: No chunks created. "
                          "The PDF may be empty or image-only.[/yellow]")
            return {
                "source": source_filename,
                "pages_parsed": len(pages),
                "chunks_created": 0,
                "chunks_indexed": 0,
            }

        console.print("[bold]Step 3/3:[/bold] Generating embeddings...")
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

        console.print(f"  ✓ {len(all_embeddings)} embedding(s) generated\n")

        console.print("  Indexing in Elasticsearch...")
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

        console.print(f"  ✓ {indexed_count} chunk(s) indexed\n")

        summary = {
            "source": source_filename,
            "pages_parsed": len(pages),
            "chunks_created": len(chunks),
            "chunks_indexed": indexed_count,
        }

        console.rule("[bold green]Ingestion Complete")
        console.print(f"  Source:   {summary['source']}")
        console.print(f"  Pages:    {summary['pages_parsed']}")
        console.print(f"  Chunks:   {summary['chunks_created']}")
        console.print(f"  Indexed:  {summary['chunks_indexed']}")
        console.print()

        return summary


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python -m rag.ingestion.ingest_pipeline <path/to/file.pdf>")
        sys.exit(1)

    pipeline = IngestPipeline()
    result = pipeline.run(sys.argv[1])
    print(f"\n✅ Pipeline complete: {result}")
