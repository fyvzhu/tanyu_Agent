"""
认证服务（异步版本）
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import (
    verify_password,
    create_access_token,
    create_refresh_token,
    hash_refresh_token,
    logger
)
from app.core.config import settings
from app.repositories import (
    UserRepository,
    UserAuthRepository,
    RefreshTokenSessionRepository
)
from app.schemas import TokenResponse, UserBasicInfo


class AuthService:
    """认证服务"""

    MAX_FAILED_ATTEMPTS = 5
    LOCK_DURATION_MINUTES = 30

    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.user_auth_repo = UserAuthRepository(db)

    async def login(self, username: str, password: str) -> tuple[TokenResponse, str]:
        """
        用户登录

        Args:
            username: 用户名或手机号
            password: 密码

        Returns:
            (TokenResponse, refresh_token): access_token 和刷新令牌

        Raises:
            ValueError: 登录失败
        """
        # 查找用户认证信息（先尝试用户名，再尝试手机号）
        user_auth = await self.user_auth_repo.get_by_username(username)

        # 如果通过用户名找不到，尝试通过手机号查找
        if not user_auth:
            user = await self.user_repo.get_by_phone(username)
            if user:
                user_auth = await self.user_auth_repo.get_by_user_id(user.user_id)

        if not user_auth:
            logger.warning(f"登录失败：用户不存在 {username}")
            raise ValueError("用户名或密码错误")

        # 检查账户是否被锁定
        if await self._is_account_locked(user_auth):
            remaining_time = self._get_remaining_lock_time(user_auth)
            raise ValueError(f"账户已被锁定，请在 {remaining_time} 分钟后重试")

        # 验证密码
        if not verify_password(password, user_auth.password_hash):
            logger.warning(f"登录失败：密码错误 {username}")
            await self._handle_login_failure(user_auth)
            raise ValueError("用户名或密码错误")

        # 检查用户状态
        if user_auth.status != "active":
            raise ValueError("账户已被禁用")

        # 登录成功，重置失败次数
        await self._reset_login_attempts(user_auth)

        # 查找用户基础信息
        user = await self.user_repo.get_by_user_id(user_auth.user_id)
        if not user:
            raise ValueError("用户信息不存在")

        # 生成 JWT access token
        access_token = create_access_token(
            data={"user_id": user.user_id, "username": user.username}
        )

        # 生成刷新令牌
        refresh_token = create_refresh_token()
        token_hash = hash_refresh_token(refresh_token)
        expires_at = datetime.now() + timedelta(days=settings.jwt_refresh_token_expire_days)

        # 存储刷新令牌会话
        refresh_repo = RefreshTokenSessionRepository(self.db)
        await refresh_repo.create(
            user_id=user.user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )

        # 更新最后登录时间
        user_auth.last_login_at = datetime.now()
        await self.db.commit()

        logger.info(f"用户登录成功：{username}")

        # 构造返回数据
        user_info = UserBasicInfo(
            user_id=user.user_id,
            username=user.username,
            nickname=user.nickname,
            level=user.level,
        )

        token_response = TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=user_info,
        )

        return token_response, refresh_token

    async def _is_account_locked(self, user_auth) -> bool:
        """检查账户是否被锁定"""
        if not user_auth.locked_until:
            return False

        # 检查锁定时间是否已过
        if datetime.now() >= user_auth.locked_until:
            # 自动解锁
            user_auth.locked_until = None
            user_auth.failed_login_count = 0
            await self.db.commit()
            return False

        return True

    def _get_remaining_lock_time(self, user_auth) -> int:
        """获取剩余锁定时间（分钟）"""
        if not user_auth.locked_until:
            return 0

        remaining = user_auth.locked_until - datetime.now()
        return max(1, int(remaining.total_seconds() / 60))

    async def _handle_login_failure(self, user_auth) -> None:
        """处理登录失败"""
        user_auth.failed_login_count += 1

        # 检查是否需要锁定账户
        if user_auth.failed_login_count >= self.MAX_FAILED_ATTEMPTS:
            user_auth.locked_until = datetime.now() + timedelta(minutes=self.LOCK_DURATION_MINUTES)
            logger.warning(f"账户被锁定：{user_auth.username}，失败次数：{user_auth.failed_login_count}")

        await self.db.commit()

    async def _reset_login_attempts(self, user_auth) -> None:
        """重置登录失败次数"""
        user_auth.failed_login_count = 0
        user_auth.locked_until = None
        await self.db.commit()

    async def register(
        self,
        username: str,
        nickname: str,
        password: str,
    ) -> tuple[TokenResponse, str]:
        """
        用户注册

        Args:
            username: 用户名
            nickname: 昵称
            password: 密码

        Returns:
            (TokenResponse, refresh_token): access_token 和刷新令牌

        Raises:
            ValueError: 注册失败
        """
        # 检查用户名是否已存在
        existing_user_auth = await self.user_auth_repo.get_by_username(username)
        if existing_user_auth:
            raise ValueError("用户名已存在")

        # 生成唯一 user_id
        from uuid import uuid4
        user_id = f"u{uuid4().hex[:8]}"

        # 创建用户基础信息
        user = await self.user_repo.create(
            user_id=user_id,
            username=username,
            nickname=nickname,
            level="普通用户",
        )

        # 创建用户认证信息（密码哈希）
        from app.core import hash_password
        password_hash = hash_password(password)
        await self.user_auth_repo.create(
            user_id=user_id,
            username=username,
            password_hash=password_hash,
            status="active",
        )

        await self.db.commit()

        logger.info(f"用户注册成功：{username} (user_id={user_id})")

        # 注册成功后自动登录，生成 token
        access_token = create_access_token(
            data={"user_id": user_id, "username": username}
        )

        # 生成刷新令牌
        refresh_token = create_refresh_token()
        token_hash = hash_refresh_token(refresh_token)
        expires_at = datetime.now() + timedelta(days=settings.jwt_refresh_token_expire_days)

        # 存储刷新令牌会话
        refresh_repo = RefreshTokenSessionRepository(self.db)
        await refresh_repo.create(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at
        )

        await self.db.commit()

        # 构造返回数据
        user_info = UserBasicInfo(
            user_id=user_id,
            username=username,
            nickname=nickname,
            level="普通用户",
        )

        token_response = TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=user_info,
        )

        return token_response, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> tuple[TokenResponse, str]:
        """
        使用刷新令牌获取新的访问令牌

        Args:
            refresh_token: 刷新令牌

        Returns:
            (TokenResponse, new_refresh_token): 新的访问令牌和刷新令牌

        Raises:
            ValueError: 刷新令牌无效或已过期
        """
        # 验证刷新令牌
        token_hash = hash_refresh_token(refresh_token)
        refresh_repo = RefreshTokenSessionRepository(self.db)
        session = await refresh_repo.get_by_token_hash(token_hash)

        if not session:
            logger.warning("刷新令牌无效或已过期")
            raise ValueError("刷新令牌无效或已过期")

        # 获取用户信息
        user = await self.user_repo.get_by_user_id(session.user_id)
        if not user:
            raise ValueError("用户不存在")

        # 撤销旧的刷新令牌
        await refresh_repo.revoke(session)

        # 生成新的访问令牌
        access_token = create_access_token(
            data={"user_id": user.user_id, "username": user.username}
        )

        # 生成新的刷新令牌（令牌轮换）
        new_refresh_token = create_refresh_token()
        new_token_hash = hash_refresh_token(new_refresh_token)
        expires_at = datetime.now() + timedelta(days=settings.jwt_refresh_token_expire_days)

        # 存储新的刷新令牌会话
        await refresh_repo.create(
            user_id=user.user_id,
            token_hash=new_token_hash,
            expires_at=expires_at
        )

        logger.info(f"刷新令牌成功：{user.username}")

        # 构造返回数据
        user_info = UserBasicInfo(
            user_id=user.user_id,
            username=user.username,
            nickname=user.nickname,
            level=user.level,
        )

        token_response = TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=user_info,
        )

        return token_response, new_refresh_token

    async def logout(self, refresh_token: str | None) -> None:
        """
        用户登出，撤销刷新令牌

        Args:
            refresh_token: 刷新令牌（可选）
        """
        if not refresh_token:
            return

        try:
            token_hash = hash_refresh_token(refresh_token)
            refresh_repo = RefreshTokenSessionRepository(self.db)
            session = await refresh_repo.get_by_token_hash(token_hash)

            if session:
                await refresh_repo.revoke(session)
                logger.info(f"用户登出成功：{session.user_id}")
        except Exception as e:
            logger.warning(f"登出时撤销令牌失败：{e}")
