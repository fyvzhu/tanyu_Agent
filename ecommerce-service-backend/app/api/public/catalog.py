"""
Public API - 商品目录路由
"""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_catalog_service, get_current_user
from app.models import User
from app.services import CatalogService
from app.schemas import ApiResponse
from app.schemas.catalog import (
    ProductItems,
    ProductPublic,
    SkuItems,
    PromotionItems,
)

router = APIRouter(prefix="/catalog", tags=["商品目录"])


@router.get("/products", response_model=ApiResponse[ProductItems], summary="商品搜索")
async def get_products(
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    q: str | None = Query(None, description="搜索关键词"),
    brand: str | None = Query(None, description="品牌筛选"),
    category: str | None = Query(None, description="分类筛选"),
    color: str | None = Query(None, description="颜色筛选"),
    size: str | None = Query(None, description="尺码筛选"),
    min_price: Decimal | None = Query(None, description="最低价格"),
    max_price: Decimal | None = Query(None, description="最高价格"),
    in_stock: bool = Query(True, description="是否仅返回有货SKU"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """
    搜索商品列表

    返回包含统一分类、主图URL、价格范围、库存状态的商品列表
    """
    return ApiResponse(
        data=await catalog_service.search_products_public(
            q=q,
            brand=brand,
            category=category,
            color=color,
            size=size,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/products/{product_id}", response_model=ApiResponse[ProductPublic], summary="商品详情")
async def get_product_detail(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    """
    获取商品详情

    返回包含统一分类和主图URL的商品详细信息
    """
    result = await catalog_service.get_product_detail_public(product_id)
    if not result:
        raise HTTPException(status_code=404, detail="商品不存在")
    return ApiResponse(data=result)


@router.get("/products/{product_id}/skus", response_model=ApiResponse[SkuItems], summary="商品 SKU 列表")
async def get_product_skus(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    """
    获取商品的所有SKU

    返回标准化的SKU列表（库存状态使用 in_stock/out_of_stock）
    """
    # 先检查商品是否存在
    product = await catalog_service.get_product_detail_public(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    skus = await catalog_service.get_product_skus_public(product_id)
    return ApiResponse(data=skus)


@router.get("/products/{product_id}/size-chart", response_model=ApiResponse[dict], summary="商品尺码图")
async def get_product_size_chart(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    """
    获取商品尺码图

    返回尺码数据和尺码图片URL
    """
    product = await catalog_service.get_product_detail_public(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return ApiResponse(
        data={
            "product_id": product_id,
            "size_data": product.size_data or {},
            "image_url": f"/static/size-images/{product_id}.jpg",
        }
    )


@router.get("/products/{product_id}/promotions", response_model=ApiResponse[PromotionItems], summary="商品促销")
async def get_product_promotions(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取商品促销（需要认证）

    - 要求用户 JWT 认证
    - 从 JWT 获取真实用户
    - 根据用户的会员等级过滤促销活动
    - 防止会员活动泄漏
    - 返回标准化的促销信息（使用统一的促销类型枚举）
    """
    product = await catalog_service.get_product_detail_public(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 使用真实用户等级过滤促销
    promotions = await catalog_service.get_active_promotions_public(
        product_id=product_id,
        member_level=current_user.level
    )
    return ApiResponse(data=promotions)
