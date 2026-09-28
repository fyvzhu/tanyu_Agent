from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import public_router, internal_router
from app.database import AsyncSessionLocal
from app.core.request_id import RequestIDMiddleware, get_request_id


openapi_tags = [
    {
        "name": "认证",
        "description": "登录、刷新、登出、当前用户接口",
    },
    {
        "name": "用户",
        "description": "用户资料、身体数据管理",
    },
    {
        "name": "商品目录",
        "description": "商品列表、搜索、详情查询",
    },
    {
        "name": "订单",
        "description": "订单查询、物流跟踪",
    },
    {
        "name": "售后",
        "description": "退货、换货、催发货服务",
    },
    {
        "name": "Internal-商品",
        "description": "[Agent 专用] 商品 SPU 真值查询",
    },
    {
        "name": "Internal-SKU",
        "description": "[Agent 专用] SKU 真值过滤",
    },
]


app = FastAPI(
    title="zhutou 电商业务服务",
    version="2.0.0",
    description="为 zhutou 客服项目提供完整的电商业务能力：用户认证、商品目录、订单管理、售后服务。",
    openapi_tags=openapi_tags,
)

# 挂载静态文件目录
app.mount("/static/main-images", StaticFiles(directory="../data/main_images"), name="main_images")
app.mount("/static/size-images", StaticFiles(directory="../data/size_images"), name="size_images")


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


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc: StarletteHTTPException):
    message = str(exc.detail)
    request_id = get_request_id(request)
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
    request_id = get_request_id(request)
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

# 添加 Request-ID 中间件
app.add_middleware(RequestIDMiddleware)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health/live", tags=["健康检查"])
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["健康检查"])
async def health_ready():
    """
    Readiness probe: check if service can handle requests

    检查项：
    - MySQL 数据库连接

    返回 503 如果关键依赖不可用
    """
    dependencies = {}
    overall_status = "ok"

    # 检查 MySQL
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        dependencies["mysql"] = "ok"
    except Exception as e:
        dependencies["mysql"] = "error"
        overall_status = "unavailable"

        return JSONResponse(
            status_code=503,
            content={
                "status": overall_status,
                "dependencies": dependencies,
            }
        )

    return {
        "status": overall_status,
        "dependencies": dependencies,
    }

# 注册 API 路由
app.include_router(public_router)    # Public API: /api/v1/...
app.include_router(internal_router)  # Internal API: /internal/v1/...
