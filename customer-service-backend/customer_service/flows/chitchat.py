"""
闲聊 Flow - 处理非业务对话
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from customer_service.graph.state import AgentState


class ChitchatFlow:
    """
    闲聊 Flow
    
    职责：
    1. 识别闲聊类型（问候、感谢、闲聊）
    2. 提供必要的上下文给 LLM 生成友好回复
    3. 不涉及任何业务逻辑
    """
    
    intent_name = "chitchat"
    
    async def execute(self, state: AgentState) -> dict[str, Any]:
        """
        执行闲聊逻辑
        
        Args:
            state: Agent 状态
            
        Returns:
            {
                "chitchat_type": "greeting" | "thanks" | "small_talk" | "goodbye",
                "sentiment": "positive" | "neutral" | "negative" | None,
            }
        """
        user_query = state.get("current_message", "")
        session_id = state.get("session_id", "unknown")
        
        logger.info(f"[{session_id}] 💬 ChitchatFlow: {user_query}")
        
        try:
            # 1. 识别闲聊类型
            chitchat_type = self._classify_chitchat(user_query)
            logger.info(f"[{session_id}] Chitchat type: {chitchat_type}")
            
            # 2. 分析情感倾向
            sentiment = self._analyze_sentiment(user_query)
            
            return {
                "chitchat_type": chitchat_type,
                "sentiment": sentiment,
            }
            
        except Exception as e:
            logger.error(f"[{session_id}] ❌ ChitchatFlow error: {e}", exc_info=True)
            return {
                "chitchat_type": "small_talk",
                "sentiment": "neutral",
                "error": str(e),
            }
    
    def _classify_chitchat(self, user_query: str) -> str:
        """分类闲聊类型"""
        user_query_lower = user_query.lower()
        
        # 问候
        greeting_keywords = [
            "你好", "您好", "嗨", "hi", "hello", "早上好", "下午好", "晚上好",
            "在吗", "在不在"
        ]
        if any(keyword in user_query_lower for keyword in greeting_keywords):
            return "greeting"
        
        # 感谢
        thanks_keywords = [
            "谢谢", "感谢", "多谢", "thanks", "thank you", "thx",
            "太好了", "帮大忙了", "辛苦了"
        ]
        if any(keyword in user_query_lower for keyword in thanks_keywords):
            return "thanks"
        
        # 告别
        goodbye_keywords = [
            "再见", "拜拜", "bye", "goodbye", "下次见", "先走了",
            "不打扰了", "就这样吧"
        ]
        if any(keyword in user_query_lower for keyword in goodbye_keywords):
            return "goodbye"
        
        # 默认为闲聊
        return "small_talk"
    
    def _analyze_sentiment(self, user_query: str) -> str:
        """简单的情感分析"""
        positive_keywords = [
            "好", "不错", "很棒", "喜欢", "满意", "开心", "高兴",
            "优秀", "赞", "厉害", "完美", "太好了"
        ]
        
        negative_keywords = [
            "不好", "差", "糟糕", "失望", "不满", "生气", "烦",
            "垃圾", "坑", "难用", "糟心", "不爽"
        ]
        
        user_query_lower = user_query.lower()
        
        if any(keyword in user_query_lower for keyword in positive_keywords):
            return "positive"
        
        if any(keyword in user_query_lower for keyword in negative_keywords):
            return "negative"
        
        return "neutral"
