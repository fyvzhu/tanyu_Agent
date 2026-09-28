from __future__ import annotations

import random
from typing import Literal


class FallbackResponse:
    """
    Deterministic fallback responses for various guard failures.
    
    These responses are safe, do not leak system information,
    and guide the user back to legitimate use cases.
    """
    
    # Generic safe responses when attack is detected
    ATTACK_DETECTED = [
        "抱歉，我无法处理这个请求。请问有什么我可以帮您的吗？",
        "您的问题似乎有些不清楚，能否换个方式描述呢？",
        "我暂时无法理解这个请求，请问您需要查询订单还是商品信息？",
    ]
    
    # When indirect injection is found in external content
    UNTRUSTED_CONTENT = [
        "抱歉，我无法确认相关信息的准确性，请稍后再试。",
        "系统暂时无法获取完整信息，建议您稍后重试。",
    ]
    
    # When tool access is denied
    UNAUTHORIZED_ACTION = [
        "抱歉，我无法执行这个操作。如需帮助请联系客服。",
        "这个操作暂时无法完成，请问还有什么我可以帮您的吗？",
    ]
    
    # When missing confirmation for side-effect operations
    CONFIRMATION_NEEDED = [
        "请确认您是否要执行这个操作？",
        "这是一个重要操作，请再次确认。",
    ]
    
    # When hallucination is detected
    UNGROUNDED_RESPONSE = [
        "抱歉，我无法确认这些信息的准确性。建议您联系人工客服获取准确答复。",
        "我暂时不能确认这些信息的来源，请稍后再试。",
    ]
    
    # When PII leakage is prevented
    PII_REDACTED = [
        "为保护您的隐私，部分敏感信息已被隐藏。",
    ]
    
    @classmethod
    def get_response(
        cls,
        reason: Literal[
            "attack_detected",
            "untrusted_content", 
            "unauthorized_action",
            "confirmation_needed",
            "ungrounded_response",
            "pii_redacted"
        ],
        custom_message: str | None = None,
        randomize: bool = True
    ) -> str:
        """
        Get an appropriate fallback response.
        
        Args:
            reason: The reason for the fallback
            custom_message: Optional custom message to use instead
            randomize: Whether to randomize selection (for more natural feel)
            
        Returns:
            Safe fallback response string
        """
        if custom_message:
            return custom_message
        
        response_pool = {
            "attack_detected": cls.ATTACK_DETECTED,
            "untrusted_content": cls.UNTRUSTED_CONTENT,
            "unauthorized_action": cls.UNAUTHORIZED_ACTION,
            "confirmation_needed": cls.CONFIRMATION_NEEDED,
            "ungrounded_response": cls.UNGROUNDED_RESPONSE,
            "pii_redacted": cls.PII_REDACTED,
        }
        
        pool = response_pool.get(reason, cls.ATTACK_DETECTED)
        
        if randomize:
            return random.choice(pool)
        else:
            return pool[0]
    
    @classmethod
    def get_clarification_prompt(cls, intent: str | None = None) -> str:
        """
        Get a clarification prompt to guide user back to legitimate use.
        
        Args:
            intent: Current detected intent to provide specific guidance
            
        Returns:
            Clarification prompt
        """
        if intent == "logistics_query":
            return "您是想查询物流状态吗？请提供订单号，我来帮您查询。"
        elif intent == "product_query":
            return "您是在找什么商品？请告诉我商品名称或品类，我来帮您搜索。"
        elif intent == "return":
            return "您是要申请退货退款吗？请提供订单号、商品和原因，我来帮您处理。"
        elif intent == "exchange":
            return "您是要换颜色或尺码吗？请提供订单号、原 SKU 和目标 SKU。"
        elif intent == "size_recommend":
            return "您是想咨询尺码吗？请先选择商品，并补充身高体重等信息。"
        else:
            return "我可以帮您搜索商品、推荐尺码、查询优惠、查物流、办理退货退款或换货。请问您需要什么帮助？"
    
    @classmethod
    def format_with_guidance(cls, base_response: str, intent: str | None = None) -> str:
        """
        Format a fallback response with helpful guidance.
        
        Args:
            base_response: Base fallback message
            intent: Current intent for context-specific guidance
            
        Returns:
            Formatted response with guidance
        """
        clarification = cls.get_clarification_prompt(intent)
        return f"{base_response}\n\n{clarification}"


def get_safe_error_message(error_type: str = "general") -> str:
    """
    Get a safe error message that doesn't leak system internals.
    
    Args:
        error_type: Type of error (general, database, api, timeout, etc.)
        
    Returns:
        User-facing error message
    """
    messages = {
        "general": "系统暂时出现问题，请稍后重试。",
        "database": "数据查询遇到问题，请稍后重试。",
        "api": "服务暂时不可用，请稍后重试。",
        "timeout": "请求超时，请稍后重试。",
        "not_found": "未找到相关信息。",
        "permission": "您没有权限执行此操作。",
    }
    return messages.get(error_type, messages["general"])
