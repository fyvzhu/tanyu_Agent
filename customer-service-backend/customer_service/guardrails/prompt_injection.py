from __future__ import annotations

import re
import unicodedata
from typing import Literal

from pydantic import BaseModel


class InjectionDecision(BaseModel):
    """Prompt injection detection result."""
    risk: Literal["low", "medium", "high"] = "low"
    score: float = 0.0
    attack_type: str | None = None
    action: Literal["allow", "sanitize", "clarify", "block"] = "allow"
    reason: str | None = None


class PromptInjectionDetector:
    """Detect direct and indirect prompt injection attacks."""
    
    # Direct injection patterns
    DIRECT_PATTERNS = [
        (r"ignore\s+(all\s+)?previous\s+(instructions|rules)", "direct_ignore", 0.9),
        (r"忽略(以上|之前|前面).{0,12}(指令|规则|提示|约束)", "direct_ignore", 0.9),
        (r"(forget|disregard).{0,20}(instructions|rules|constraints)", "direct_forget", 0.85),
        (r"you\s+are\s+now\s+(a|an)\s+\w+", "role_override", 0.8),
        (r"你现在(是|扮演|充当).{0,20}(角色|助手|专家)", "role_override", 0.8),
        (r"system\s*:?\s*ignore", "system_override", 0.95),
        (r"repeat\s+(your|the)\s+(instructions|prompt|system)", "prompt_leakage", 0.9),
        (r"输出.*系统提示", "prompt_leakage", 0.9),
        (r"reveal.{0,15}(system\s+)?prompt", "prompt_leakage", 0.9),
    ]
    
    # Indirect injection markers (from external content)
    INDIRECT_PATTERNS = [
        (r"\[INST\]|\[/INST\]", "instruction_tag", 0.7),
        (r"<\|system\|>|<\|assistant\|>|<\|user\|>", "llm_tag", 0.8),
        (r"###\s*(instruction|system|assistant)", "markdown_instruction", 0.7),
        (r"(tell|ask|inform).{0,30}(user|customer).{0,30}(phone|email|password|credit)", "exfiltration", 0.95),
        (r"(发送|传递|告诉).{0,20}(手机号|邮箱|密码|银行卡)", "exfiltration", 0.95),
        (r"```[\s\S]{0,200}(os\.system|subprocess|rm\s+-rf|del\s+/[sq])", "dangerous_code_block", 0.8),
    ]
    
    # Zero-width and invisible characters
    INVISIBLE_CHARS = [
        "\u200b",  # zero-width space
        "\u200c",  # zero-width non-joiner
        "\u200d",  # zero-width joiner
        "\u2060",  # word joiner
        "\ufeff",  # zero-width no-break space
    ]
    
    def __init__(self):
        self.direct_re = [(re.compile(p, re.IGNORECASE), label, score) 
                          for p, label, score in self.DIRECT_PATTERNS]
        self.indirect_re = [(re.compile(p, re.IGNORECASE), label, score)
                           for p, label, score in self.INDIRECT_PATTERNS]
    
    def normalize_text(self, text: str) -> str:
        """Normalize and clean input text."""
        # Unicode normalization
        text = unicodedata.normalize("NFKC", text)
        
        # Remove invisible characters
        for char in self.INVISIBLE_CHARS:
            text = text.replace(char, "")
        
        return text.strip()
    
    def detect_direct_injection(self, text: str) -> InjectionDecision:
        """
        Detect direct prompt injection in user input.
        
        Returns decision with risk level and recommended action.
        """
        normalized = self.normalize_text(text)
        
        # Check for excessive length
        if len(normalized) > 10000:
            return InjectionDecision(
                risk="medium",
                score=0.6,
                attack_type="excessive_length",
                action="sanitize",
                reason="Input exceeds safe length limit"
            )
        
        # Check for unusual repetition
        if self._detect_repetition(normalized):
            return InjectionDecision(
                risk="medium",
                score=0.65,
                attack_type="repetition_attack",
                action="sanitize",
                reason="Detected unusual repetitive pattern"
            )
        
        # Pattern matching
        max_score = 0.0
        matched_type = None
        
        for pattern, label, score in self.direct_re:
            if pattern.search(normalized):
                if score > max_score:
                    max_score = score
                    matched_type = label
        
        if max_score >= 0.9:
            return InjectionDecision(
                risk="high",
                score=max_score,
                attack_type=matched_type,
                action="block",
                reason=f"High-confidence injection attack: {matched_type}"
            )
        elif max_score >= 0.7:
            return InjectionDecision(
                risk="medium",
                score=max_score,
                attack_type=matched_type,
                action="clarify",
                reason=f"Possible injection pattern: {matched_type}"
            )
        
        return InjectionDecision(action="allow")
    
    def detect_indirect_injection(self, text: str, source: str = "unknown") -> InjectionDecision:
        """
        Detect indirect prompt injection in external content (tool output, RAG, etc).
        
        Args:
            text: Content from external source
            source: Source identifier (e.g., "product_detail", "knowledge_base")
        """
        normalized = self.normalize_text(text)
        
        max_score = 0.0
        matched_type = None
        
        for pattern, label, score in self.indirect_re:
            if pattern.search(normalized):
                if score > max_score:
                    max_score = score
                    matched_type = label
        
        if max_score >= 0.8:
            return InjectionDecision(
                risk="high",
                score=max_score,
                attack_type=f"indirect_{matched_type}",
                action="sanitize",
                reason=f"Indirect injection from {source}: {matched_type}"
            )
        elif max_score >= 0.6:
            return InjectionDecision(
                risk="medium",
                score=max_score,
                attack_type=f"indirect_{matched_type}",
                action="sanitize",
                reason=f"Suspicious content from {source}"
            )
        
        return InjectionDecision(action="allow")
    
    def _detect_repetition(self, text: str, threshold: int = 50) -> bool:
        """Detect unusual repetitive patterns."""
        if len(text) < 100:
            return False
        
        # Check for repeated phrases
        words = text.split()
        if len(words) > 20:
            # Count most frequent 3-gram
            trigrams = [" ".join(words[i:i+3]) for i in range(len(words)-2)]
            if trigrams:
                max_count = max((trigrams.count(t) for t in set(trigrams)), default=0)
                if max_count > threshold:
                    return True
        
        return False
