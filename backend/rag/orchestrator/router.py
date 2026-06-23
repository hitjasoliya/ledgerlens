from __future__ import annotations

import re


class QueryRouter:
    """Classifies user queries to route them to the correct generation path."""

    def is_greeting(self, query: str) -> bool:
        q = query.strip().lower().rstrip("?.!")

        common_phrases = {
            "hi", "hello", "hey", "hola", "greetings", "good morning",
            "good afternoon", "good evening", "howdy", "yo", "sup",
            "how are you", "hows it going", "how are you doing", "whats up",
            "hi there", "hello there", "hey there", "thanks", "thank you",
            "thank you so much", "perfect", "awesome", "great", "ok", "okay",
            "bye", "goodbye", "good day"
        }

        if q in common_phrases:
            return True

        greeting_patterns = [
            r"^(hi|hello|hey|greetings|good\s+morning|good\s+afternoon|good\s+evening|howdy|yo)(\s+(there|buddy|friend|team|all))?$",
            r"^how\s+are\s+you(\s+doing)?$",
            r"^hows\s+it\s+going$",
            r"^whats\s+up$",
            r"^thank\s+you(\s+so\s+much)?$",
            r"^thanks(\s+a\s+lot)?$",
        ]

        for pattern in greeting_patterns:
            if re.match(pattern, q):
                return True

        return False
