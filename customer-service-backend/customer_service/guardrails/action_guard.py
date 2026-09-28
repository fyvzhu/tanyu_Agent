from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class ActionDecision(BaseModel):
    """Decision on whether to allow a tool action."""
    allowed: bool = True
    risk: Literal["low", "medium", "high"] = "low"
    reason: str | None = None
    requires_confirmation: bool = False


class ActionGuard:
    """
    Guard for tool execution to prevent unauthorized or malicious actions.
    
    Validates that:
    1. Tool belongs to current intent's allowed toolset
    2. Parameters come from trusted slots
    3. No cross-user access attempts
    4. Side-effect operations require confirmation
    """
    
    # Intent to allowed tools mapping
    INTENT_TOOLSETS = {
        "product_query": {"product_search_tool", "selling_point_tool"},
        "size_recommend": {"size_recommend_tool"},
        "urge_order_payment": set(),
        "promotion_query": {"promotion_query_tool"},
        "logistics_query": {"logistics_query_tool"},
        "return": {"return_request_tool"},
        "exchange": {"exchange_request_tool"},
        "chitchat": set(),
        "other": set(),
    }
    
    # Tools with side effects that need extra validation
    SIDE_EFFECT_TOOLS = {
        "return_request_tool",
        "exchange_request_tool",
    }
    
    # Tools that need user confirmation
    CONFIRMATION_REQUIRED: dict[str, str] = {}
    
    def validate_action(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        intent: str,
        user_id: str,
        trusted_params: set[str] | None = None,
        confirmed: bool = False
    ) -> ActionDecision:
        """
        Validate whether a tool action should be allowed.
        
        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
            intent: Current conversation intent
            user_id: Current authenticated user ID
            trusted_params: Set of parameter names that came from trusted sources
            confirmed: Whether user has confirmed this action
            
        Returns:
            ActionDecision with validation result
        """
        # Check 1: Tool belongs to intent's allowed toolset
        allowed_tools = self.INTENT_TOOLSETS.get(intent, set())
        if tool_name not in allowed_tools:
            return ActionDecision(
                allowed=False,
                risk="high",
                reason=f"Tool '{tool_name}' not allowed for intent '{intent}'"
            )
        
        # Check 2: No cross-user access
        if "user_id" in tool_args:
            if tool_args["user_id"] != user_id:
                return ActionDecision(
                    allowed=False,
                    risk="high",
                    reason="Attempt to access another user's data"
                )
        
        # Check 3: Side-effect operations validation
        if tool_name in self.SIDE_EFFECT_TOOLS:
            # Ensure critical params come from trusted sources
            critical_params = self._get_critical_params(tool_name)
            if trusted_params is None:
                trusted_params = set()
            
            untrusted = critical_params - trusted_params
            if untrusted:
                return ActionDecision(
                    allowed=False,
                    risk="high",
                    reason=f"Critical parameters not from trusted source: {untrusted}"
                )
            
            # Check if confirmation is required
            if tool_name in self.CONFIRMATION_REQUIRED and not confirmed:
                return ActionDecision(
                    allowed=False,
                    risk="medium",
                    reason=self.CONFIRMATION_REQUIRED[tool_name],
                    requires_confirmation=True
                )
        
        # Check 4: Parameter validation
        validation_result = self._validate_parameters(tool_name, tool_args)
        if not validation_result.allowed:
            return validation_result
        
        return ActionDecision(allowed=True, risk="low")
    
    def _get_critical_params(self, tool_name: str) -> set[str]:
        """Get critical parameters that must come from trusted sources."""
        critical_params_map = {
            "return_request_tool": {"order_id", "product_id", "sku_id", "reason"},
            "exchange_request_tool": {"order_id", "product_id", "original_sku_id", "exchange_sku_id", "reason"},
        }
        return critical_params_map.get(tool_name, set())
    
    def _validate_parameters(self, tool_name: str, tool_args: dict[str, Any]) -> ActionDecision:
        """Validate tool parameters for common attack patterns."""
        
        # Check for SQL injection patterns in string params
        for key, value in tool_args.items():
            if isinstance(value, str):
                if self._contains_sql_injection(value):
                    return ActionDecision(
                        allowed=False,
                        risk="high",
                        reason=f"Potential SQL injection in parameter '{key}'"
                    )
        
        # Check for path traversal in file-related params
        if any(k in tool_args for k in ["file_path", "path", "filename"]):
            for key in ["file_path", "path", "filename"]:
                if key in tool_args:
                    value = tool_args[key]
                    if isinstance(value, str) and self._contains_path_traversal(value):
                        return ActionDecision(
                            allowed=False,
                            risk="high",
                            reason=f"Potential path traversal in parameter '{key}'"
                        )
        
        return ActionDecision(allowed=True)
    
    def _contains_sql_injection(self, value: str) -> bool:
        """Basic SQL injection pattern detection."""
        dangerous_patterns = [
            r"'\s*(or|and)\s*'?\d*\s*'?\s*=\s*'?\d*",
            r";\s*drop\s+table",
            r";\s*delete\s+from",
            r"union\s+select",
            r"exec\s*\(",
            r"execute\s*\(",
        ]
        import re
        for pattern in dangerous_patterns:
            if re.search(pattern, value, re.IGNORECASE):
                return True
        return False
    
    def _contains_path_traversal(self, value: str) -> bool:
        """Path traversal pattern detection."""
        dangerous_patterns = [
            "..",
            "~",
            "/etc/",
            "\\windows\\",
            "%2e%2e",
        ]
        value_lower = value.lower()
        return any(p in value_lower for p in dangerous_patterns)
    
    def get_allowed_tools(self, intent: str) -> set[str]:
        """Get the set of allowed tools for a given intent."""
        return set(self.INTENT_TOOLSETS.get(intent, []))
    
    def is_side_effect_tool(self, tool_name: str) -> bool:
        """Check if a tool has side effects."""
        return tool_name in self.SIDE_EFFECT_TOOLS
