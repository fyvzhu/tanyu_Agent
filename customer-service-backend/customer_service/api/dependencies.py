"""
依赖注入 - Slice 01 Foundation

P0-19 修复：删除旧的 JWT 验证实现
现在统一使用 chat_dependencies.py 中的 AuthPrincipal
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_agent_service():
    """
    初始化 Agent 基础设施（Slice 01 Foundation）

    职责：
    - 初始化数据库引擎
    - 初始化 LangGraph
    - 构造共享的 ProductRetrievalService（P0-02/P0-03 修复）
    - 注册工具和 Flow

    不再创建 AgentService 实例 - Router 直接调用 Graph
    """

    # 初始化数据库引擎
    from customer_service.infrastructure.database import init_db_engine
    init_db_engine()
    logger.info("数据库引擎初始化完成")

    # 初始化 LangGraph
    from customer_service.graph.graph_manager import init_agent_graph
    init_agent_graph()
    logger.info("Agent Graph 初始化完成")

    # ===== P0-02/P0-03 修复：构造共享的 ProductRetrievalService =====
    from customer_service.config.config import get_settings
    from customer_service.retrieval.service import (
        ProductRetrievalService,
        HttpEmbeddingClient,
        QdrantProductRetriever,
        ElasticsearchProductRetriever,
    )

    settings = get_settings()

    # 根据配置初始化检索组件
    embedder = None
    if settings.embedding_enabled:
        embedder = HttpEmbeddingClient(base_url=settings.embedding_service_url)
        logger.info(f"✅ Embedding client initialized: {settings.embedding_service_url}")

    semantic_retriever = None
    if settings.qdrant_enabled:
        semantic_retriever = QdrantProductRetriever(
            url=settings.qdrant_url,
            collection_name=settings.qdrant_collection_name
        )
        logger.info(f"✅ Qdrant retriever initialized: {settings.qdrant_url}/{settings.qdrant_collection_name}")

    lexical_retriever = None
    if settings.elasticsearch_enabled:
        lexical_retriever = ElasticsearchProductRetriever(
            url=settings.elasticsearch_url,
            index_name=settings.elasticsearch_index_name
        )
        logger.info(f"✅ Elasticsearch retriever initialized: {settings.elasticsearch_url}/{settings.elasticsearch_index_name}")

    # 构造共享的 ProductRetrievalService（即使部分组件为 None 也可以降级）
    shared_retrieval_service = ProductRetrievalService(
        embedder=embedder,
        semantic=semantic_retriever,
        lexical=lexical_retriever,
    )
    logger.info("✅ 共享 ProductRetrievalService 构造完成")
    # ===== 修复结束 =====

    # 初始化工具注册表（Slice 02）- 注入共享的 retrieval service
    from customer_service.clients.ecommerce import get_ecommerce_client
    from customer_service.tools.registry import build_default_tool_registry, get_global_tool_registry

    ecommerce_client = get_ecommerce_client()
    tool_registry = build_default_tool_registry(ecommerce_client, retrieval=shared_retrieval_service)

    # 将工具复制到全局注册表
    global_registry = get_global_tool_registry()
    for tool_spec in tool_registry.list_tools():
        if tool_spec.name not in global_registry.names():
            global_registry.register(tool_spec)

    logger.info(f"✅ 工具注册完成，共 {len(tool_registry.list_tools())} 个工具（含共享 RAG）")

    # 注册 Slice 02 Intent Flows
    from customer_service.flows import (
        IntentFlowRegistry,
        ProductQueryFlow,
        PromotionQueryFlow,
        UrgeOrderPaymentFlow,
        ChitchatFlow,
    )

    IntentFlowRegistry.register(ProductQueryFlow())
    IntentFlowRegistry.register(PromotionQueryFlow())
    IntentFlowRegistry.register(UrgeOrderPaymentFlow())
    IntentFlowRegistry.register(ChitchatFlow())
    logger.info("Slice 02 Intent Flows 注册完成")

    logger.info("✅ Agent 基础设施初始化完成（Slice 01 Foundation）")


async def close_managed_clients() -> None:
    """清理资源（关闭 EcommerceClient、数据库连接和 Redis Checkpointer）"""
    from customer_service.clients.ecommerce import close_ecommerce_client
    from customer_service.infrastructure.database import close_db_engine
    from customer_service.graph.graph_manager import close_agent_graph

    await close_ecommerce_client()
    await close_db_engine()
    await close_agent_graph()
    logger.info("所有托管资源已关闭")
