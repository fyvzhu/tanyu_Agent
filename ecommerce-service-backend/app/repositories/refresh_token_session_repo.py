"""
刷新令牌会话存储库
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth_session import RefreshTokenSession


class RefreshTokenSessionRepository:
    """刷新令牌会话存储库"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime
    ) -> RefreshTokenSession:
        """创建刷新令牌会话"""
        session = RefreshTokenSession(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            created_at=datetime.now(),
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_by_token_hash(self, token_hash: str) -> RefreshTokenSession | None:
        """根据令牌哈希获取会话"""
        result = await self.db.execute(
            select(RefreshTokenSession).where(
                and_(
                    RefreshTokenSession.token_hash == token_hash,
                    RefreshTokenSession.revoked_at.is_(None),
                    RefreshTokenSession.expires_at > datetime.now()
                )
            )
        )
        return result.scalar_one_or_none()

    async def revoke(self, session: RefreshTokenSession) -> None:
        """撤销令牌"""
        session.revoked_at = datetime.now()
        await self.db.commit()

    async def revoke_all_user_sessions(self, user_id: str) -> None:
        """撤销用户的所有会话"""
        result = await self.db.execute(
            select(RefreshTokenSession).where(
                and_(
                    RefreshTokenSession.user_id == user_id,
                    RefreshTokenSession.revoked_at.is_(None)
                )
            )
        )
        sessions = result.scalars().all()
        for session in sessions:
            session.revoked_at = datetime.now()
        await self.db.commit()

    async def cleanup_expired(self) -> int:
        """清理过期的令牌会话"""
        result = await self.db.execute(
            select(RefreshTokenSession).where(
                RefreshTokenSession.expires_at < datetime.now()
            )
        )
        sessions = result.scalars().all()
        for session in sessions:
            await self.db.delete(session)
        await self.db.commit()
        return len(sessions)
