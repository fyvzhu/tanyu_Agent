"""
Intent Flow 注册表

P0-11 修复：
- 删除重复的 IntentFlow Protocol 定义
- 统一使用 flows/models.py 中的正式定义
"""
from __future__ import annotations

from loguru import logger

# 导入统一的 IntentFlow Protocol
from customer_service.flows.models import IntentFlow


class IntentFlowRegistry:
    """Intent Flow 注册表 - 管理所有 Intent Flow 的注册和获取"""
    
    _flows: dict[str, IntentFlow] = {}
    
    @classmethod
    def register(cls, flow: IntentFlow) -> None:
        """
        注册 Flow
        
        Args:
            flow: 要注册的 Flow 实例
        """
        cls._flows[flow.intent_name] = flow
        logger.info(f"✅ Registered flow: {flow.intent_name}")
    
    @classmethod
    def get(cls, intent_name: str) -> IntentFlow | None:
        """
        获取 Flow
        
        Args:
            intent_name: Intent 名称
            
        Returns:
            对应的 Flow 实例，如果未注册则返回 None
        """
        return cls._flows.get(intent_name)
    
    @classmethod
    def list_all(cls) -> list[str]:
        """
        列出所有已注册的 Flow
        
        Returns:
            所有已注册的 Intent 名称列表
        """
        return list(cls._flows.keys())
    
    @classmethod
    def is_registered(cls, intent_name: str) -> bool:
        """
        检查 Intent 是否已注册
        
        Args:
            intent_name: Intent 名称
            
        Returns:
            是否已注册
        """
        return intent_name in cls._flows
