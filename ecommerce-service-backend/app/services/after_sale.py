"""
售后服务（异步版本）
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import logger
from app.repositories import (
    ReturnRequestRepository,
    ExchangeRequestRepository,
    ShippingUrgeRepository,
    OrderRepository,
    OrderItemRepository,
    ProductSKURepository,
)
from app.schemas import (
    ReturnRequestCreate,
    ReturnRequestResponse,
    ExchangeRequestCreate,
    ExchangeRequestResponse,
    ShippingUrgeRequestCreate,
    ShippingUrgeRequestResponse,
)
from app.models import ReturnRequest, ExchangeRequest, ShippingUrgeRequest


class AfterSaleService:
    """售后服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.return_repo = ReturnRequestRepository(db)
        self.exchange_repo = ExchangeRequestRepository(db)
        self.urge_repo = ShippingUrgeRepository(db)
        self.order_repo = OrderRepository(db)
        self.order_item_repo = OrderItemRepository(db)
        self.sku_repo = ProductSKURepository(db)

    async def create_return_request(self, user_id: str, data: ReturnRequestCreate) -> ReturnRequestResponse:
        """
        创建退货申请

        Args:
            user_id: 用户 ID
            data: 退货申请数据

        Returns:
            退货申请响应

        Raises:
            ValueError: 订单不存在或不属于该用户
        """
        # 验证订单
        order = await self.order_repo.get_by_order_id(data.order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.user_id != user_id:
            raise ValueError("无权操作此订单")

        if order.status in {"已取消", "待付款"}:
            raise ValueError("订单状态不允许退货")

        # 验证订单项并计算退款金额
        order_items = await self.order_item_repo.get_by_order_id(data.order_id)
        target_item = None
        for item in order_items:
            if item.sku_id == data.sku_id and item.product_id == data.product_id:
                target_item = item
                break

        if not target_item:
            raise ValueError("订单中不存在此商品或 SKU")

        existing_return = await self.return_repo.get_active_by_order_and_sku(data.order_id, data.sku_id)
        if existing_return:
            raise ValueError("该订单商品已有进行中的退货申请")

        existing_exchange = await self.exchange_repo.get_active_by_order_and_sku(data.order_id, data.sku_id)
        if existing_exchange:
            raise ValueError("该订单商品已有进行中的换货申请")

        refund_amount = target_item.price * target_item.quantity

        # 生成申请 ID
        request_id = self._generate_return_request_id()

        # 创建退货申请
        return_request = ReturnRequest(
            request_id=request_id,
            user_id=user_id,
            order_id=data.order_id,
            product_id=target_item.product_id,
            sku_id=data.sku_id,
            reason=data.reason,
            refund_amount=refund_amount,
            status="REQUESTED",
        )

        created = await self.return_repo.create(return_request)
        await self.db.commit()

        logger.info(f"退货申请创建成功：{request_id}")

        return ReturnRequestResponse(
            request_id=created.request_id,
            order_id=created.order_id,
            product_id=created.product_id,
            sku_id=created.sku_id,
            reason=created.reason,
            refund_amount=created.refund_amount,
            status=created.status,
            created_at=created.created_at.isoformat() if created.created_at else None,
        )

    async def create_exchange_request(self, user_id: str, data: ExchangeRequestCreate) -> ExchangeRequestResponse:
        """
        创建换货申请

        Args:
            user_id: 用户 ID
            data: 换货申请数据

        Returns:
            换货申请响应

        Raises:
            ValueError: 订单不存在或不属于该用户
        """
        # 验证订单
        order = await self.order_repo.get_by_order_id(data.order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.user_id != user_id:
            raise ValueError("无权操作此订单")

        if order.status in {"已取消", "待付款"}:
            raise ValueError("订单状态不允许换货")

        # 验证订单项
        order_items = await self.order_item_repo.get_by_order_id(data.order_id)
        target_item = None
        for item in order_items:
            if item.sku_id == data.original_sku_id and item.product_id == data.product_id:
                target_item = item
                break

        if not target_item:
            raise ValueError("订单中不存在此商品或 SKU")

        exchange_sku = await self.sku_repo.get_by_sku_id(data.exchange_sku_id)
        if not exchange_sku:
            raise ValueError("目标 SKU 不存在")
        if exchange_sku.product_id != data.product_id:
            raise ValueError("目标 SKU 不属于同一商品")
        if exchange_sku.stock_status != "in_stock":
            raise ValueError("目标 SKU 无库存")

        existing_return = await self.return_repo.get_active_by_order_and_sku(data.order_id, data.original_sku_id)
        if existing_return:
            raise ValueError("该订单商品已有进行中的退货申请")

        existing_exchange = await self.exchange_repo.get_active_by_order_and_sku(data.order_id, data.original_sku_id)
        if existing_exchange:
            raise ValueError("该订单商品已有进行中的换货申请")

        # 生成申请 ID
        request_id = self._generate_exchange_request_id()

        # 创建换货申请
        exchange_request = ExchangeRequest(
            request_id=request_id,
            user_id=user_id,
            order_id=data.order_id,
            product_id=target_item.product_id,
            original_sku_id=data.original_sku_id,
            exchange_sku_id=data.exchange_sku_id,
            reason=data.reason,
            status="REQUESTED",
        )


        created = await self.exchange_repo.create(exchange_request)
        await self.db.commit()

        logger.info(f"换货申请创建成功：{request_id}")

        return ExchangeRequestResponse(
            request_id=created.request_id,
            order_id=created.order_id,
            product_id=created.product_id,
            original_sku_id=created.original_sku_id,
            exchange_sku_id=created.exchange_sku_id,
            reason=created.reason,
            status=created.status,
            refund_amount=Decimal("0.00"),
            created_at=created.created_at.isoformat() if created.created_at else None,
        )

    async def create_shipping_urge(self, user_id: str, data: ShippingUrgeRequestCreate) -> ShippingUrgeRequestResponse:
        """
        创建催发货请求

        Args:
            user_id: 用户 ID
            data: 催发货请求数据

        Returns:
            催发货请求响应

        Raises:
            ValueError: 订单不存在或不属于该用户
        """
        # 验证订单
        order = await self.order_repo.get_by_order_id(data.order_id)
        if not order:
            raise ValueError("订单不存在")

        if order.user_id != user_id:
            raise ValueError("无权操作此订单")
        if order.status not in {"待发货", "运输中", "待收货"}:
            raise ValueError("当前订单状态不支持催发货")

        # 生成请求 ID
        request_id = self._generate_urge_request_id()

        # 创建催发货请求
        urge_request = ShippingUrgeRequest(
            request_id=request_id,
            user_id=user_id,
            order_id=data.order_id,
            reason_code=data.reason_code,
            reason_detail=data.reason_detail,
            status="SUBMITTED",
        )

        created = await self.urge_repo.create(urge_request)
        await self.db.commit()

        logger.info(f"催发货请求创建成功：{request_id}")

        return ShippingUrgeRequestResponse(
            request_id=created.request_id,
            order_id=created.order_id,
            reason_code=created.reason_code,
            reason_detail=created.reason_detail,
            status=created.status,
            created_at=created.created_at.isoformat() if created.created_at else None,
        )

    @staticmethod
    def _generate_return_request_id() -> str:
        """生成退货申请 ID：R20260913000016"""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S%f")
        return f"R{timestamp}"

    @staticmethod
    def _generate_exchange_request_id() -> str:
        """生成换货申请 ID：E20260913000016"""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S%f")
        return f"E{timestamp}"

    @staticmethod
    def _generate_urge_request_id() -> str:
        """生成催发货请求 ID：U20260913000016"""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S%f")
        return f"U{timestamp}"
