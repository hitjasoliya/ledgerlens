"""
intelligence/generator.py — Layer 4: Google Gemini generation wrapper.

Wraps the Gemini GenerativeModel API (gemini-2.0-flash) with:
  - The strict financial-analyst system prompt
  - Context assembly from retrieved chunks (with page/chunk headers)
  - Single generate() method returning the plain answer string
"""
from __future__ import annotations

from typing import Any, Dict, List

import google.generativeai as genai

from utils.config import GEMINI_API_KEY, GENERATION_MODEL, SYSTEM_PROMPT


class Generator:
    """Generates answers from retrieved context using Gemini 2.0 Flash."""

    def __init__(self) -> None:
        """Initialise the Gemini client with the configured API key."""
        if not GEMINI_API_KEY:
            raise ValueError(
                "[Generator] GEMINI_API_KEY is not set. "
                "Please add it to your .env file."
            )
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=GENERATION_MODEL,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                temperature=0.1,       # low temp for factual precision
                max_output_tokens=1024,
            ),
        )

    def _build_context_string(self, context_chunks: List[Dict[str, Any]]) -> str:
        """
        Assemble retrieved chunks into a numbered context block.

        Each chunk is formatted as:
            [Chunk p3_c2 | Page 3]
            <chunk text>

        Args:
            context_chunks: List of dicts with keys: text, page, chunk_id.

        Returns:
            A single string with all chunks formatted and separated by blank lines.
        """
        parts: List[str] = []
        for i, chunk in enumerate(context_chunks, start=1):
            header = f"[Chunk {chunk['chunk_id']} | Page {chunk['page']}]"
            parts.append(f"{header}\n{chunk['text']}")
        return "\n\n".join(parts)

    def generate(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> str:
        """
        Generate an answer to the question using the retrieved context chunks.

        Args:
            question: The user's natural-language question.
            context_chunks: Retrieved chunks from hybrid search, each with
                            keys: text, page, chunk_id.
            conversation_history: Optional list of prior {role, content} messages
                                  for multi-turn context.

        Returns:
            The model's answer as a plain string (includes [Sources: ...] footer).
        """
        context_str = self._build_context_string(context_chunks)

        # Build the conversation for Gemini
        # Gemini uses "user" and "model" roles (not "assistant")
        history = []
        if conversation_history:
            for msg in conversation_history:
                role = "model" if msg["role"] == "assistant" else "user"
                history.append({"role": role, "parts": [msg["content"]]})

        # Final user message with context + question
        user_message = (
            f"Context:\n{context_str}\n\n"
            f"---\n\n"
            f"Question: {question}"
        )

        try:
            # Start a chat session with history for multi-turn
            chat = self.model.start_chat(history=history)
            response = chat.send_message(user_message)
            return response.text.strip()
        except Exception as exc:
            raise RuntimeError(
                f"[Generator] Failed to generate answer: {exc}"
            ) from exc


# ── Quick self-test ─────────────────────────────────────────────────
if __name__ == "__main__":
    generator = Generator()

    # Fake context to test formatting + generation
    test_chunks = [
        {
            "text": "Revenue for FY2024 was $45.2 billion, up 12% year-over-year.",
            "page": 3,
            "chunk_id": "p3_c1",
        },
        {
            "text": "Operating expenses increased to $28.1 billion due to R&D investment.",
            "page": 7,
            "chunk_id": "p7_c2",
        },
    ]

    answer = generator.generate(
        question="What was the revenue for FY2024?",
        context_chunks=test_chunks,
    )
    print(f"✅ Generator working\n\nAnswer:\n{answer}")
