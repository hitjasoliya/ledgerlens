from __future__ import annotations

from typing import Any, Dict, List

import google.generativeai as genai

from rag.utils.config import GEMINI_API_KEY, GENERATION_MODEL, SYSTEM_PROMPT


class Generator:
    def __init__(self) -> None:
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
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )

    def _build_context_string(self, context_chunks: List[Dict[str, Any]]) -> str:
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
        context_str = self._build_context_string(context_chunks)

        history = []
        if conversation_history:
            for msg in conversation_history:
                role = "model" if msg["role"] == "assistant" else "user"
                history.append({"role": role, "parts": [msg["content"]]})

        user_message = (
            f"Context:\n{context_str}\n\n"
            f"---\n\n"
            f"Question: {question}"
        )

        try:
            chat = self.model.start_chat(history=history)
            response = chat.send_message(user_message)
            return response.text.strip()
        except Exception as exc:
            raise RuntimeError(
                f"[Generator] Failed to generate answer: {exc}"
            ) from exc


if __name__ == "__main__":
    generator = Generator()

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
