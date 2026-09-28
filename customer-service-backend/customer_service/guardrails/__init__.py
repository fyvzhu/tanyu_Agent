"""
Guardrails system for customer service agent.

This module implements a comprehensive security guardrail system following
the architecture described in the refactor guide:

1. Input Guard - Validates and sanitizes user input
2. Prompt Injection Detector - Detects direct and indirect injection attacks
3. Tool Output Guard - Sanitizes external/tool outputs before LLM processing
4. Action Guard - Validates tool executions for authorization and safety
5. Grounding Guard - Validates response grounding in evidence
6. Fallback Responses - Safe responses when attacks are detected

Usage:
    from customer_service.guardrails import (
        inspect_input,
        PromptInjectionDetector,
        ToolOutputGuard,
        ActionGuard,
        FallbackResponse,
    )
"""

from __future__ import annotations

from .action_guard import ActionDecision, ActionGuard
from .fallback import FallbackResponse, get_safe_error_message
from .grounding_guard import validate_grounding
from .input_guard import GuardDecision, inspect_input
from .pii import redact_pii
from .prompt_injection import InjectionDecision, PromptInjectionDetector
from .tool_output_guard import ToolOutputGuard

__all__ = [
    # Input validation
    "GuardDecision",
    "inspect_input",
    # Prompt injection detection
    "InjectionDecision",
    "PromptInjectionDetector",
    # Tool output validation
    "ToolOutputGuard",
    # Action/tool execution validation
    "ActionDecision",
    "ActionGuard",
    # Grounding validation
    "validate_grounding",
    # PII handling
    "redact_pii",
    # Fallback responses
    "FallbackResponse",
    "get_safe_error_message",
]
