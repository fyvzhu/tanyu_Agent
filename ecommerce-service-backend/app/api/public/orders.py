"""
Public API - 订单与物流路由
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_user, get_order_service
from app.services import OrderService
from app.models import User
from app.schemas import (
    ApiResponse,
    OrderResponse,
    LogisticsResponse,
    PaginatedResponse,
)

router = APIRouter(prefix="/orders", tags=["订单"])


@router.get("", response_model=ApiResponse[PaginatedResponse[OrderResponse]], summary="我的订单")
async def get_orders(
    current_user: Annotated[User, Depends(get_current_user)],
    order_service: Annotated[OrderService, Depends(get_order_service)],
    status: str | None = Query(None, description="订单状态筛选"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    return ApiResponse(
        data=await order_service.get_user_orders(
            user_id=current_user.user_id,
            status=status,
            page=page,
            page_size=page_size,
        )
    )


@router.get("/{order_id}", response_model=ApiResponse[OrderResponse], summary="订单详情")
async def get_order_detail(
    order_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    order_service: Annotated[OrderService, Depends(get_order_service)],
):
    result = await order_service.get_order_detail(order_id, current_user.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="订单不存在或无权访问")
    return ApiResponse(data=result)


@router.get("/{order_id}/logistics", response_model=ApiResponse[dict], summary="订单物流")
async def get_order_logistics(
    order_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    order_service: Annotated[OrderService, Depends(get_order_service)],
):
    order = await order_service.get_order_detail(order_id, current_user.user_id)
    if not order:
        raise HTTPException(status_code=404, detail="订单不存在或无权访问")

    records: list[LogisticsResponse] = await order_service.get_order_logistics(order_id)
    return ApiResponse(data={"records": records})
