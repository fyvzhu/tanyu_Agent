"""
Public API - 认证路由
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, Request

from app.dependencies import get_auth_service, get_current_user
from app.models import User
from app.services import AuthService
from app.schemas import (
    UserLoginRequest,
    UserRegisterRequest,
    TokenResponse,
    ApiResponse,
    UserBasicInfo,
)

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/register", response_model=ApiResponse[TokenResponse], summary="用户注册")
async def register(
    data: UserRegisterRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    用户注册接口

    - **username**: 用户名（4-20个字符）
    - **nickname**: 昵称
    - **password**: 密码（8-16个字符）
    - **confirm_password**: 确认密码

    返回 JWT Access Token，并在 HttpOnly Cookie 中设置 Refresh Token
    """
    # 验证两次密码是否一致
    if data.password != data.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")

    # 验证用户名格式（字母、数字、下划线）
    import re
    if not re.match(r'^[a-zA-Z0-9_]{4,20}$', data.username):
        raise HTTPException(status_code=400, detail="用户名只能包含字母、数字、下划线")

    try:
        token_response, refresh_token = await auth_service.register(
            username=data.username,
            nickname=data.nickname,
            password=data.password,
        )

        # 设置刷新令牌到 HttpOnly Cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,  # 生产环境需要 HTTPS
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7天
        )

        return ApiResponse(data=token_response)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=ApiResponse[TokenResponse], summary="用户登录")
async def login(
    data: UserLoginRequest,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    用户登录接口（简化版：只使用 username）

    - **username**: 用户名
    - **password**: 密码

    返回 JWT Access Token，并在 HttpOnly Cookie 中设置 Refresh Token
    """
    try:
        token_response, refresh_token = await auth_service.login(data.username, data.password)

        # 设置刷新令牌到 HttpOnly Cookie
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=True,  # 生产环境需要 HTTPS
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7天
        )

        return ApiResponse(data=token_response)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/refresh", response_model=ApiResponse[TokenResponse], summary="刷新 Token")
async def refresh_token(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    刷新访问令牌

    - 从 HttpOnly Cookie 读取 refresh_token
    - 验证并生成新的 access_token 和 refresh_token
    - 实现令牌轮换（token rotation）
    """
    # 从 Cookie 获取刷新令牌
    refresh_token_value = request.cookies.get("refresh_token")

    if not refresh_token_value:
        raise HTTPException(status_code=401, detail="refresh token 未提供")

    try:
        token_response, new_refresh_token = await auth_service.refresh_access_token(refresh_token_value)

        # 更新刷新令牌到 HttpOnly Cookie
        response.set_cookie(
            key="refresh_token",
            value=new_refresh_token,
            httponly=True,
            secure=True,  # 生产环境需要 HTTPS
            samesite="lax",
            max_age=7 * 24 * 60 * 60,  # 7天
        )

        return ApiResponse(data=token_response)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@router.post("/logout", response_model=ApiResponse[dict], summary="用户登出")
async def logout(
    request: Request,
    response: Response,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """
    用户登出（P0-18 修复）

    - 从 Cookie 读取 refresh_token
    - 调用 AuthService.logout() 撤销 DB 中的会话
    - 清除 Cookie

    确保 Refresh Token Rotation 完整闭环
    """
    # 从 Cookie 获取刷新令牌
    refresh_token_value = request.cookies.get("refresh_token")

    # 撤销刷新令牌会话（P0-18：必须撤销 DB session）
    await auth_service.logout(refresh_token_value)

    # 清除 Cookie
    response.delete_cookie("refresh_token")

    return ApiResponse(data={"logged_out": True})


@router.get("/me", response_model=ApiResponse[UserBasicInfo], summary="当前用户")
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    return ApiResponse(
        data=UserBasicInfo(
            user_id=current_user.user_id,
            username=current_user.username,
            nickname=current_user.nickname,
            level=current_user.level,
            phone_number_masked=(
                f"{current_user.phone_number[:3]}****{current_user.phone_number[-4:]}"
                if current_user.phone_number and len(current_user.phone_number) >= 7
                else current_user.phone_number
            ),
            email_masked=(
                f"{current_user.email[:1]}***@{current_user.email.split('@', 1)[1]}"
                if current_user.email and "@" in current_user.email
                else current_user.email
            ),
        )
    )
