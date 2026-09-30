"""
Internal API - SKU 路由
供 Agent 服务调用，需要 Service Token 认证
"""
from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies import verify_service_token, get_catalog_service
from app.services import CatalogService
from app.schemas import (
    SKUFilterRequest,
    SKUInfo,
    ApiResponse,
)

router = APIRouter(prefix="/skus", tags=["Internal-SKU"])


@router.post("/filter", summary="[Agent] SKU Truth Filter")
async def filter_skus(
    data: SKUFilterRequest,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    _verified: Annotated[bool, Depends(verify_service_token)],
):
    """
    SKU Truth Filter - 返回当前 MySQL 真值
    
    用于 Agent 在向量检索后，验证 SKU 的真实库存、价格等信息
    
    请求示例:
    {
      "product_ids": ["15970"],
      "colors": ["黑色"],
      "sizes": ["M"],
      "min_price": null,
      "max_price": "400.00",
      "stock_status": "in_stock"
    }
    """
    # 调用 catalog service 的 SKU 筛选逻辑
    filtered_skus = await catalog_service.filter_skus(
        product_ids=data.product_ids,
        colors=data.colors,
        sizes=data.sizes,
        min_price=data.min_price,
        max_price=data.max_price,
        stock_status=data.stock_status,
    )
    
    return ApiResponse(data={"items": filtered_skus})
