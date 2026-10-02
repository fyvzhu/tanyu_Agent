"""
对话历史构建器

参考 ecommerce-customer-service 的 HistoryBuilder 实现
用于将对话历史格式化为 LLM prompt 的一部分

核心职责：
1. 将 ChatMessage 列表序列化为可读的对话历史字符串
2. 支持限制历史轮数（例如最近10轮）
3. 用于意图识别时提供上下文
"""
from __future__ import annotations

from typing import Any


class HistoryBuilder:
    """
    对话历史构建器
    
    将数据库中的 ChatMessage 记录转换为结构化的对话历史字符串
    用于 LLM 意图识别和上下文理解
    """
    
    @staticmethod
    def build_from_messages(messages: list[dict[str, Any]], max_turns: int = 10) -> str:
        """
        从 ChatMessage 列表构建对话历史字符串
        
        Args:
            messages: ChatMessage 字典列表，必须包含 role 和 content 字段
            max_turns: 最多保留的轮数（默认10轮，即最近5个用户消息+5个助手响应）
        
        Returns:
            格式化的对话历史字符串，例如：
            USER: 我想查询订单信息
            ASSISTANT: 好的，请提供您的订单编号
            USER: 12345
            ASSISTANT: ...
        """
        if not messages:
            return ""
        
        # 只取最近的 max_turns 条消息
        recent_messages = messages[-max_turns:] if len(messages) > max_turns else messages
        
        history_lines = []
        for msg in recent_messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # 格式化角色名称
            role_name = "USER" if role == "user" else "ASSISTANT"
            
            # 清理内容（去除多余空白）
            clean_content = content.strip()
            
            if clean_content:
                history_lines.append(f"{role_name}: {clean_content}")
        
        return "\n".join(history_lines)
    
    @staticmethod
    def build_from_db_models(messages: list[Any], max_turns: int = 10) -> str:
        """
        从 SQLAlchemy 模型列表构建对话历史
        
        Args:
            messages: ChatMessage 模型实例列表
            max_turns: 最多保留的轮数
        
        Returns:
            格式化的对话历史字符串
        """
        # 转换为字典格式
        message_dicts = []
        for msg in messages:
            message_dicts.append({
                "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                "content": msg.content,
                "created_at": msg.created_at,
            })
        
        return HistoryBuilder.build_from_messages(message_dicts, max_turns)
    
    @staticmethod
    def build_context_for_intent_classification(
        current_message: str,
        history_messages: list[dict[str, Any]],
        max_history_turns: int = 10
    ) -> dict[str, str]:
        """
        构建用于意图识别的上下文
        
        Args:
            current_message: 当前用户消息
            history_messages: 历史消息列表
            max_history_turns: 最多保留的历史轮数
        
        Returns:
            包含 user_message 和 conversation_history 的字典
        """
        history = HistoryBuilder.build_from_messages(history_messages, max_history_turns)
        
        return {
            "user_message": current_message.strip(),
            "conversation_history": history if history else "(无历史对话)",
        }
