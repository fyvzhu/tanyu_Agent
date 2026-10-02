"""
Internal API - SKU 路由
供 Agent 服务调用，需要 Service Token 认证
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Body

from app.dependencies import verify_service_token, get_catalog_service
from app.services import CatalogService
from app.schemas import ApiResponse
from app.schemas.catalog import SkuItems

router = APIRouter(prefix="/skus", tags=["Internal-SKU"])


@router.post("/filter", response_model=ApiResponse[SkuItems], summary="[Agent] SKU Truth Filter")
async def filter_skus(
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    _verified: Annotated[bool, Depends(verify_service_token)],
    product_ids: list[str] = Body(...),
    colors: list[str] | None = Body(None),
    sizes: list[str] | None = Body(None),
    in_stock: bool | None = Body(None),
):
    """
    SKU Truth Filter - 返回当前 MySQL 真值（使用标准化枚举）

    用于 Agent 在向量检索后，验证 SKU 的真实库存、价格等信息

    参数：
    - product_ids: 商品ID列表
    - colors: 颜色过滤（可选）
    - sizes: 尺码过滤（可选）
    - in_stock: 是否有货（True=in_stock, False=out_of_stock, None=全部）

    返回示例:
    {
      "success": true,
      "data": {
        "items": [
          {
            "sku_id": "SKU001",
            "product_id": "15970",
            "color": "黑色",
            "size_code": "M",
            "price": 299.00,
            "stock_status": "in_stock"
          }
        ]
      }
    }
    """
    # 调用公开版本的SKU过滤（使用标准化枚举）
    result = await catalog_service.filter_skus_public(
        product_ids=product_ids,
        colors=colors,
        sizes=sizes,
        in_stock=in_stock,
    )

    return ApiResponse(data=result)
