"""
检索安全防护 - 防止注入攻击和恶意内容
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


class RetrievalGuard:
    """防止检索内容中的注入攻击和恶意指令"""
    
    # 可疑注入模式（中英文）
    INJECTION_PATTERNS = [
        r"忽略.*规则",
        r"忽略.*指令",
        r"ignore.*rules",
        r"ignore.*instructions",
        r"调用.*工具",
        r"call.*tool",
        r"系统提示",
        r"system\s+prompt",
        r"你是.*助手",
        r"you\s+are\s+.*assistant",
        r"执行.*命令",
        r"execute.*command",
        r"重置.*",
        r"reset.*",
        r"删除.*数据",
        r"delete.*data",
    ]
    
    # 敏感信息模式
    SENSITIVE_PATTERNS = [
        r"\b\d{15,19}\b",  # 可能的银行卡号
        r"\b\d{17,18}[Xx\d]\b",  # 可能的身份证号
        r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b",  # 邮箱
    ]
    
    def __init__(self, strict_mode: bool = False):
        """
        Args:
            strict_mode: 严格模式，检测到注入时抛出异常而非仅警告
        """
        self.strict_mode = strict_mode
        self._compiled_injection = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.INJECTION_PATTERNS
        ]
        self._compiled_sensitive = [
            re.compile(pattern, re.IGNORECASE) for pattern in self.SENSITIVE_PATTERNS
        ]
    
    def sanitize_chunk_text(self, text: str, chunk_id: str = "") -> str:
        """
        清理 chunk 文本中的潜在注入
        
        Args:
            text: 原始文本
            chunk_id: chunk 标识（用于日志）
            
        Returns:
            清理后的文本
            
        Raises:
            ValueError: 严格模式下检测到注入时抛出
        """
        # 检测注入模式
        for pattern in self._compiled_injection:
            if pattern.search(text):
                logger.warning(
                    f"⚠️  Suspicious injection pattern detected in chunk {chunk_id}: "
                    f"'{pattern.pattern}'"
                )
                if self.strict_mode:
                    raise ValueError(f"Injection pattern detected: {pattern.pattern}")
        
        # 检测敏感信息（仅记录，不修改）
        for pattern in self._compiled_sensitive:
            if pattern.search(text):
                logger.warning(
                    f"⚠️  Sensitive information detected in chunk {chunk_id}"
                )
        
        return text
    
    def sanitize_query(self, query: str) -> str:
        """
        清理用户查询中的特殊字符和注入尝试
        
        Args:
            query: 原始查询
            
        Returns:
            清理后的查询
        """
        # 移除可能导致注入的特殊字符
        sanitized = query
        
        # 限制长度
        max_length = 500
        if len(sanitized) > max_length:
            logger.warning(f"Query too long ({len(sanitized)}), truncating to {max_length}")
            sanitized = sanitized[:max_length]
        
        # 移除控制字符
        sanitized = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", sanitized)
        
        return sanitized
    
    def validate_retrieval_results(
        self,
        results: list[dict],
        max_results: int = 100
    ) -> list[dict]:
        """
        验证检索结果的安全性
        
        Args:
            results: 检索结果列表
            max_results: 最大结果数量
            
        Returns:
            验证后的结果列表
        """
        # 限制结果数量，防止 DoS
        if len(results) > max_results:
            logger.warning(
                f"Too many retrieval results ({len(results)}), "
                f"truncating to {max_results}"
            )
            results = results[:max_results]
        
        # 验证每个结果
        validated = []
        for result in results:
            try:
                # 确保必要字段存在
                if "product_id" not in result:
                    logger.warning("Result missing product_id, skipping")
                    continue
                
                # 清理文本字段
                if "text" in result:
                    result["text"] = self.sanitize_chunk_text(
                        result["text"],
                        chunk_id=result.get("chunk_id", "")
                    )
                
                validated.append(result)
                
            except Exception as e:
                logger.error(f"Failed to validate result: {e}")
                continue
        
        return validated
    
    def check_rate_limit(self, user_id: str, max_requests: int = 100) -> bool:
        """
        简单的速率限制检查（实际应使用 Redis）
        
        Args:
            user_id: 用户 ID
            max_requests: 最大请求数
            
        Returns:
            是否允许请求
        """
        # 这里只是占位符，实际实现需要 Redis
        # 未来可以集成 Redis 计数器或滑动窗口算法
        return True
