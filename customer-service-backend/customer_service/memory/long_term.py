"""
MySQL 长期结构化记忆 Provider
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import select, update, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service.memory.schemas import (
    MemoryFact,
    MemoryEvent,
    UserPreference,
    UserMeasurement,
    MemoryStatus,
)

logger = logging.getLogger(__name__)


class LongTermProvider(Protocol):
    """长期记忆 Provider 接口"""

    async def add_fact(self, fact: MemoryFact) -> bool:
        """添加记忆事实"""
        ...

    async def update_fact(self, memory_id: str, fact: MemoryFact) -> bool:
        """更新记忆事实"""
        ...

    async def get_facts(self, user_id: str, limit: int = 50) -> list[MemoryFact]:
        """获取用户的活跃记忆事实"""
        ...

    async def supersede_fact(self, memory_id: str, new_fact: MemoryFact) -> bool:
        """标记旧记忆为 superseded，插入新记忆"""
        ...

    async def delete_fact(self, memory_id: str) -> bool:
        """删除记忆（软删除）"""
        ...

    async def add_event(self, event: MemoryEvent) -> bool:
        """记录记忆变更事件"""
        ...

    async def get_preferences(self, user_id: str) -> list[UserPreference]:
        """获取用户偏好"""
        ...

    async def get_measurements(self, user_id: str) -> UserMeasurement | None:
        """获取用户身材数据"""
        ...


class MySQLLongTermProvider:
    """
    MySQL 长期记忆实现
    
    操作表：
    - user_memory_facts: 记忆事实
    - memory_events: 变更审计
    - user_preferences: 偏好
    - user_measurements: 身材数据
    """

    def __init__(self, session_factory):
        """
        Args:
            session_factory: async_sessionmaker[AsyncSession]
        """
        self.session_factory = session_factory

    async def add_fact(self, fact: MemoryFact) -> bool:
        """添加记忆事实到 user_memory_facts 表"""
        try:
            async with self.session_factory() as session:
                # 注意：这里需要实际的 SQLAlchemy ORM 模型
                # 暂时使用 text 方式插入（实际应该定义 ORM 模型）
                from sqlalchemy import text

                query = text("""
                    INSERT INTO user_memory_facts 
                    (memory_id, user_id, memory_type, memory_key, memory_text, 
                     value_json, confidence, importance, source, source_session_id, 
                     source_turn_id, status, expires_at, created_at, updated_at)
                    VALUES 
                    (:memory_id, :user_id, :memory_type, :memory_key, :memory_text,
                     :value_json, :confidence, :importance, :source, :source_session_id,
                     :source_turn_id, :status, :expires_at, :created_at, :updated_at)
                """)

                await session.execute(query, {
                    "memory_id": fact.memory_id,
                    "user_id": fact.user_id,
                    "memory_type": fact.memory_type.value,
                    "memory_key": fact.memory_key,
                    "memory_text": fact.memory_text,
                    "value_json": fact.value_json,
                    "confidence": fact.confidence,
                    "importance": fact.importance,
                    "source": fact.source.value,
                    "source_session_id": fact.source_session_id,
                    "source_turn_id": fact.source_turn_id,
                    "status": fact.status.value,
                    "expires_at": fact.expires_at,
                    "created_at": fact.created_at,
                    "updated_at": fact.updated_at,
                })
                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to add memory fact: {e}")
            return False

    async def update_fact(self, memory_id: str, fact: MemoryFact) -> bool:
        """更新记忆事实"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text

                query = text("""
                    UPDATE user_memory_facts 
                    SET memory_text = :memory_text,
                        value_json = :value_json,
                        confidence = :confidence,
                        importance = :importance,
                        updated_at = :updated_at
                    WHERE memory_id = :memory_id
                """)

                result = await session.execute(query, {
                    "memory_id": memory_id,
                    "memory_text": fact.memory_text,
                    "value_json": fact.value_json,
                    "confidence": fact.confidence,
                    "importance": fact.importance,
                    "updated_at": datetime.now(timezone.utc),
                })
                await session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to update memory fact: {e}")
            return False

    async def get_facts(self, user_id: str, limit: int = 50) -> list[MemoryFact]:
        """获取用户的活跃记忆事实"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text

                query = text("""
                    SELECT * FROM user_memory_facts
                    WHERE user_id = :user_id AND status = 'active'
                    ORDER BY importance DESC, created_at DESC
                    LIMIT :limit
                """)

                result = await session.execute(query, {"user_id": user_id, "limit": limit})
                rows = result.fetchall()

                facts = []
                for row in rows:
                    facts.append(MemoryFact(
                        memory_id=row.memory_id,
                        user_id=row.user_id,
                        memory_type=row.memory_type,
                        memory_key=row.memory_key,
                        memory_text=row.memory_text,
                        value_json=row.value_json,
                        confidence=row.confidence,
                        importance=row.importance,
                        source=row.source,
                        source_session_id=row.source_session_id,
                        source_turn_id=row.source_turn_id,
                        status=row.status,
                        expires_at=row.expires_at,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    ))
                return facts
        except Exception as e:
            logger.error(f"Failed to get memory facts: {e}")
            return []

    async def supersede_fact(self, memory_id: str, new_fact: MemoryFact) -> bool:
        """标记旧记忆为 superseded，插入新记忆"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text

                # 标记旧记忆
                update_query = text("""
                    UPDATE user_memory_facts
                    SET status = 'superseded', updated_at = :updated_at
                    WHERE memory_id = :memory_id
                """)
                await session.execute(update_query, {
                    "memory_id": memory_id,
                    "updated_at": datetime.now(timezone.utc),
                })

                # 插入新记忆
                insert_query = text("""
                    INSERT INTO user_memory_facts
                    (memory_id, user_id, memory_type, memory_key, memory_text,
                     value_json, confidence, importance, source, source_session_id,
                     source_turn_id, status, expires_at, created_at, updated_at)
                    VALUES
                    (:memory_id, :user_id, :memory_type, :memory_key, :memory_text,
                     :value_json, :confidence, :importance, :source, :source_session_id,
                     :source_turn_id, :status, :expires_at, :created_at, :updated_at)
                """)
                await session.execute(insert_query, {
                    "memory_id": new_fact.memory_id,
                    "user_id": new_fact.user_id,
                    "memory_type": new_fact.memory_type.value,
                    "memory_key": new_fact.memory_key,
                    "memory_text": new_fact.memory_text,
                    "value_json": new_fact.value_json,
                    "confidence": new_fact.confidence,
                    "importance": new_fact.importance,
                    "source": new_fact.source.value,
                    "source_session_id": new_fact.source_session_id,
                    "source_turn_id": new_fact.source_turn_id,
                    "status": new_fact.status.value,
                    "expires_at": new_fact.expires_at,
                    "created_at": new_fact.created_at,
                    "updated_at": new_fact.updated_at,
                })

                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to supersede memory fact: {e}")
            return False

    async def delete_fact(self, memory_id: str) -> bool:
        """删除记忆（软删除）"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text

                query = text("""
                    UPDATE user_memory_facts
                    SET status = 'deleted', updated_at = :updated_at
                    WHERE memory_id = :memory_id
                """)
                result = await session.execute(query, {
                    "memory_id": memory_id,
                    "updated_at": datetime.now(timezone.utc),
                })
                await session.commit()
                return result.rowcount > 0
        except Exception as e:
            logger.error(f"Failed to delete memory fact: {e}")
            return False

    async def add_event(self, event: MemoryEvent) -> bool:
        """记录记忆变更事件"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text

                query = text("""
                    INSERT INTO memory_events
                    (memory_id, action, old_value_json, new_value_json, source_turn_id, created_at)
                    VALUES
                    (:memory_id, :action, :old_value_json, :new_value_json, :source_turn_id, :created_at)
                """)
                await session.execute(query, {
                    "memory_id": event.memory_id,
                    "action": event.action,
                    "old_value_json": event.old_value_json,
                    "new_value_json": event.new_value_json,
                    "source_turn_id": event.source_turn_id,
                    "created_at": event.created_at,
                })
                await session.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to add memory event: {e}")
            return False

    async def get_preferences(self, user_id: str) -> list[UserPreference]:
        """获取用户偏好"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text

                query = text("""
                    SELECT * FROM user_preferences
                    WHERE user_id = :user_id AND active = 1
                    ORDER BY confidence DESC, updated_at DESC
                """)
                result = await session.execute(query, {"user_id": user_id})
                rows = result.fetchall()

                prefs = []
                for row in rows:
                    prefs.append(UserPreference(
                        id=row.id,
                        user_id=row.user_id,
                        preference_type=row.preference_type,
                        preference_value=row.preference_value,
                        confidence=row.confidence,
                        source=row.source,
                        active=row.active,
                        created_at=row.created_at,
                        updated_at=row.updated_at,
                    ))
                return prefs
        except Exception as e:
            logger.error(f"Failed to get user preferences: {e}")
            return []

    async def get_measurements(self, user_id: str) -> UserMeasurement | None:
        """获取用户身材数据"""
        try:
            async with self.session_factory() as session:
                from sqlalchemy import text

                query = text("""
                    SELECT * FROM user_measurements
                    WHERE user_id = :user_id
                    ORDER BY updated_at DESC
                    LIMIT 1
                """)
                result = await session.execute(query, {"user_id": user_id})
                row = result.fetchone()

                if row:
                    return UserMeasurement(
                        id=row.id,
                        user_id=row.user_id,
                        height_cm=row.height_cm,
                        weight_kg=row.weight_kg,
                        bust_cm=row.bust_cm,
                        waist_cm=row.waist_cm,
                        hip_cm=row.hip_cm,
                        shoulder_cm=row.shoulder_cm,
                        foot_length_cm=row.foot_length_cm,
                        foot_width_cm=row.foot_width_cm,
                        source=row.source,
                        updated_at=row.updated_at,
                    )
                return None
        except Exception as e:
            logger.error(f"Failed to get user measurements: {e}")
            return None
