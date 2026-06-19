import abc
from typing import Any, Dict, List

from rag.utils.config import GEMINI_API_KEY, GENERATION_MODEL, SYSTEM_PROMPT
from rag.utils.timeout import TimeoutError as ThreadTimeoutError


class Generator(abc.ABC):
    @abc.abstractmethod
    def generate(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> str:
        """Generate an answer using context chunks and conversation history."""
        pass

    @abc.abstractmethod
    def generate_greeting(
        self,
        question: str,
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> str:
        """Generate a response to casual greetings and pleasantries."""
        pass


class GeminiGenerator(Generator):
    GENERATE_TIMEOUT: int = 60  # seconds

    def __init__(self) -> None:
        if not GEMINI_API_KEY:
            raise ValueError(
                "[GeminiGenerator] GEMINI_API_KEY is not set. "
                "Please add it to your .env file."
            )
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        self.model = genai.GenerativeModel(
            model_name=GENERATION_MODEL,
            system_instruction=SYSTEM_PROMPT,
            generation_config=genai.GenerationConfig(
                temperature=0.15,
                max_output_tokens=2048,
                top_p=0.95,
            ),
        )
        self.greeting_model = genai.GenerativeModel(
            model_name=GENERATION_MODEL,
            system_instruction=(
                "You are LedgerLens, a helpful and precise assistant for analyzing financial documents. "
                "The user is saying a greeting, pleasantry, or other casual remark. "
                "Respond in a warm, polite, professional, and concise manner. "
                "Keep your response to 1-2 sentences. "
                "Invite the user to ask questions about their uploaded financial documents."
            ),
            generation_config=genai.GenerationConfig(
                temperature=0.7,
                max_output_tokens=150,
            ),
        )

    def _send_with_timeout(self, chat_session, message: str) -> str:
        from rag.utils.timeout import timeout_after

        @timeout_after(self.GENERATE_TIMEOUT)
        def _send() -> str:
            response = chat_session.send_message(message)
            return response.text.strip()

        return _send()

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
            return self._send_with_timeout(chat, user_message)
        except ThreadTimeoutError:
            raise RuntimeError(f"Answer generation timed out after {self.GENERATE_TIMEOUT}s")
        except Exception as exc:
            raise RuntimeError(
                f"[GeminiGenerator] Failed to generate answer: {exc}"
            ) from exc

    def generate_greeting(
        self,
        question: str,
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> str:
        history = []
        if conversation_history:
            for msg in conversation_history:
                role = "model" if msg["role"] == "assistant" else "user"
                history.append({"role": role, "parts": [msg["content"]]})

        try:
            chat = self.greeting_model.start_chat(history=history)
            return self._send_with_timeout(chat, question)
        except ThreadTimeoutError:
            raise RuntimeError(f"Greeting generation timed out after {self.GENERATE_TIMEOUT}s")
        except Exception as exc:
            raise RuntimeError(
                f"[GeminiGenerator] Failed to generate greeting: {exc}"
            ) from exc


class StubGenerator(Generator):
    """An in-memory stub implementation of the Generator interface for off-network tests."""

    def __init__(self, stub_answer: str = "Stubbed Response", stub_greeting: str = "Hello from Stub!") -> None:
        self.stub_answer = stub_answer
        self.stub_greeting = stub_greeting

    def generate(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> str:
        return self.stub_answer

    def generate_greeting(
        self,
        question: str,
        conversation_history: List[Dict[str, str]] | None = None,
    ) -> str:
        return self.stub_greeting


if __name__ == "__main__":
    generator = GeminiGenerator()

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
    print(f"✅ GeminiGenerator working\n\nAnswer:\n{answer}")
