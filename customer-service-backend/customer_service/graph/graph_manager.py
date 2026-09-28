"""
LangGraph 实例管理器
管理全局的 LangGraph 实例和 Redis Checkpointer
"""
from __future__ import annotations

from loguru import logger

from customer_service.graph.builder import build_agent_graph
from customer_service.infrastructure.checkpointer import RedisCheckpointer


# 全局 Graph 实例和 Checkpointer
_agent_graph = None
_checkpointer: RedisCheckpointer | None = None


def init_agent_graph():
    """
    初始化全局 Agent Graph（带 Redis Checkpointer）

    在应用启动时调用一次
    支持跨 Turn 状态持久化、Task pause/resume
    """
    global _agent_graph, _checkpointer

    if _agent_graph is None:
        logger.info("🔧 开始初始化 Agent Graph...")

        # 创建 Redis Checkpointer
        _checkpointer = RedisCheckpointer()
        logger.info("✅ Redis Checkpointer 创建完成")

        # 构建带 Checkpointer 的 Graph
        _agent_graph = build_agent_graph(checkpointer=_checkpointer)
        logger.info("✅ Agent Graph 初始化成功（五节点固定流程 + Redis 持久化）")

    return _agent_graph


def get_agent_graph():
    """
    获取全局 Agent Graph 实例

    Returns:
        编译后的 LangGraph 实例（带 Redis Checkpointer）

    Raises:
        RuntimeError: 如果 Graph 未初始化
    """
    if _agent_graph is None:
        raise RuntimeError(
            "Agent Graph 未初始化。请确保在应用启动时调用了 init_agent_graph()"
        )

    return _agent_graph


def get_checkpointer():
    """
    获取全局 Redis Checkpointer 实例

    Returns:
        RedisCheckpointer 实例

    Raises:
        RuntimeError: 如果 Checkpointer 未初始化
    """
    if _checkpointer is None:
        raise RuntimeError(
            "Redis Checkpointer 未初始化。请确保在应用启动时调用了 init_agent_graph()"
        )

    return _checkpointer


async def close_agent_graph():
    """
    关闭 Agent Graph 和 Checkpointer 资源

    在应用关闭时调用
    """
    global _checkpointer

    if _checkpointer:
        await _checkpointer.aclose()
        logger.info("✅ Redis Checkpointer 已关闭")
        _checkpointer = None
