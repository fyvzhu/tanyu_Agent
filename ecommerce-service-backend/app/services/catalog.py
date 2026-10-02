"""
商品目录服务（异步版本）
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.repositories import ProductRepository, ProductSKURepository, PromotionRepository
from app.schemas import ProductDetail, ProductWithDefaultSKU, SKUInfo, PromotionInfo, PaginatedResponse


class CatalogService:
    """商品目录服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.product_repo = ProductRepository(db)
        self.sku_repo = ProductSKURepository(db)
        self.promotion_repo = PromotionRepository(db)

    async def search_products(
        self,
        q: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        color: str | None = None,
        size: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        in_stock: bool = True,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[ProductWithDefaultSKU]:
        """
        搜索商品（返回商品 + 默认 SKU）

        Args:
            q: 搜索关键词
            brand: 品牌筛选
            category: 分类筛选
            color: 颜色筛选
            size: 尺码筛选
            min_price: 最低价格
            max_price: 最高价格
            in_stock: 是否有货
            page: 页码
            page_size: 每页数量

        Returns:
            分页的商品列表
        """
        logger.info(f"搜索商品: q={q}, brand={brand}, category={category}, color={color}, size={size}, price=[{min_price}, {max_price}], in_stock={in_stock}, page={page}")

        # 使用 Repository 的 SQL 过滤（而不是 Python 过滤）
        # 先获取符合条件的商品 ID 列表（通过 SKU JOIN）
        product_ids = await self.product_repo.search_product_ids_with_sku_filter(
            q=q,
            brand=brand,
            category=category,
            color=color,
            size=size,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
        )

        # 计算总数（在分页前）
        total = len(product_ids)
        total_pages = (total + page_size - 1) // page_size if total > 0 else 0

        # 分页
        skip = (page - 1) * page_size
        paginated_product_ids = product_ids[skip:skip + page_size]

        # 批量获取商品详情
        items = []
        for product_id in paginated_product_ids:
            product = await self.product_repo.get_by_product_id(product_id)
            if not product:
                continue

            # 获取符合条件的 SKU（用于显示默认 SKU）
            skus = await self.sku_repo.get_by_product_id(product_id)

            # 应用相同的过滤条件获取默认 SKU
            filtered_skus = [
                sku for sku in skus
                if (not color or sku.color == color)
                and (not size or sku.size_code == size)
                and (min_price is None or sku.price >= min_price)
                and (max_price is None or sku.price <= max_price)
                and (not in_stock or sku.stock_status == "in_stock")
            ]

            default_sku = filtered_skus[0] if filtered_skus else None

            items.append(ProductWithDefaultSKU(
                product_id=product.product_id,
                brand=product.brand,
                product_display_name=product.product_display_name,
                default_sku=SKUInfo(
                    sku_id=default_sku.sku_id,
                    product_id=default_sku.product_id,
                    color=default_sku.color,
                    size_code=default_sku.size_code,
                    price=default_sku.price,
                    stock_status=default_sku.stock_status,
                ) if default_sku else None,
            ))

        logger.info(f"搜索商品完成: 总共 {total} 个结果，返回第 {page} 页（{len(items)} 项）")
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    
    async def get_product_detail(self, product_id: str) -> ProductDetail | None:
        """
        获取商品详情（SPU 信息）

        Args:
            product_id: 商品 ID

        Returns:
            商品详情或 None
        """
        logger.info(f"获取商品详情: product_id={product_id}")
        product = await self.product_repo.get_by_product_id(product_id)
        if not product:
            logger.warning(f"商品不存在: product_id={product_id}")
            return None

        return ProductDetail(
            product_id=product.product_id,
            brand=product.brand,
            product_display_name=product.product_display_name,
            gender=product.gender,
            master_category=product.master_category,
            sub_category=product.sub_category,
            type=product.type,
            material=product.material,
            selling_points=product.selling_points,
            size_data=product.size_data,
        )

    async def get_product_skus(self, product_id: str) -> list[SKUInfo]:
        """
        获取商品的所有 SKU

        Args:
            product_id: 商品 ID

        Returns:
            SKU 列表
        """
        logger.info(f"获取商品SKU列表: product_id={product_id}")
        skus = await self.sku_repo.get_by_product_id(product_id)
        logger.info(f"找到 {len(skus)} 个SKU")
        return [
            SKUInfo(
                sku_id=sku.sku_id,
                product_id=sku.product_id,
                color=sku.color,
                size_code=sku.size_code,
                price=sku.price,
                stock_status=sku.stock_status,
            )
            for sku in skus
        ]

    async def get_active_promotions(
        self,
        product_id: str,
        member_level: str | None = None,
    ) -> list[PromotionInfo]:
        """
        获取商品的有效促销

        Args:
            product_id: 商品 ID
            member_level: 会员等级（PLUS/普通会员）

        Returns:
            促销信息列表
        """
        logger.info(f"获取商品促销: product_id={product_id}, member_level={member_level}")
        promotions = await self.promotion_repo.get_active_promotions_for_product(
            product_id=product_id,
            member_level=member_level,
            at=datetime.now(),
        )

        logger.info(f"找到 {len(promotions)} 个有效促销")
        return [
            PromotionInfo(
                promotion_id=promo.promotion_id,
                promotion_name=promo.promotion_name,
                promotion_type=promo.promotion_type,
                discount_amount=promo.discount_amount,
                discount_rate=promo.discount_rate,
                promo_price=promo.promo_price,
                description=promo.description,
            )
            for promo in promotions
        ]

    async def get_all_active_promotions(
        self,
        member_level: str | None = None,
        at: datetime | None = None,
    ) -> list[PromotionInfo]:
        """
        获取所有有效促销

        Args:
            member_level: 会员等级（PLUS/普通会员）
            at: 查询时间点（默认为当前时间）

        Returns:
            促销信息列表
        """
        if at is None:
            at = datetime.now()

        logger.info(f"获取所有有效促销: member_level={member_level}, at={at}")
        promotions = await self.promotion_repo.get_active_promotions(at=at)

        # 如果指定了会员等级，过滤促销
        if member_level:
            promotions = [
                promo for promo in promotions
                if promo.member_level in (member_level, "ALL", None)
            ]

        logger.info(f"找到 {len(promotions)} 个有效促销")
        return [
            PromotionInfo(
                promotion_id=promo.promotion_id,
                promotion_name=promo.promotion_name,
                promotion_type=promo.promotion_type,
                discount_amount=promo.discount_amount,
                discount_rate=promo.discount_rate,
                promo_price=promo.promo_price,
                description=promo.description,
            )
            for promo in promotions
        ]

    async def get_all_active_promotions(
        self,
        member_level: str | None = None,
        at: datetime | None = None,
    ) -> list[PromotionInfo]:
        """
        获取所有有效促销

        Args:
            member_level: 会员等级（PLUS/普通会员）
            at: 查询时间点（默认为当前时间）

        Returns:
            促销信息列表
        """
        if at is None:
            at = datetime.now()

        logger.info(f"获取所有有效促销: member_level={member_level}, at={at}")
        promotions = await self.promotion_repo.get_active_promotions(at=at)

        # 如果指定了会员等级，过滤促销
        if member_level:
            promotions = [
                promo for promo in promotions
                if promo.member_level in (member_level, "ALL", None)
            ]

        logger.info(f"找到 {len(promotions)} 个有效促销")
        return [
            PromotionInfo(
                promotion_id=promo.promotion_id,
                promotion_name=promo.promotion_name,
                promotion_type=promo.promotion_type,
                discount_amount=promo.discount_amount,
                discount_rate=promo.discount_rate,
                promo_price=promo.promo_price,
                description=promo.description,
            )
            for promo in promotions
        ]

    async def get_sku_by_id(self, sku_id: str) -> SKUInfo | None:
        """
        根据 SKU ID 获取 SKU 信息

        Args:
            sku_id: SKU ID

        Returns:
            SKU 信息或 None
        """
        sku = await self.sku_repo.get_by_sku_id(sku_id)
        if not sku:
            return None

        return SKUInfo(
            sku_id=sku.sku_id,
            product_id=sku.product_id,
            color=sku.color,
            size_code=sku.size_code,
            price=sku.price,
            stock_status=sku.stock_status,
        )

    async def filter_skus(
        self,
        product_ids: list[str] | None = None,
        colors: list[str] | None = None,
        sizes: list[str] | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        stock_status: str | None = None,
    ) -> list[SKUInfo]:
        """
        SKU Truth Filter - 按条件筛选 SKU（供 Internal API 使用）

        Args:
            product_ids: 商品 ID 列表
            colors: 颜色列表
            sizes: 尺码列表
            min_price: 最低价格
            max_price: 最高价格
            stock_status: 库存状态

        Returns:
            符合条件的 SKU 列表
        """
        logger.info(f"筛选SKU: product_ids={product_ids}, colors={colors}, sizes={sizes}, price=[{min_price}, {max_price}], stock_status={stock_status}")

        # 调用 repository 的筛选方法
        skus = await self.sku_repo.filter_skus(
            product_ids=product_ids,
            colors=colors,
            sizes=sizes,
            min_price=min_price,
            max_price=max_price,
            stock_status=stock_status,
        )

        logger.info(f"筛选到 {len(skus)} 个SKU")
        return [
            SKUInfo(
                sku_id=sku.sku_id,
                product_id=sku.product_id,
                color=sku.color,
                size_code=sku.size_code,
                price=sku.price,
                stock_status=sku.stock_status,
            )
            for sku in skus
        ]

    async def get_product_promotions(
        self,
        product_id: str,
        member_level: str | None = None,
    ) -> list[PromotionInfo]:
        """
        获取商品的有效促销信息（供 Internal API 使用）

        Args:
            product_id: 商品 ID
            member_level: 会员等级

        Returns:
            促销信息列表
        """
        return await self.get_active_promotions(product_id=product_id, member_level=member_level)

    # ==================== 公开 API 方法（返回公开 Schema） ====================

    def _compute_category(self, product) -> str:
        """计算统一的分类字段（从最细到最粗）"""
        return product.type or product.sub_category or product.master_category or "未分类"

    def _compute_main_image_url(self, product_id: str) -> str:
        """计算主图 URL"""
        return f"/static/main-images/{product_id}.jpg"

    def _compute_size_image_url(self, product_id: str) -> str | None:
        """计算尺码图 URL（如果存在）"""
        # 可以检查文件是否存在，但这里先简单返回
        return f"/static/size-images/{product_id}.jpg"

    async def get_product_detail_public(self, product_id: str):
        """
        获取公开的商品详情（带统一字段）

        Returns:
            ProductPublic 或 None
        """
        from app.schemas.catalog import ProductPublic

        logger.info(f"获取公开商品详情: product_id={product_id}")
        product = await self.product_repo.get_by_product_id(product_id)
        if not product:
            logger.warning(f"商品不存在: product_id={product_id}")
            return None

        return ProductPublic(
            product_id=product.product_id,
            brand=product.brand,
            product_display_name=product.product_display_name,
            gender=product.gender,
            category=self._compute_category(product),
            main_image_url=self._compute_main_image_url(product.product_id),
            material=product.material,
            selling_points=product.selling_points,
            size_data=product.size_data,
        )

    async def search_products_public(
        self,
        q: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        color: str | None = None,
        size: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        in_stock: bool = True,
        page: int = 1,
        page_size: int = 20,
    ):
        """
        搜索商品（返回公开的商品列表项）

        Returns:
            ProductItems
        """
        from app.schemas.catalog import ProductListItem, ProductItems, StockStatus

        logger.info(f"搜索公开商品: q={q}, brand={brand}, category={category}")

        # 获取符合条件的商品 ID
        product_ids = await self.product_repo.search_product_ids_with_sku_filter(
            q=q, brand=brand, category=category, color=color, size=size,
            min_price=min_price, max_price=max_price, in_stock=in_stock,
        )

        total = len(product_ids)
        skip = (page - 1) * page_size
        paginated_product_ids = product_ids[skip:skip + page_size]

        items = []
        for product_id in paginated_product_ids:
            product = await self.product_repo.get_by_product_id(product_id)
            if not product:
                continue

            # 获取该商品的所有 SKU 计算价格范围和库存
            skus = await self.sku_repo.get_by_product_id(product_id)
            if not skus:
                continue

            prices = [sku.price for sku in skus]
            has_stock = any(sku.stock_status == StockStatus.IN_STOCK.value for sku in skus)

            items.append(ProductListItem(
                product_id=product.product_id,
                brand=product.brand,
                product_display_name=product.product_display_name,
                category=self._compute_category(product),
                main_image_url=self._compute_main_image_url(product.product_id),
                min_price=min(prices),
                max_price=max(prices),
                has_stock=has_stock,
            ))

        logger.info(f"搜索完成: 总共 {total} 个结果，返回第 {page} 页（{len(items)} 项）")
        return ProductItems(items=items, total=total, page=page, page_size=page_size)

    async def get_product_skus_public(self, product_id: str):
        """
        获取商品的公开 SKU 列表

        Returns:
            SkuItems
        """
        from app.schemas.catalog import SkuPublic, SkuItems, StockStatus

        logger.info(f"获取公开SKU列表: product_id={product_id}")
        skus = await self.sku_repo.get_by_product_id(product_id)

        items = [
            SkuPublic(
                sku_id=sku.sku_id,
                product_id=sku.product_id,
                color=sku.color,
                size_code=sku.size_code,
                price=sku.price,
                stock_status=StockStatus(sku.stock_status),
            )
            for sku in skus
        ]

        return SkuItems(items=items)

    async def filter_skus_public(
        self,
        product_ids: list[str],
        colors: list[str] | None = None,
        sizes: list[str] | None = None,
        in_stock: bool | None = None,
    ):
        """
        批量过滤 SKU（公开版本）

        Returns:
            SkuItems
        """
        from app.schemas.catalog import SkuPublic, SkuItems, StockStatus

        logger.info(f"批量过滤SKU: product_ids={product_ids}, colors={colors}, sizes={sizes}, in_stock={in_stock}")

        all_skus = []
        for product_id in product_ids:
            skus = await self.sku_repo.get_by_product_id(product_id)
            all_skus.extend(skus)

        # 应用过滤条件
        filtered = all_skus
        if colors:
            filtered = [sku for sku in filtered if sku.color in colors]
        if sizes:
            filtered = [sku for sku in filtered if sku.size_code in sizes]
        if in_stock is not None:
            target_status = StockStatus.IN_STOCK.value if in_stock else StockStatus.OUT_OF_STOCK.value
            filtered = [sku for sku in filtered if sku.stock_status == target_status]

        items = [
            SkuPublic(
                sku_id=sku.sku_id,
                product_id=sku.product_id,
                color=sku.color,
                size_code=sku.size_code,
                price=sku.price,
                stock_status=StockStatus(sku.stock_status),
            )
            for sku in filtered
        ]

        return SkuItems(items=items)

    async def get_active_promotions_public(
        self,
        product_id: str,
        member_level: str | None = None,
        at: datetime | None = None,
    ):
        """
        获取商品的公开促销信息

        Returns:
            PromotionItems
        """
        from app.schemas.catalog import PromotionPublic, PromotionItems, PromotionType

        if at is None:
            at = datetime.now()

        logger.info(f"获取公开促销: product_id={product_id}, member_level={member_level}")
        promotions = await self.promotion_repo.get_active_promotions_for_product(
            product_id=product_id, at=at
        )

        # 根据会员等级过滤
        if member_level:
            promotions = [
                promo for promo in promotions
                if promo.member_level in (member_level, "ALL", None)
            ]

        items = []
        for promo in promotions:
            try:
                # 尝试转换枚举值，如果失败则跳过该促销
                promo_type = PromotionType(promo.promotion_type)
                items.append(
                    PromotionPublic(
                        promotion_id=promo.promotion_id,
                        title=promo.promotion_name,
                        promotion_type=promo_type,
                        description=promo.description,
                        start_at=promo.start_at,
                        end_at=promo.end_at,
                        applicable=True,  # 已过滤，所以都适用
                        discount_rate=promo.discount_rate,
                        discount_amount=promo.discount_amount,
                        threshold_amount=promo.threshold_amount,
                        promo_price=promo.promo_price,
                    )
                )
            except ValueError as e:
                logger.warning(
                    f"跳过未知促销类型: promotion_id={promo.promotion_id}, "
                    f"promotion_type={promo.promotion_type}, error={e}"
                )

        return PromotionItems(items=items)

