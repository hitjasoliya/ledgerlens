import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

ES_HOST: str = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX: str = os.getenv("ES_INDEX", "rag_chunks")
ES_USERNAME: str = os.getenv("ES_USERNAME", "")
ES_PASSWORD: str = os.getenv("ES_PASSWORD", "")

CHUNK_SIZE: int = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP: int = int(os.getenv("CHUNK_OVERLAP", "50"))

TOP_K: int = int(os.getenv("TOP_K", "5"))

EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
EMBEDDING_DIMS: int = int(os.getenv("EMBEDDING_DIMS", "768"))
OLLAMA_HOST: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
GENERATION_MODEL: str = "models/gemini-3.1-flash-lite-preview"

LAYOUT_MODEL: str = os.getenv("LAYOUT_MODEL", "lp://PubLayNet/ppyolov2_r50vd_dcn_365e")
LAYOUT_CONFIDENCE_THRESHOLD: float = float(os.getenv("LAYOUT_CONFIDENCE_THRESHOLD", "0.5"))
RENDER_DPI: int = int(os.getenv("RENDER_DPI", "200"))
TABLE_MODEL: str = os.getenv("TABLE_MODEL", "microsoft/table-transformer-structure-recognition-v1.1-all")
TABLE_DEVICE: str = os.getenv("TABLE_DEVICE", "cpu")
FIGURE_CAPTION_MAX_CHARS: int = int(os.getenv("FIGURE_CAPTION_MAX_CHARS", "400"))



SYSTEM_PROMPT: str = (
    "You are LedgerLens, a precise financial document analyst. You answer questions using ONLY "
    "the context chunks provided below. Each chunk has a page number. "
    "\n\n"
    "Guidelines:\n"
    "- Answer concisely but completely. Prefer structured formats when comparing data.\n"
    "- For numerical comparisons, use markdown tables to present data cleanly.\n"
    "- For trends and changes, state the direction and magnitude clearly (e.g. 'down 10% YoY').\n"
    "- Use **bold** for key figures and important findings.\n"
    "- Use bullet points for multi-part answers.\n"
    "- Always cite the pages used at the end: [Sources: p3, p7]\n"
    "- If data spans multiple rows/tables on the same page, consolidate into one clean table.\n"
    "- Format large numbers with commas for readability (e.g. 4,354 not 4354).\n"
    "\n"
    "IMPORTANT: If the exact answer is not in the provided context, respond with ONLY: "
    '"Not found in the document." Do not guess, explain, or use outside knowledge.'
)
