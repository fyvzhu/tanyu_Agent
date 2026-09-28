"""
用户相关 Repository（异步版本）
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import User, UserAuth, UserMeasurements, UserProfile, UserPreferences
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """用户 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(User, db)

    async def get_by_user_id(self, user_id: str) -> User | None:
        """根据业务 user_id 获取用户"""
        result = await self.db.execute(
            select(User).where(User.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """根据用户名获取用户"""
        result = await self.db.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_phone(self, phone_number: str) -> User | None:
        """根据手机号获取用户"""
        result = await self.db.execute(
            select(User).where(User.phone_number == phone_number)
        )
        return result.scalar_one_or_none()


class UserAuthRepository(BaseRepository[UserAuth]):
    """用户认证 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(UserAuth, db)

    async def get_by_username(self, username: str) -> UserAuth | None:
        """根据用户名获取认证信息"""
        result = await self.db.execute(
            select(UserAuth).where(UserAuth.username == username)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: str) -> UserAuth | None:
        """根据 user_id 获取认证信息"""
        result = await self.db.execute(
            select(UserAuth).where(UserAuth.user_id == user_id)
        )
        return result.scalar_one_or_none()


class UserMeasurementsRepository(BaseRepository[UserMeasurements]):
    """用户体型数据 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(UserMeasurements, db)

    async def get_by_user_id(self, user_id: str) -> UserMeasurements | None:
        """根据 user_id 获取体型数据"""
        result = await self.db.execute(
            select(UserMeasurements).where(UserMeasurements.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def delete_by_user_id(self, user_id: str) -> bool:
        """删除用户体型数据"""
        measurements = await self.get_by_user_id(user_id)
        if measurements:
            await self.delete(measurements)
            return True
        return False


class UserProfileRepository(BaseRepository[UserProfile]):
    """用户资料 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(UserProfile, db)

    async def get_by_user_id(self, user_id: str) -> UserProfile | None:
        """根据 user_id 获取用户资料"""
        result = await self.db.execute(
            select(UserProfile).where(UserProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()


class UserPreferencesRepository(BaseRepository[UserPreferences]):
    """用户偏好 Repository"""

    def __init__(self, db: AsyncSession):
        super().__init__(UserPreferences, db)

    async def get_by_user_id(self, user_id: str) -> UserPreferences | None:
        """根据 user_id 获取用户偏好"""
        result = await self.db.execute(
            select(UserPreferences).where(UserPreferences.user_id == user_id)
        )
        return result.scalar_one_or_none()
