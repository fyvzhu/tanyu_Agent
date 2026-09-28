from __future__ import annotations

import re
import unicodedata

from pydantic import BaseModel


class GuardDecision(BaseModel):
    risk: str = "low"
    score: float = 0.0
    action: str = "allow"
    reason: str | None = None
    sanitized_text: str


INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"忽略(以上|之前|前面).{0,12}(指令|规则|提示)",
    r"输出.*系统提示",
    r"reveal.*system prompt",
]


def inspect_input(text: str) -> GuardDecision:
    normalized = unicodedata.normalize("NFKC", text).replace("\u200b", "").strip()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return GuardDecision(
                risk="high",
                score=0.95,
                action="block",
                reason="prompt_injection",
                sanitized_text=normalized,
            )
    return GuardDecision(sanitized_text=normalized)
