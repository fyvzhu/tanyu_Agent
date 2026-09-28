"""
Public API - 商品目录路由
"""
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_catalog_service, get_current_user
from app.models import User
from app.services import CatalogService
from app.schemas import (
    ApiResponse,
    ProductResponse,
    ProductDetailResponse,
    SKUInfo,
    PromotionInfo,
    PaginatedResponse,
)

router = APIRouter(prefix="/catalog", tags=["商品目录"])


@router.get("/products", response_model=ApiResponse[PaginatedResponse[ProductResponse]], summary="商品搜索")
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
    return ApiResponse(
        data=await catalog_service.search_products(
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


@router.get("/products/{product_id}", response_model=ApiResponse[ProductDetailResponse], summary="商品详情")
async def get_product_detail(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    result = await catalog_service.get_product_detail(product_id)
    if not result:
        raise HTTPException(status_code=404, detail="商品不存在")
    return ApiResponse(data=result)


@router.get("/products/{product_id}/skus", response_model=ApiResponse[dict], summary="商品 SKU 列表")
async def get_product_skus(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    product = await catalog_service.get_product_detail(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    skus: list[SKUInfo] = await catalog_service.get_product_skus(product_id)
    return ApiResponse(data={"items": skus})


@router.get("/products/{product_id}/size-chart", response_model=ApiResponse[dict], summary="商品尺码图")
async def get_product_size_chart(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
):
    product = await catalog_service.get_product_detail(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    return ApiResponse(
        data={
            "product_id": product_id,
            "size_data": product.size_data or {},
            "image_url": f"/static/size-images/{product_id}.jpg",
        }
    )


@router.get("/products/{product_id}/promotions", response_model=ApiResponse[dict], summary="商品促销")
async def get_product_promotions(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取商品促销（P1-04 修复）

    - 要求用户 JWT 认证
    - 从 JWT sub 获取真实用户
    - 根据用户的 member level 过滤促销活动
    - 防止会员活动泄漏
    """
    product = await catalog_service.get_product_detail(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # P1-04: 传入用户的真实 member_level
    promotions: list[PromotionInfo] = await catalog_service.get_active_promotions(
        product_id=product_id,
        member_level=current_user.level  # 使用真实用户等级
    )
    return ApiResponse(data={"items": promotions})
