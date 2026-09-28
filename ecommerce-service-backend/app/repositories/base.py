"""
Repository 基类
提供通用 CRUD 操作（异步版本）
"""
from __future__ import annotations

from typing import Generic, TypeVar, Type

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """基础 Repository（异步）"""

    def __init__(self, model: Type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get_by_id(self, id: int) -> ModelType | None:
        """根据主键 ID 获取"""
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
        )
        return result.scalar_one_or_none()

    async def get_all(self, skip: int = 0, limit: int = 100) -> list[ModelType]:
        """获取所有记录"""
        result = await self.db.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def create(self, obj: ModelType) -> ModelType:
        """创建记录"""
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelType) -> ModelType:
        """更新记录"""
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        """删除记录"""
        await self.db.delete(obj)
        await self.db.flush()

    async def commit(self) -> None:
        """提交事务"""
        await self.db.commit()

    async def rollback(self) -> None:
        """回滚事务"""
        await self.db.rollback()
