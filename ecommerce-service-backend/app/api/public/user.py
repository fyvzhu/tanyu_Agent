"""
Public API - 用户路由
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_current_user, get_user_service
from app.services import UserService
from app.models import User
from app.schemas import (
    ApiResponse,
    UserProfileResponse,
    UserProfileUpdateRequest,
    UserPreferencesResponse,
    UserMeasurementsResponse,
    UserMeasurementsUpdateRequest,
)

router = APIRouter(prefix="/users/me", tags=["用户"])


@router.get("/profile", response_model=ApiResponse[UserProfileResponse], summary="获取用户资料")
async def get_profile(
    current_user: Annotated[User, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    获取当前登录用户的资料

    需要在 Header 中携带 Bearer Token
    """
    try:
        return ApiResponse(data=await user_service.get_user_profile(current_user.user_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/profile", response_model=ApiResponse[UserProfileResponse], summary="更新用户资料")
async def update_profile(
    data: UserProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    更新用户资料（昵称、邮箱、性别、生日）

    需要在 Header 中携带 Bearer Token
    """
    try:
        return ApiResponse(data=await user_service.update_profile(current_user.user_id, data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# 添加 /users/profile 路由（兼容前端路径）
profile_router = APIRouter(prefix="/users", tags=["用户"])

@profile_router.get("/profile", response_model=ApiResponse[UserProfileResponse], summary="获取用户资料")
async def get_user_profile_compat(
    current_user: Annotated[User, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """获取当前登录用户的资料（兼容路径）"""
    try:
        return ApiResponse(data=await user_service.get_user_profile(current_user.user_id))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@profile_router.put("/profile", response_model=ApiResponse[UserProfileResponse], summary="更新用户资料")
async def update_user_profile_compat(
    data: UserProfileUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """更新用户资料（兼容路径）"""
    try:
        return ApiResponse(data=await user_service.update_profile(current_user.user_id, data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/preferences", response_model=ApiResponse[UserPreferencesResponse], summary="获取用户显式偏好")
async def get_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return ApiResponse(data=UserPreferencesResponse(items=[]))


@router.put("/preferences", response_model=ApiResponse[UserPreferencesResponse], summary="更新用户显式偏好")
async def put_preferences(
    data: UserPreferencesResponse,
    current_user: Annotated[User, Depends(get_current_user)],
):
    return ApiResponse(data=data)


@router.get("/measurements", response_model=ApiResponse[UserMeasurementsResponse | None], summary="获取用户身体数据")
async def get_measurements(
    current_user: Annotated[User, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    获取用户身体测量数据
    
    需要在 Header 中携带 Bearer Token
    """
    result = await user_service.get_user_measurements(current_user.user_id)
    return ApiResponse(data=result)


@router.put("/measurements", response_model=ApiResponse[UserMeasurementsResponse], summary="更新用户身体数据")
async def update_measurements(
    data: UserMeasurementsUpdateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
):
    """
    更新用户身体测量数据
    
    需要在 Header 中携带 Bearer Token
    """
    try:
        return ApiResponse(data=await user_service.update_measurements(current_user.user_id, data))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
