import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH)

GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

ES_HOST: str = os.getenv("ES_HOST", "http://localhost:9200")
ES_INDEX: str = os.getenv("ES_INDEX", "rag_chunks")

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
    "You are a strict, precise financial document analyst. You ONLY answer using the context "
    "provided below. Each context chunk has a page number and chunk ID in its header. "
    "Always end your answer by listing the pages you used in this format: [Sources: p3, p7]. "
    "If the user asks for a summary, provide a summary of the context chunks provided. "
    "For ALL other questions: If the exact answer cannot be found in the provided context, you MUST respond EXACTLY and ONLY with the phrase: "
    '"Not found in the document." '
    "Do not provide explanations. Do not provide alternative information. Do not mention what the text focuses on instead. "
    "Do not guess. Do not use outside knowledge."
)
