"""
订单相关 Repository（异步版本）
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.models import Order, OrderItem, LogisticsRecord, LogisticsTrace
from app.repositories.base import BaseRepository


class OrderRepository(BaseRepository[Order]):
    """订单 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(Order, db)

    async def get_by_order_id(self, order_id: str) -> Order | None:
        """根据 order_id 获取订单（包含明细）"""
        result = await self.db.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.order_id == order_id)
        )
        return result.scalar_one_or_none()

    async def get_user_orders(
        self,
        user_id: str,
        status: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Order]:
        """获取用户订单列表"""
        query = select(Order).where(Order.user_id == user_id)

        if status:
            query = query.where(Order.status == status)

        query = query.order_by(Order.created_at.desc()).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def count_user_orders(self, user_id: str, status: str | None = None) -> int:
        """统计用户订单数量"""
        query = select(func.count()).select_from(Order).where(Order.user_id == user_id)

        if status:
            query = query.where(Order.status == status)

        result = await self.db.execute(query)
        return result.scalar() or 0


class OrderItemRepository(BaseRepository[OrderItem]):
    """订单明细 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(OrderItem, db)

    async def get_by_order_id(self, order_id: str) -> list[OrderItem]:
        """获取订单的所有明细"""
        result = await self.db.execute(
            select(OrderItem).where(OrderItem.order_id == order_id)
        )
        return list(result.scalars().all())

    async def get_item_by_sku(self, order_id: str, sku_id: str) -> OrderItem | None:
        """根据订单和 SKU 获取订单项"""
        result = await self.db.execute(
            select(OrderItem).where(
                OrderItem.order_id == order_id,
                OrderItem.sku_id == sku_id
            )
        )
        return result.scalar_one_or_none()


class LogisticsRepository(BaseRepository[LogisticsRecord]):
    """物流 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(LogisticsRecord, db)

    async def get_by_order_id(self, order_id: str) -> list[LogisticsRecord]:
        """获取订单的所有物流记录（包含轨迹）"""
        result = await self.db.execute(
            select(LogisticsRecord)
            .options(selectinload(LogisticsRecord.traces))
            .where(LogisticsRecord.order_id == order_id)
            .order_by(LogisticsRecord.updated_at.desc())
        )
        return list(result.scalars().all())
