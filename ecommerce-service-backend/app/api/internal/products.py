"""
Internal API - 商品（SPU）路由
供 Agent 服务调用，需要 Service Token 认证
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import verify_service_token, get_catalog_service
from app.services import CatalogService
from app.schemas import (
    BatchGetProductsRequest,
    ProductKnowledgeCard,
    ApiResponse,
)
from app.schemas.catalog import ProductListItem

router = APIRouter(prefix="/products", tags=["Internal-商品"])


@router.post("/batch-get", response_model=ApiResponse[list[ProductListItem]], summary="[Agent] 批量获取商品信息")
async def batch_get_products(
    data: BatchGetProductsRequest,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    _verified: Annotated[bool, Depends(verify_service_token)],
):
    """
    批量获取商品信息（供 Agent Discovery 使用）

    返回包含主图、分类、价格范围和库存的商品列表项
    用于 Agent 组装 ProductCandidate 和 ProductCard
    """
    from app.schemas.catalog import StockStatus

    products = []
    for product_id in data.product_ids:
        try:
            # 获取商品基本信息
            product = await catalog_service.get_product_detail(product_id)
            if not product:
                continue

            # 获取该商品的所有 SKU 计算价格范围和库存
            skus = await catalog_service.sku_repo.get_by_product_id(product_id)
            if not skus:
                continue

            prices = [sku.price for sku in skus]
            has_stock = any(sku.stock_status == StockStatus.IN_STOCK.value for sku in skus)

            products.append(ProductListItem(
                product_id=product.product_id,
                brand=product.brand,
                product_display_name=product.product_display_name,
                category=catalog_service._compute_category(product),
                main_image_url=catalog_service._compute_main_image_url(product.product_id),
                min_price=min(prices),
                max_price=max(prices),
                has_stock=has_stock,
            ))
        except Exception:
            # 忽略单个商品获取失败，继续处理其他商品
            continue

    return ApiResponse(data=products)


@router.get("/{product_id}/knowledge-card", response_model=ApiResponse[ProductKnowledgeCard], summary="[Agent] 获取商品知识卡片")
async def get_product_knowledge_card(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    _verified: Annotated[bool, Depends(verify_service_token)],
):
    """
    获取商品知识卡片（供 RAG 使用）
    
    返回商品的核心事实信息，用于 Agent 向量检索和知识问答
    """
    product = await catalog_service.get_product_detail(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    
    category = product.type or product.sub_category or product.master_category
    selling_points = product.selling_points or []
    size_summary = None
    if product.size_data:
        size_summary = "商品包含结构化尺码表，Agent 需要展示或计算尺码时应回查 Commerce API。"

    # 添加静态资源URL
    main_image_url = f"/static/main-images/{product_id}.jpg"
    size_chart_url = f"/static/size-images/{product_id}.jpg" if product.size_data else None

    knowledge_card = ProductKnowledgeCard(
        product_id=product.product_id,
        brand=product.brand,
        product_display_name=product.product_display_name,
        category=category,
        material=product.material,
        selling_points=selling_points,
        features=selling_points,  # 保持向后兼容
        size_summary=size_summary,
        main_image_url=main_image_url,
        size_chart_url=size_chart_url,
    )

    return ApiResponse(data=knowledge_card)


@router.get("/{product_id}/assets", summary="[Agent] 获取商品素材")
async def get_product_assets(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    _verified: Annotated[bool, Depends(verify_service_token)],
    asset_type: str = Query("MAIN_IMAGE", description="素材类型: MAIN_IMAGE 或 SIZE_CHART"),
):
    """
    获取商品素材（图片URL）
    
    - MAIN_IMAGE: 主图
    - SIZE_CHART: 尺码表
    """
    product = await catalog_service.get_product_detail(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")
    
    if asset_type == "MAIN_IMAGE":
        asset_url = f"/static/main-images/{product_id}.jpg"
    elif asset_type == "SIZE_CHART":
        asset_url = f"/static/size-images/{product_id}.jpg"
    else:
        raise HTTPException(status_code=400, detail="不支持的素材类型")
    
    return ApiResponse(data={"product_id": product_id, "type": asset_type, "url": asset_url})


@router.get("/{product_id}/promotions/active", summary="[Agent] 获取商品当前有效促销")
async def get_active_promotions(
    product_id: str,
    catalog_service: Annotated[CatalogService, Depends(get_catalog_service)],
    _verified: Annotated[bool, Depends(verify_service_token)],
    member_level: str | None = Query(None, description="会员等级: PLUS/普通会员"),
    at: str | None = Query(None, description="查询时间点（ISO 8601格式）"),
):
    """
    获取商品当前有效的促销信息
    
    Agent 不自行判断促销时间有效性，由后端返回真实有效的促销
    """
    # 获取商品详情（验证商品存在）
    product = await catalog_service.get_product_detail(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="商品不存在")

    # 获取促销信息（简化版：返回商品关联的促销）
    promotions = await catalog_service.get_product_promotions(
        product_id=product_id,
        member_level=member_level
    )
    
    return ApiResponse(data={"items": promotions})
