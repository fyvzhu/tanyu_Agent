"""
FastAPI 应用 - 新架构：LangGraph Agent
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from customer_service.api.router.chat_router import router
from customer_service.api.dependencies import close_managed_clients, init_agent_service
from customer_service.api.middleware.request_id import RequestIDMiddleware
from customer_service.config.config import settings
from customer_service.infrastructure.http import init_http_client, close_http_client
import sys
from loguru import logger

# 配置 loguru 输出到 stdout（而不是 stderr），避免被 uvicorn 过滤
logger.remove()  # 移除默认的 handler
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG",  # 显示 DEBUG 级别的日志
    colorize=True,
)


def _error_code(status_code: int) -> str:
    return {
        400: "VALIDATION_ERROR",
        401: "AUTH_REQUIRED",
        403: "FORBIDDEN",
        404: "RESOURCE_NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        503: "UPSTREAM_UNAVAILABLE",
        504: "UPSTREAM_TIMEOUT",
    }.get(status_code, "INTERNAL_ERROR")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理：初始化和清理资源
    """
    # 启动时初始化
    init_http_client()
    init_agent_service()  # 初始化 Agent Service（包含 Graph、Tools、Flows）

    yield  # FastAPI 处理请求

    # 关闭时清理
    await close_managed_clients()
    await close_http_client()


app = FastAPI(
    title="探域电商售前 Agent",
    description="基于 LangGraph 的电商智能客服系统",
    lifespan=lifespan
)

# P1-50 修复：添加 Request-ID 中间件（必须在 CORS 之前）
app.add_middleware(RequestIDMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    message = str(exc.detail)
    # P1-50 修复：从 request.state 读取 request_id
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": _error_code(exc.status_code),
                "message": message,
                "safe_message": message,
                "details": {},
            },
            "request_id": request_id,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    # P1-50 修复：从 request.state 读取 request_id
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "request validation failed",
                "safe_message": "请求参数不正确",
                "details": {"errors": exc.errors()},
            },
            "request_id": request_id,
        },
    )

@app.get("/health/live")
async def health_live():
    """Liveness probe: service is running"""
    return {"status": "ok", "service": "customer-service-backend"}


@app.get("/health/ready")
async def health_ready():
    """
    P1-51 修复：完整的 Readiness 检查

    检查关键依赖（任一失败返回 503 unavailable）：
    - Agent Graph
    - Database
    - Redis
    - Commerce API
    - LLM

    检查可选依赖（失败降级为 degraded，但返回 200）：
    - Embedding 服务
    - Qdrant
    - Elasticsearch

    返回状态：
    - ok: 所有关键依赖可用，可选依赖全部可用
    - degraded: 关键依赖可用，但部分可选依赖不可用
    - unavailable: 至少一个关键依赖不可用（HTTP 503）
    """
    dependencies = {}
    overall_status = "ok"
    critical_failures = []
    optional_failures = []

    # ========== 关键依赖检查 ==========

    # 1. 检查 Agent Graph 是否初始化
    try:
        from customer_service.graph.graph_manager import get_agent_graph
        get_agent_graph()
        dependencies["agent_graph"] = "ok"
    except Exception as e:
        dependencies["agent_graph"] = f"error: {str(e)[:100]}"
        critical_failures.append("agent_graph")
        overall_status = "unavailable"

    # 2. 检查数据库连接（关键依赖）
    try:
        from customer_service.infrastructure.database import async_session, init_db_engine
        from sqlalchemy import text

        # 确保数据库引擎已初始化
        if async_session is None:
            init_db_engine()

        # 创建临时会话测试连接
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        dependencies["database"] = "ok"
    except Exception as e:
        dependencies["database"] = f"error: {str(e)[:100]}"
        critical_failures.append("database")
        overall_status = "unavailable"

    # 3. 检查 Redis（关键依赖）
    if settings.redis_enabled:
        try:
            from customer_service.api.chat_dependencies import get_redis
            redis = get_redis()
            await redis.ping()
            dependencies["redis"] = "ok"
        except Exception as e:
            dependencies["redis"] = f"error: {str(e)[:100]}"
            critical_failures.append("redis")
            overall_status = "unavailable"
    else:
        dependencies["redis"] = "disabled"

    # 4. 检查 Commerce API（关键依赖）
    try:
        from customer_service.clients.ecommerce import get_ecommerce_client
        import httpx

        client = get_ecommerce_client()
        # P1-51: 尝试访问 /health/ready，回退到 /health/live
        try:
            response = await client.http.get(f"{client.base_url}/health/ready", timeout=2.0)
        except httpx.HTTPStatusError:
            response = await client.http.get(f"{client.base_url}/health/live", timeout=2.0)

        if response.status_code == 200:
            dependencies["commerce"] = "ok"
        else:
            dependencies["commerce"] = f"http_{response.status_code}"
            critical_failures.append("commerce")
            overall_status = "unavailable"
    except Exception as e:
        dependencies["commerce"] = f"error: {str(e)[:100]}"
        critical_failures.append("commerce")
        overall_status = "unavailable"

    # 5. 检查 LLM 服务（关键依赖）
    try:
        from customer_service.infrastructure.llm import get_llm
        llm = get_llm()
        # 简单测试：生成一个 token
        await llm.ainvoke("test")
        dependencies["llm"] = "ok"
    except Exception as e:
        dependencies["llm"] = f"error: {str(e)[:100]}"
        critical_failures.append("llm")
        overall_status = "unavailable"

    # ========== 可选依赖检查（降级模式）==========

    # 6. 检查 Embedding 服务（可选）
    if settings.embedding_enabled:
        try:
            from customer_service.infrastructure.embedding import get_embedding_service
            embedding = get_embedding_service()
            # 测试 embedding 生成
            await embedding.embed("test")
            dependencies["embedding"] = "ok"
        except Exception as e:
            dependencies["embedding"] = f"degraded: {str(e)[:100]}"
            optional_failures.append("embedding")
            if overall_status == "ok":
                overall_status = "degraded"
    else:
        dependencies["embedding"] = "disabled"

    # 7. 检查 Qdrant（可选）
    if settings.qdrant_enabled:
        try:
            from qdrant_client import AsyncQdrantClient
            qdrant = AsyncQdrantClient(url=settings.qdrant_url, timeout=2.0)
            # 检查集合是否存在
            collections = await qdrant.get_collections()
            dependencies["qdrant"] = "ok"
            await qdrant.close()
        except Exception as e:
            dependencies["qdrant"] = f"degraded: {str(e)[:100]}"
            optional_failures.append("qdrant")
            if overall_status == "ok":
                overall_status = "degraded"
    else:
        dependencies["qdrant"] = "disabled"

    # 8. 检查 Elasticsearch（可选）
    if settings.elasticsearch_enabled:
        try:
            from elasticsearch import AsyncElasticsearch
            es = AsyncElasticsearch([settings.elasticsearch_url], request_timeout=2.0)
            # 检查集群健康
            health = await es.cluster.health()
            dependencies["elasticsearch"] = "ok"
            await es.close()
        except Exception as e:
            dependencies["elasticsearch"] = f"degraded: {str(e)[:100]}"
            optional_failures.append("elasticsearch")
            if overall_status == "ok":
                overall_status = "degraded"
    else:
        dependencies["elasticsearch"] = "disabled"

    # 返回状态码
    status_code = 503 if overall_status == "unavailable" else 200

    return JSONResponse(
        status_code=status_code,
        content={
            "status": overall_status,
            "dependencies": dependencies,
            "critical_failures": critical_failures if critical_failures else None,
            "optional_failures": optional_failures if optional_failures else None,
        }
    )


@app.get("/health")
async def health_check():
    """Compatibility alias for local smoke checks."""
    return await health_live()

# 注册路由
app.include_router(router)
