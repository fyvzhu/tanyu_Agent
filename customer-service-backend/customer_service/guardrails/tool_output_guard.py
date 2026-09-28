from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel

from .prompt_injection import InjectionDecision, PromptInjectionDetector


class ToolOutputGuard:
    """
    Guard for tool outputs to prevent indirect prompt injection.
    
    Tool outputs are UNTRUSTED DATA and must be sanitized before
    being passed to the LLM.
    """
    
    def __init__(self):
        self.detector = PromptInjectionDetector()
    
    def scan_tool_output(
        self,
        output: Any,
        tool_name: str,
        **kwargs: Any
    ) -> tuple[Any, InjectionDecision]:
        """
        Scan tool output for indirect injection and sanitize if needed.
        
        Args:
            output: Tool output (dict, list, str, etc.)
            tool_name: Name of the tool that produced this output
            
        Returns:
            (sanitized_output, injection_decision)
        """
        if output is None:
            return output, InjectionDecision(action="allow")
        
        # Handle different output types
        if isinstance(output, str):
            return self._scan_string(output, tool_name)
        elif isinstance(output, dict):
            return self._scan_dict(output, tool_name)
        elif isinstance(output, list):
            return self._scan_list(output, tool_name)
        else:
            # Primitive types are safe
            return output, InjectionDecision(action="allow")
    
    def _scan_string(self, text: str, source: str) -> tuple[str, InjectionDecision]:
        """Scan and sanitize string content."""
        # Detect injection
        decision = self.detector.detect_indirect_injection(text, source=source)
        
        if decision.action == "sanitize":
            # Clean HTML script/style tags
            cleaned = self._clean_html(text)
            # Remove control sequences
            cleaned = self._remove_control_sequences(cleaned)
            return cleaned, decision
        
        return text, decision
    
    def _scan_dict(self, data: dict, source: str) -> tuple[dict, InjectionDecision]:
        """Recursively scan dictionary values."""
        sanitized = {}
        max_risk = "low"
        max_score = 0.0
        
        for key, value in data.items():
            if isinstance(value, str):
                cleaned_value, decision = self._scan_string(value, f"{source}.{key}")
                sanitized[key] = cleaned_value
                if decision.score > max_score:
                    max_score = decision.score
                    max_risk = decision.risk
            elif isinstance(value, dict):
                cleaned_value, decision = self._scan_dict(value, f"{source}.{key}")
                sanitized[key] = cleaned_value
                if decision.score > max_score:
                    max_score = decision.score
                    max_risk = decision.risk
            elif isinstance(value, list):
                cleaned_value, decision = self._scan_list(value, f"{source}.{key}")
                sanitized[key] = cleaned_value
                if decision.score > max_score:
                    max_score = decision.score
                    max_risk = decision.risk
            else:
                sanitized[key] = value
        
        final_decision = InjectionDecision(
            risk=max_risk,
            score=max_score,
            action="allow" if max_score < 0.6 else "sanitize"
        )
        
        return sanitized, final_decision
    
    def _scan_list(self, items: list, source: str) -> tuple[list, InjectionDecision]:
        """Recursively scan list items."""
        sanitized = []
        max_risk = "low"
        max_score = 0.0
        
        for i, item in enumerate(items):
            if isinstance(item, str):
                cleaned_item, decision = self._scan_string(item, f"{source}[{i}]")
                sanitized.append(cleaned_item)
                if decision.score > max_score:
                    max_score = decision.score
                    max_risk = decision.risk
            elif isinstance(item, dict):
                cleaned_item, decision = self._scan_dict(item, f"{source}[{i}]")
                sanitized.append(cleaned_item)
                if decision.score > max_score:
                    max_score = decision.score
                    max_risk = decision.risk
            elif isinstance(item, list):
                cleaned_item, decision = self._scan_list(item, f"{source}[{i}]")
                sanitized.append(cleaned_item)
                if decision.score > max_score:
                    max_score = decision.score
                    max_risk = decision.risk
            else:
                sanitized.append(item)
        
        final_decision = InjectionDecision(
            risk=max_risk,
            score=max_score,
            action="allow" if max_score < 0.6 else "sanitize"
        )
        
        return sanitized, final_decision
    
    def _clean_html(self, text: str) -> str:
        """Remove potentially dangerous HTML tags."""
        # Remove script tags and content
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Remove style tags and content
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Remove event handlers
        text = re.sub(r'\s+on\w+\s*=\s*["\'][^"\']*["\']', "", text, flags=re.IGNORECASE)
        # Remove javascript: links
        text = re.sub(r'javascript:', "", text, flags=re.IGNORECASE)
        return text
    
    def _remove_control_sequences(self, text: str) -> str:
        """Remove control sequences that might manipulate LLM behavior."""
        # Remove LLM-specific tags
        text = re.sub(r"<\|.*?\|>", "", text)
        text = re.sub(r"\[INST\]|\[/INST\]", "", text)
        # Remove excessive whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()
    
    def mark_as_untrusted(self, data: Any, source: str) -> dict:
        """
        Wrap tool output with metadata marking it as untrusted data.
        
        This can be used in prompt construction to explicitly tell the LLM
        that this content should not be treated as instructions.
        """
        return {
            "_source": source,
            "_trust_level": "UNTRUSTED",
            "_type": "external_data",
            "content": data
        }
