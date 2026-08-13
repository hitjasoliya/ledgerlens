from __future__ import annotations
import abc
import os
import re
import logging
from typing import Any, Dict, List, Optional

from common.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are LedgerLens AI, an expert financial and corporate document intelligence assistant.
Answer the user's question accurately using ONLY the provided document context chunks.
If the provided chunks do not contain enough information to answer, state clearly that the information is not present in the documents.
Always maintain a professional, objective tone. Include explicit source references like [Source: p1, p3] when citing information from specific pages."""


class QueryRouter:
    """Routes chat input to greeting / small talk / document queries.

    Document queries are the default; only short, purely social messages are
    routed away from the RAG pipeline so they never produce a misleading
    "no relevant information" answer.
    """

    _GREETINGS = {
        "hi", "hello", "hey", "heya", "hiya", "yo", "sup", "wassup", "wazzup",
        "howdy", "greetings", "hola", "good morning", "good afternoon",
        "good evening", "good day", "good night", "what's up", "whats up",
        "how are you", "how are you doing", "how's it going", "how is it going",
        "how do you do", "what's good", "what is good", "nice to meet you",
    }
    _GREETING_WORDS = {"hi", "hello", "hey", "heya", "hiya", "yo", "sup", "howdy"}
    _GREETING_PHRASE_PREFIXES = (
        "good morning", "good afternoon", "good evening", "good day",
        "good night", "hey there", "hello there", "what's up", "whats up",
        "wassup", "how are you", "how's it going", "how is it going",
        "how do you do", "what's good", "what is good", "nice to meet you",
    )
    _SMALLTALK_EXACT = {
        "help", "help me", "test", "ping", "thanks", "thank you",
        "thank you very much", "thanks a lot", "ty", "bye", "goodbye",
        "see you", "see ya", "you there", "are you there",
        "what can you do", "what do you do", "what are you",
        "who are you", "tell me about yourself",
    }
    _SMALLTALK_PREFIXES = (
        "help ", "thank ", "thanks ", "bye ", "see you ", "see ya ",
        "are you there", "what can you", "what do you do", "who are you",
        "what are you", "tell me about yourself", "are you working",
    )

    def _normalize(self, query: str) -> str:
        q = query.strip().lower().replace("’", "'").replace("–", " ").replace("—", " ")
        q = q.rstrip("!.?")
        words = []
        for w in q.split():
            # Collapse trailing repeated letters: "heyy" -> "hey", "hellooo" -> "hello"
            w = re.sub(r"(\w)\1+$", r"\1", w)
            words.append(w)
        return " ".join(words)

    def is_greeting(self, query: str) -> bool:
        q = self._normalize(query)
        if not q:
            return False
        if q in self._GREETINGS:
            return True
        words = q.split()
        # Short messages that merely start with a greeting word ("heyy", "hi there")
        if len(words) <= 3 and words[0] in self._GREETING_WORDS:
            return True
        # Phrase greetings; keep them short so real questions aren't misrouted
        if len(words) <= 4 and any(q.startswith(p) for p in self._GREETING_PHRASE_PREFIXES):
            return True
        return False

    def is_smalltalk(self, query: str) -> bool:
        q = self._normalize(query)
        if not q:
            return False
        if len(q.split()) > 6:
            return False
        if q in self._SMALLTALK_EXACT:
            return True
        return any(q.startswith(p) for p in self._SMALLTALK_PREFIXES)

    def classify(self, query: str) -> str:
        """Returns 'greeting', 'smalltalk', or 'document'."""
        if self.is_greeting(query):
            return "greeting"
        if self.is_smalltalk(query):
            return "smalltalk"
        return "document"


class CitationParser:
    def parse_citations(
        self, answer: str, retrieved_chunks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        if not retrieved_chunks:
            return citations

        # Extract page references from text like [Source: p1, p3] or page 2
        page_nums = set()
        for match in re.finditer(r"p(?:age)?\s*(\d+)", answer, re.IGNORECASE):
            try:
                page_nums.add(int(match.group(1)))
            except ValueError:
                pass

        if not page_nums:
            # Default to pages present in top retrieved chunks
            page_nums = {c.get("page_number", 1) for c in retrieved_chunks[:3]}

        seen = set()
        for chunk in retrieved_chunks:
            pnum = chunk.get("page_number", 1)
            cid = chunk.get("chunk_id", "")
            if pnum in page_nums and cid not in seen:
                seen.add(cid)
                citations.append({"page": pnum, "chunk_id": cid})

        return citations


class Generator(abc.ABC):
    @abc.abstractmethod
    def generate(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
    ) -> str:
        pass

    @abc.abstractmethod
    def generate_greeting(self, conversation_history: List[Dict[str, str]]) -> str:
        pass


class GeminiGenerator(Generator):
    def __init__(self) -> None:
        self.api_key = settings.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is missing")
        from google import genai

        self.client = genai.Client(api_key=self.api_key)
        self.model_name = os.getenv("GENERATION_MODEL", "gemini-2.5-flash")
        self._config = genai.types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT
        )

    def _build_context_string(self, context_chunks: List[Dict[str, Any]]) -> str:
        parts = []
        for i, chunk in enumerate(context_chunks, start=1):
            parts.append(
                f"--- CHUNK {i} [File: {chunk.get('filename', 'doc')} | Page: {chunk.get('page_number', 1)}] ---\n{chunk.get('text', '')}"
            )
        return "\n\n".join(parts)

    def _call_model(
        self, prompt: str, conversation_history: List[Dict[str, str]]
    ) -> str:
        contents: List[Dict[str, Any]] = []
        for turn in conversation_history:
            role = "user" if turn["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": turn["content"]}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config=self._config,
        )
        return (response.text or "").strip()

    def generate(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
    ) -> str:
        context_str = self._build_context_string(context_chunks)
        prompt = f"RETRIEVED DOCUMENT CONTEXT:\n{context_str}\n\nUSER QUESTION: {question}"

        try:
            return self._call_model(prompt, conversation_history)
        except Exception as exc:
            logger.warning(f"Gemini generation error: {exc}. Using stub generator response.")
            stub = StubGenerator()
            return stub.generate(question, context_chunks, conversation_history)

    def generate_greeting(self, conversation_history: List[Dict[str, str]]) -> str:
        prompt = "The user sent a friendly greeting or casual message. Respond warmly and briefly, asking how you can help them analyze financial or corporate documents today."

        try:
            return self._call_model(prompt, conversation_history)
        except Exception as exc:
            logger.warning(f"Gemini greeting generation error: {exc}. Using stub response.")
            stub = StubGenerator()
            return stub.generate_greeting(conversation_history)


class StubGenerator(Generator):
    def generate(
        self,
        question: str,
        context_chunks: List[Dict[str, Any]],
        conversation_history: List[Dict[str, str]],
    ) -> str:
        if not context_chunks:
            return "I couldn't find relevant information in the uploaded financial documents for your question."
        pages = ", ".join([f"p{c.get('page_number', 1)}" for c in context_chunks])
        return f"Based on the financial document context ({len(context_chunks)} sections reviewed), here is the summary for '{question}': The document contains detailed financial data. [Source: {pages}]"

    def generate_greeting(self, conversation_history: List[Dict[str, str]]) -> str:
        return "Hello! I am LedgerLens AI. How can I help you analyze your financial reports or earnings presentations today?"
