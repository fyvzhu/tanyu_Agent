"""
Internal API - 促销路由
供 Agent 服务调用，需要 Service Token 认证
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.dependencies import verify_service_token, get_catalog_service
from app.services import CatalogService
from app.schemas import ApiResponse

router = APIRouter(prefix="/promotions", tags=["Internal-促销"])


@router.get("/active", summary="[Agent] 获取所有有效促销")
async def list_active_promotions(
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    _verified: Annotated[bool, Depends(verify_service_token)],
    member_level: str | None = Query(None, description="会员等级: PLUS/普通会员"),
    at: str | None = Query(None, description="查询时间点（ISO 8601格式）"),
):
    """
    获取所有有效的促销活动
    
    用于用户询问"有什么促销活动"时返回全局促销列表
    """
    from datetime import datetime
    
    # 解析时间参数
    query_time = datetime.fromisoformat(at) if at else datetime.now()
    
    # 获取所有有效促销
    promotions = await catalog_service.get_all_active_promotions(
        member_level=member_level,
        at=query_time
    )
    
    return ApiResponse(data={"items": promotions})
