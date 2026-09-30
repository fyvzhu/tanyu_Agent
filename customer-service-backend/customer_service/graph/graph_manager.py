"""
LangGraph 实例管理器
管理全局的 LangGraph 实例和官方 AsyncRedisSaver
"""
from __future__ import annotations

from loguru import logger

from customer_service.graph.builder import build_agent_graph
from customer_service.config.config import settings


# 全局 Graph 实例和 Checkpointer
_agent_graph = None
_checkpointer = None
_checkpointer_cm = None  # Context manager for proper cleanup


async def init_agent_graph():
    """
    初始化全局 Agent Graph（使用官方 AsyncRedisSaver）

    在应用启动时调用一次
    支持跨 Turn 状态持久化、Task pause/resume

    使用 Redis 8.0+ 的 RedisJSON 和 RediSearch 模块
    """
    global _agent_graph, _checkpointer, _checkpointer_cm

    if _agent_graph is None:
        logger.info("🔧 开始初始化 Agent Graph...")

        # 导入官方 AsyncRedisSaver
        from langgraph.checkpoint.redis.aio import AsyncRedisSaver

        # 创建官方 AsyncRedisSaver
        # TTL单位是分钟，需要从秒转换
        ttl_minutes = settings.redis_checkpoint_ttl_seconds / 60

        # from_conn_string返回context manager，需要进入上下文
        _checkpointer_cm = AsyncRedisSaver.from_conn_string(
            settings.redis_url,
            ttl={
                "default_ttl": ttl_minutes,  # 默认TTL（分钟）
                "refresh_on_read": True,  # 读取时刷新TTL
            },
        )

        # 进入async context manager
        _checkpointer = await _checkpointer_cm.__aenter__()

        # 初始化索引（必须调用）
        await _checkpointer.asetup()
        logger.info(f"✅ AsyncRedisSaver 创建完成（TTL={ttl_minutes}分钟，refresh_on_read=True）")

        # 构建带 Checkpointer 的 Graph
        _agent_graph = build_agent_graph(checkpointer=_checkpointer)
        logger.info("✅ Agent Graph 初始化成功（五节点固定流程 + Redis 持久化）")

    return _agent_graph


def get_agent_graph():
    """
    获取全局 Agent Graph 实例

    Returns:
        编译后的 LangGraph 实例（带 AsyncRedisSaver）

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
    获取全局 AsyncRedisSaver 实例

    Returns:
        AsyncRedisSaver 实例

    Raises:
        RuntimeError: 如果 Checkpointer 未初始化
    """
    if _checkpointer is None:
        raise RuntimeError(
            "AsyncRedisSaver 未初始化。请确保在应用启动时调用了 init_agent_graph()"
        )

    return _checkpointer


async def close_agent_graph():
    """
    关闭 Agent Graph 和 Checkpointer 资源

    在应用关闭时调用
    """
    global _checkpointer, _checkpointer_cm

    if _checkpointer_cm:
        await _checkpointer_cm.__aexit__(None, None, None)
        logger.info("✅ AsyncRedisSaver 已关闭")
        _checkpointer = None
        _checkpointer_cm = None
