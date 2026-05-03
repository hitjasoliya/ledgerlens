"""
main.py — Layer 1: CLI entry point for the RAG Hackathon chatbot.

Two modes:
  python main.py --ingest path/to/file.pdf   → runs ingestion pipeline
  python main.py --chat                       → starts interactive Q&A loop
"""
from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.theme import Theme

# Custom theme for consistent styling
custom_theme = Theme({
    "banner": "bold cyan",
    "prompt": "bold green",
    "answer": "white",
    "citation": "dim cyan",
    "success": "bold green",
    "error": "bold red",
    "info": "dim white",
})

console = Console(theme=custom_theme)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for --ingest and --chat modes."""
    parser = argparse.ArgumentParser(
        prog="rag_hackathon",
        description="RAG Chatbot — Query financial PDFs with AI-powered answers and citations.",
    )
    parser.add_argument(
        "--ingest",
        type=str,
        metavar="PDF_PATH",
        help="Path to a PDF file to ingest into the system.",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help="Start an interactive Q&A session over ingested documents.",
    )

    args = parser.parse_args()

    # If neither flag is given, print help and exit
    if not args.ingest and not args.chat:
        parser.print_help()
        sys.exit(0)

    return args


# ── Ingest mode ─────────────────────────────────────────────────────

def run_ingest(pdf_path: str) -> None:
    """Run the full ingestion pipeline on the given PDF."""
    from ingestion.ingest_pipeline import IngestPipeline

    console.print()
    console.print("[banner]📄 RAG Document Ingestion[/banner]")
    console.print()

    try:
        pipeline = IngestPipeline()
        summary = pipeline.run(pdf_path)
    except FileNotFoundError as exc:
        console.print(f"[error]✗ {exc}[/error]")
        sys.exit(1)
    except Exception as exc:
        console.print(f"[error]✗ Ingestion failed: {exc}[/error]")
        sys.exit(1)

    # Print success summary
    console.print()
    console.print(Panel(
        f"[success]✓ Ingestion complete![/success]\n\n"
        f"  Source:          {summary['source']}\n"
        f"  Pages parsed:    {summary['pages_parsed']}\n"
        f"  Chunks created:  {summary['chunks_created']}\n"
        f"  Chunks indexed:  {summary['chunks_indexed']}",
        title="Summary",
        border_style="green",
    ))
    console.print()


# ── Chat mode ───────────────────────────────────────────────────────

def run_chat() -> None:
    """Start the interactive REPL chat loop using the RAG engine."""
    from orchestrator.engine import RAGEngine

    # Print welcome banner
    console.print()
    console.print(Panel(
        Text.from_markup(
            "[bold cyan]📊 RAG Financial Document Q&A[/bold cyan]\n\n"
            "[dim]Ask questions about your ingested documents.\n"
            "Type [bold]exit[/bold] or press [bold]Ctrl+C[/bold] to quit.[/dim]"
        ),
        border_style="cyan",
        padding=(1, 2),
    ))
    console.print()

    # Initialise the RAG engine
    try:
        engine = RAGEngine()
    except Exception as exc:
        console.print(f"[error]✗ Failed to initialise RAG engine: {exc}[/error]")
        console.print("[info]Make sure Elasticsearch is running and .env is configured.[/info]")
        sys.exit(1)

    console.print("[success]✓ Engine ready. Start asking questions![/success]\n")

    # REPL loop
    while True:
        try:
            question = console.input("[prompt]You:[/prompt] ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[info]👋 Goodbye![/info]")
            break

        # Exit command
        if question.lower() in ("exit", "quit", "q"):
            console.print("[info]👋 Goodbye![/info]")
            break

        # Skip empty input
        if not question:
            continue

        # Process the question
        try:
            result = engine.chat(question)
        except Exception as exc:
            console.print(f"[error]✗ Error: {exc}[/error]\n")
            continue

        answer_text = result["answer"]
        console.print()
        console.print(Panel(
            answer_text,
            title="Answer",
            border_style="cyan",
            padding=(1, 2),
        ))

        # Display citations below the panel
        citations = result.get("citations", [])
        if citations:
            for cite in citations:
                console.print(
                    f"  [citation]→ Page {cite['page']} ({cite['chunk_id']})[/citation]"
                )
        else:
            console.print("  [citation]→ No specific citations[/citation]")

        console.print()  # blank line before next prompt


# ── Entry point ─────────────────────────────────────────────────────

def main() -> None:
    """Main entry point — dispatch to ingest or chat mode."""
    args = parse_args()

    if args.ingest:
        run_ingest(args.ingest)
    elif args.chat:
        run_chat()


if __name__ == "__main__":
    main()
