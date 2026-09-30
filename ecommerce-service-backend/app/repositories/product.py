"""
商品相关 Repository（异步版本）
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Product, ProductSKU, Promotion
from app.repositories.base import BaseRepository


class ProductRepository(BaseRepository[Product]):
    """商品 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(Product, db)

    async def get_by_product_id(self, product_id: str) -> Product | None:
        """根据 product_id 获取商品"""
        result = await self.db.execute(
            select(Product).where(Product.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_by_product_ids(self, product_ids: list[str]) -> list[Product]:
        """批量获取商品"""
        result = await self.db.execute(
            select(Product).where(Product.product_id.in_(product_ids))
        )
        return list(result.scalars().all())

    async def search_products(
        self,
        q: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Product]:
        """搜索商品"""
        query = select(Product)

        if q:
            query = query.where(
                or_(
                    Product.product_display_name.contains(q),
                    Product.brand.contains(q),
                )
            )

        if brand:
            query = query.where(Product.brand == brand)

        if category:
            query = query.where(Product.master_category == category)

        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def search_product_ids_with_sku_filter(
        self,
        q: str | None = None,
        brand: str | None = None,
        category: str | None = None,
        color: str | None = None,
        size: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        in_stock: bool = True,
    ) -> list[str]:
        """
        搜索商品 ID（带 SKU 过滤）

        使用 SQL JOIN 在数据库层面过滤，避免在 Python 中过滤
        返回符合条件的 product_id 列表
        """
        # 构建查询：Product JOIN ProductSKU
        query = select(Product.product_id).distinct()

        # 如果有 SKU 相关条件，需要 JOIN
        if color or size or min_price or max_price or in_stock:
            query = query.join(ProductSKU, Product.product_id == ProductSKU.product_id)

            if color:
                query = query.where(ProductSKU.color == color)

            if size:
                query = query.where(ProductSKU.size_code == size)

            if min_price is not None:
                query = query.where(ProductSKU.price >= min_price)

            if max_price is not None:
                query = query.where(ProductSKU.price <= max_price)

            if in_stock:
                query = query.where(ProductSKU.stock_status == "in_stock")

        # Product 级别的过滤
        if q:
            query = query.where(
                or_(
                    Product.product_display_name.contains(q),
                    Product.brand.contains(q),
                )
            )

        if brand:
            query = query.where(Product.brand == brand)

        if category:
            query = query.where(Product.master_category == category)

        # 按 product_id 排序（确保分页稳定）
        query = query.order_by(Product.product_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())


class ProductSKURepository(BaseRepository[ProductSKU]):
    """SKU Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(ProductSKU, db)

    async def get_by_sku_id(self, sku_id: str) -> ProductSKU | None:
        """根据 sku_id 获取 SKU"""
        result = await self.db.execute(
            select(ProductSKU).where(ProductSKU.sku_id == sku_id)
        )
        return result.scalar_one_or_none()

    async def get_by_product_id(self, product_id: str) -> list[ProductSKU]:
        """获取商品的所有 SKU"""
        result = await self.db.execute(
            select(ProductSKU).where(ProductSKU.product_id == product_id)
        )
        return list(result.scalars().all())

    async def filter_skus(
        self,
        product_ids: list[str] | None = None,
        colors: list[str] | None = None,
        sizes: list[str] | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        stock_status: str | None = None,
    ) -> list[ProductSKU]:
        """筛选 SKU"""
        query = select(ProductSKU)

        if product_ids:
            query = query.where(ProductSKU.product_id.in_(product_ids))

        if colors:
            query = query.where(ProductSKU.color.in_(colors))

        if sizes:
            query = query.where(ProductSKU.size_code.in_(sizes))

        if min_price is not None:
            query = query.where(ProductSKU.price >= min_price)

        if max_price is not None:
            query = query.where(ProductSKU.price <= max_price)

        if stock_status:
            query = query.where(ProductSKU.stock_status == stock_status)

        result = await self.db.execute(query)
        return list(result.scalars().all())


class PromotionRepository(BaseRepository[Promotion]):
    """促销 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(Promotion, db)

    async def get_active_promotions(self, at: datetime | None = None) -> list[Promotion]:
        """获取所有有效促销"""
        if at is None:
            at = datetime.now()

        result = await self.db.execute(
            select(Promotion).where(
                and_(
                    Promotion.status == "active",
                    Promotion.start_at <= at,
                    Promotion.end_at >= at,
                )
            )
        )
        return list(result.scalars().all())

    async def get_active_promotions_for_product(
        self,
        product_id: str,
        member_level: str | None = None,
        at: datetime | None = None,
    ) -> list[Promotion]:
        """获取商品的有效促销"""
        if at is None:
            at = datetime.now()

        query = select(Promotion).where(
            and_(
                Promotion.product_id == product_id,
                Promotion.status == "active",
                Promotion.start_at <= at,
                Promotion.end_at >= at,
            )
        )

        if member_level:
            query = query.where(
                or_(
                    Promotion.member_level == member_level,
                    Promotion.member_level == "ALL",
                    Promotion.member_level.is_(None),
                )
            )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_knowledge_card(self, product_id: str) -> Product | None:
        """
        获取商品知识卡片

        返回稳定的索引字段，不包含动态的价格/库存
        """
        from loguru import logger

        logger.info(f"获取商品知识卡片: product_id={product_id}")

        product = await self.get_by_product_id(product_id)

        if not product:
            logger.warning(f"商品不存在: product_id={product_id}")
            return None

        logger.debug(
            f"知识卡片获取成功: {product.brand} {product.product_display_name}"
        )

        return product
