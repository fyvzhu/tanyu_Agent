"""
订单服务（异步版本）
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import logger
from app.repositories import (
    OrderRepository,
    OrderItemRepository,
    LogisticsRepository,
    ProductRepository,
    ProductSKURepository,
)
from app.schemas import (
    OrderCreateRequest,
    OrderResponse,
    OrderItemResponse,
    LogisticsResponse,
    LogisticsTraceInfo,
    PaginatedResponse,
)
from app.models import Order, OrderItem


class OrderService:
    """订单服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.order_repo = OrderRepository(db)
        self.order_item_repo = OrderItemRepository(db)
        self.logistics_repo = LogisticsRepository(db)
        self.product_repo = ProductRepository(db)
        self.sku_repo = ProductSKURepository(db)

    async def create_order(self, user_id: str, data: OrderCreateRequest) -> OrderResponse:
        """
        创建订单

        Args:
            user_id: 用户 ID
            data: 订单创建请求

        Returns:
            订单响应

        Raises:
            ValueError: SKU 不存在或缺货
        """
        # 验证 SKU 并计算总金额
        total_amount = Decimal("0.00")
        order_items = []

        for item in data.items:
            sku = await self.sku_repo.get_by_sku_id(item.sku_id)
            if not sku:
                raise ValueError(f"SKU {item.sku_id} 不存在")

            if sku.stock_status != "in_stock":
                raise ValueError(f"SKU {item.sku_id} 已缺货")

            item_total = sku.price * item.quantity
            total_amount += item_total

            order_items.append({
                "product_id": sku.product_id,
                "sku_id": sku.sku_id,
                "quantity": item.quantity,
                "price": sku.price,
            })

        # 生成订单 ID
        order_id = self._generate_order_id()

        # 创建订单
        order = Order(
            order_id=order_id,
            user_id=user_id,
            status="待付款",
            status_desc="等待用户付款",
            amount=total_amount,
            receiver_name=data.receiver_name,
            receiver_phone=data.receiver_phone,
            receiver_address=data.receiver_address,
        )

        created_order = await self.order_repo.create(order)

        # 创建订单明细
        for item_data in order_items:
            item = OrderItem(
                order_id=order_id,
                product_id=item_data["product_id"],
                sku_id=item_data["sku_id"],
                quantity=item_data["quantity"],
                price=item_data["price"],
            )
            await self.order_item_repo.create(item)

        await self.db.commit()

        logger.info(f"订单创建成功：{order_id}")

        return await self._build_order_response(created_order)

    async def get_user_orders(
        self,
        user_id: str,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[OrderResponse]:
        """
        获取用户订单列表

        Args:
            user_id: 用户 ID
            status: 订单状态筛选
            page: 页码
            page_size: 每页数量

        Returns:
            分页的订单列表
        """
        skip = (page - 1) * page_size

        orders = await self.order_repo.get_user_orders(
            user_id=user_id,
            status=status,
            skip=skip,
            limit=page_size,
        )

        items = []
        for order in orders:
            items.append(await self._build_order_response(order))

        # 简化版总数计算
        total = len(items)
        total_pages = (total + page_size - 1) // page_size

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_order_detail(self, order_id: str, user_id: str | None = None) -> OrderResponse | None:
        """
        获取订单详情

        Args:
            order_id: 订单 ID
            user_id: 用户 ID（用于权限校验，None 表示内部调用）

        Returns:
            订单详情或 None
        """
        order = await self.order_repo.get_by_order_id(order_id)
        if not order:
            return None

        # 权限校验
        if user_id is not None and order.user_id != user_id:
            return None

        return await self._build_order_response(order)

    async def get_order_logistics(self, order_id: str) -> list[LogisticsResponse]:
        """
        获取订单物流信息

        Args:
            order_id: 订单 ID

        Returns:
            物流记录列表
        """
        records = await self.logistics_repo.get_by_order_id(order_id)

        return [
            LogisticsResponse(
                logistics_company=record.logistics_company,
                tracking_number=record.tracking_number,
                status=record.status,
                status_desc=record.status_desc,
                updated_at=record.updated_at.isoformat() if record.updated_at else None,
                traces=[
                    LogisticsTraceInfo(
                        trace_time=trace.trace_time.isoformat() if trace.trace_time else None,
                        trace_desc=trace.trace_desc,
                    )
                    for trace in record.traces
                ],
            )
            for record in records
        ]

    async def _build_order_response(self, order: Order) -> OrderResponse:
        """构建订单响应对象"""
        items = await self.order_item_repo.get_by_order_id(order.order_id)

        return OrderResponse(
            order_id=order.order_id,
            user_id=order.user_id,
            status=order.status,
            status_desc=order.status_desc,
            amount=order.amount,
            created_at=order.created_at.isoformat() if order.created_at else None,
            receiver_name=order.receiver_name,
            receiver_phone=order.receiver_phone,
            receiver_address=order.receiver_address,
            items=[
                OrderItemResponse(
                    product_id=item.product_id,
                    sku_id=item.sku_id,
                    quantity=item.quantity,
                    price=item.price,
                )
                for item in items
            ],
        )

    @staticmethod
    def _generate_order_id() -> str:
        """生成订单 ID：O20260913000016"""
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")
        return f"O{timestamp}"
