"""
utils/config.py — Centralised configuration loader.

Reads all settings from .env via python-dotenv and exposes them as
module-level constants. Every other module imports from here —
nothing is hardcoded elsewhere.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# ── locate and load .env ────────────────────────────────────────────
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

# ── Gemini ──────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

# ── Elasticsearch ───────────────────────────────────────────────────
ES_HOST: str = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX: str = os.getenv("ES_INDEX", "rag_chunks")

# ── Chunking ────────────────────────────────────────────────────────
CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

# ── Retrieval ───────────────────────────────────────────────────────
TOP_K: int = int(os.getenv("TOP_K", "5"))

# ── Model identifiers (single source of truth) ─────────────────────
EMBEDDING_MODEL: str = "models/gemini-embedding-001"
EMBEDDING_DIMS: int = 768
GENERATION_MODEL: str = "models/gemini-3.1-flash-lite-preview"

UNSTRUCTURED_PDF_STRATEGY: str = os.getenv(
    "UNSTRUCTURED_PDF_STRATEGY", "fast"
)

# ── System prompt (used by generator.py) ────────────────────────────
SYSTEM_PROMPT: str = (
    "You are a precise financial document analyst. You ONLY answer using the context "
    "provided below. Each context chunk has a page number and chunk ID in its header. "
    "Always end your answer by listing the pages you used in this format: [Sources: p3, p7] "
    "If the answer cannot be found in the provided context, respond ONLY with: "
    '"Not found in the document." '
    "Do not guess. Do not use outside knowledge."
)
