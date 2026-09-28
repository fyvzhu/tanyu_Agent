"""
售后相关 Repository（异步版本）
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import ReturnRequest, ExchangeRequest, ShippingUrgeRequest
from app.repositories.base import BaseRepository


class ReturnRequestRepository(BaseRepository[ReturnRequest]):
    """退货退款 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(ReturnRequest, db)

    async def get_by_request_id(self, request_id: str) -> ReturnRequest | None:
        """根据请求 ID 获取退货记录"""
        result = await self.db.execute(
            select(ReturnRequest).where(ReturnRequest.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_order_and_sku(self, order_id: str, sku_id: str) -> ReturnRequest | None:
        """检查订单+SKU是否已有进行中的退货申请"""
        result = await self.db.execute(
            select(ReturnRequest).where(
                ReturnRequest.order_id == order_id,
                ReturnRequest.sku_id == sku_id,
                ReturnRequest.status.in_(["REQUESTED", "APPROVED"]),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: str) -> list[ReturnRequest]:
        """获取订单的所有退货记录"""
        result = await self.db.execute(
            select(ReturnRequest).where(ReturnRequest.order_id == order_id)
        )
        return list(result.scalars().all())


class ExchangeRequestRepository(BaseRepository[ExchangeRequest]):
    """换货 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(ExchangeRequest, db)

    async def get_by_request_id(self, request_id: str) -> ExchangeRequest | None:
        """根据请求 ID 获取换货记录"""
        result = await self.db.execute(
            select(ExchangeRequest).where(ExchangeRequest.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_active_by_order_and_sku(self, order_id: str, sku_id: str) -> ExchangeRequest | None:
        """检查订单+SKU是否已有进行中的换货申请"""
        result = await self.db.execute(
            select(ExchangeRequest).where(
                ExchangeRequest.order_id == order_id,
                ExchangeRequest.original_sku_id == sku_id,
                ExchangeRequest.status.in_(["REQUESTED", "APPROVED"]),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: str) -> list[ExchangeRequest]:
        """获取订单的所有换货记录"""
        result = await self.db.execute(
            select(ExchangeRequest).where(ExchangeRequest.order_id == order_id)
        )
        return list(result.scalars().all())


class ShippingUrgeRepository(BaseRepository[ShippingUrgeRequest]):
    """催发货 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(ShippingUrgeRequest, db)

    async def get_by_request_id(self, request_id: str) -> ShippingUrgeRequest | None:
        """根据请求 ID 获取催发货记录"""
        result = await self.db.execute(
            select(ShippingUrgeRequest).where(ShippingUrgeRequest.request_id == request_id)
        )
        return result.scalar_one_or_none()

    async def get_by_order_id(self, order_id: str) -> list[ShippingUrgeRequest]:
        """获取订单的所有催发货记录"""
        result = await self.db.execute(
            select(ShippingUrgeRequest).where(ShippingUrgeRequest.order_id == order_id)
        )
        return list(result.scalars().all())
