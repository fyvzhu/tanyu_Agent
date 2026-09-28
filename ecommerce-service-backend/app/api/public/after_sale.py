"""
Public API - 订单售后动作路由
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user, get_after_sale_service
from app.models import User
from app.services import AfterSaleService
from app.schemas import (
    ApiResponse,
    ReturnRequestBody,
    ReturnRequestCreate,
    ReturnRequestResponse,
    ExchangeRequestBody,
    ExchangeRequestCreate,
    ExchangeRequestResponse,
    ShippingUrgeRequestBody,
    ShippingUrgeRequestCreate,
    ShippingUrgeRequestResponse,
)

router = APIRouter(prefix="/orders", tags=["售后"])


def _map_business_error(message: str) -> HTTPException:
    if "已有" in message or "重复" in message:
        return HTTPException(status_code=409, detail=message)
    if "无权" in message:
        return HTTPException(status_code=403, detail=message)
    if "不存在" in message:
        return HTTPException(status_code=404, detail=message)
    return HTTPException(status_code=422, detail=message)


@router.post("/{order_id}/return-requests", response_model=ApiResponse[ReturnRequestResponse], summary="退货退款")
async def create_return_request(
    order_id: str,
    data: ReturnRequestBody,
    current_user: Annotated[User, Depends(get_current_user)],
    after_sale_service: Annotated[AfterSaleService, Depends(get_after_sale_service)],
):
    try:
        result = await after_sale_service.create_return_request(
            current_user.user_id,
            ReturnRequestCreate(order_id=order_id, **data.model_dump()),
        )
        return ApiResponse(data=result)
    except ValueError as e:
        raise _map_business_error(str(e))


@router.post("/{order_id}/exchange-requests", response_model=ApiResponse[ExchangeRequestResponse], summary="换货")
async def create_exchange_request(
    order_id: str,
    data: ExchangeRequestBody,
    current_user: Annotated[User, Depends(get_current_user)],
    after_sale_service: Annotated[AfterSaleService, Depends(get_after_sale_service)],
):
    try:
        result = await after_sale_service.create_exchange_request(
            current_user.user_id,
            ExchangeRequestCreate(order_id=order_id, **data.model_dump()),
        )
        return ApiResponse(data=result)
    except ValueError as e:
        raise _map_business_error(str(e))


@router.post("/{order_id}/shipping-urge-requests", response_model=ApiResponse[ShippingUrgeRequestResponse], summary="催发货")
async def create_shipping_urge(
    order_id: str,
    data: ShippingUrgeRequestBody,
    current_user: Annotated[User, Depends(get_current_user)],
    after_sale_service: Annotated[AfterSaleService, Depends(get_after_sale_service)],
):
    try:
        result = await after_sale_service.create_shipping_urge(
            current_user.user_id,
            ShippingUrgeRequestCreate(order_id=order_id, **data.model_dump()),
        )
        return ApiResponse(data=result)
    except ValueError as e:
        raise _map_business_error(str(e))
