"""
Chat Repository - 数据访问层
根据 01_slice_foundation 文档 #10 定义

核心约束：
- 强制用户隔离（Ownership Check）
- 禁止跨用户访问
"""
import json
import uuid
from datetime import datetime
from typing import Optional

from loguru import logger
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service.models.chat import ChatSession, ChatMessage, MessageRole
from customer_service.context import AuthPrincipal


class ChatRepository:
    """
    Chat 数据访问层
    
    强制用户隔离：
    - 所有查询都必须带 user_id 过滤
    - 禁止跨用户访问
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    # ==================== Session 操作 ====================
    
    async def create_session(
        self,
        session_id: str,
        user_id: str,
        metadata: Optional[dict] = None
    ) -> ChatSession:
        """创建新 Session"""
        logger.info(f"📝 创建 Session: session_id={session_id}, user_id={user_id}")
        
        chat_session = ChatSession(
            id=session_id,
            user_id=user_id,
            channel=(metadata or {}).get("channel", "web"),
            status="active",
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            last_active_at=datetime.utcnow(),
        )
        
        self.session.add(chat_session)
        await self.session.commit()
        await self.session.refresh(chat_session)
        
        logger.info(f"✅ Session 创建成功: {session_id}")
        return chat_session
    
    async def get_session(
        self,
        session_id: str,
        principal: AuthPrincipal
    ) -> Optional[ChatSession]:
        """
        获取 Session（强制用户隔离）
        
        Args:
            session_id: Session ID
            principal: 认证主体（用于 Ownership Check）
        
        Returns:
            ChatSession 或 None（不存在或无权限）
        """
        stmt = select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == principal.user_id  # 强制用户隔离
        )
        result = await self.session.execute(stmt)
        session = result.scalar_one_or_none()
        
        if session is None:
            logger.warning(f"⚠️ Session 不存在或无权限: session_id={session_id}, user_id={principal.user_id}")
        
        return session
    
    async def list_sessions(
        self,
        principal: AuthPrincipal,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[list[ChatSession], int]:
        """
        列出用户的所有 Session（按最后活跃时间排序）

        Returns:
            (sessions, total): 会话列表和总数
        """
        # 查询总数
        count_stmt = (
            select(func.count(ChatSession.id))
            .where(ChatSession.user_id == principal.user_id)
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        # 查询会话列表（按 last_active_at 降序）
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == principal.user_id)
            .order_by(ChatSession.last_active_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        sessions = list(result.scalars().all())

        return sessions, total

    async def get_first_user_message(self, session_id: str) -> Optional[str]:
        """获取会话的第一条用户消息内容（用于生成标题）"""
        stmt = (
            select(ChatMessage.text)
            .where(
                ChatMessage.session_id == session_id,
                ChatMessage.role == MessageRole.USER
            )
            .order_by(ChatMessage.created_at.asc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        message_text = result.scalar_one_or_none()
        return message_text
    
    async def close_session(
        self,
        session_id: str,
        principal: AuthPrincipal
    ) -> bool:
        """
        关闭 Session（强制用户隔离）

        Returns:
            True: 关闭成功
            False: Session 不存在或无权限
        """
        session = await self.get_session(session_id, principal)
        if session is None:
            return False

        session.status = "closed"
        session.updated_at = datetime.utcnow()
        await self.session.commit()
        logger.info(f"Session 已关闭: {session_id}")
        return True

    async def delete_session(self, session_id: str, principal: AuthPrincipal) -> bool:
        """兼容旧调用名：Contract 语义为关闭 session，不物理删除。"""
        return await self.close_session(session_id, principal)
    
    # ==================== Message 操作 ====================
    
    async def add_message(
        self,
        session_id: str,
        role: MessageRole,
        content: str,
        principal: AuthPrincipal,
        metadata: Optional[dict] = None,
        objects_json: Optional[str] = None  # 问题修复2：支持直接传递已序列化的对象
    ) -> Optional[ChatMessage]:
        """
        添加消息（强制 Ownership Check）

        Args:
            objects_json: 已序列化的对象 JSON 字符串（优先使用）

        Returns:
            ChatMessage 或 None（Session 不存在或无权限）
        """
        # 先检查 Session Ownership
        session = await self.get_session(session_id, principal)
        if session is None:
            logger.error(f"❌ 无法添加消息：Session 不存在或无权限: {session_id}")
            return None
        if session.status == "closed":
            logger.warning(f"无法添加消息：Session 已关闭: {session_id}")
            return None

        metadata = metadata or {}
        turn_id = str(metadata.get("turn_id") or uuid.uuid4())

        # 问题修复2：优先使用传入的 objects_json，否则从 metadata 获取
        if objects_json is None:
            objects_json = json.dumps(metadata.get("objects", []), ensure_ascii=False)

        message = ChatMessage(
            message_id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=principal.user_id,
            turn_id=turn_id,
            role=role,
            content=content,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
            objects_json=objects_json,
            created_at=datetime.utcnow()
        )
        
        self.session.add(message)
        
        # 更新 Session 的 updated_at
        session.updated_at = datetime.utcnow()
        session.last_active_at = datetime.utcnow()
        
        await self.session.commit()
        await self.session.refresh(message)
        
        logger.debug(f"💬 消息已添加: session_id={session_id}, role={role}")
        return message
    
    async def get_messages(
        self,
        session_id: str,
        principal: AuthPrincipal,
        limit: int = 50,
        after_message_id: int | None = None
    ) -> list[ChatMessage]:
        """
        获取 Session 的消息历史（强制 Ownership Check）

        P1-34 修复：支持 cursor-based pagination

        Args:
            session_id: Session ID
            principal: 认证主体
            limit: 返回数量限制
            after_message_id: 游标（返回此 ID 之后的消息）

        Returns:
            消息列表（按时间正序）
            空列表（Session 不存在或无权限）
        """
        # 先检查 Session Ownership
        session = await self.get_session(session_id, principal)
        if session is None:
            logger.warning(f"⚠️ 无法获取消息：Session 不存在或无权限: {session_id}")
            return []

        stmt = (
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id, ChatMessage.user_id == principal.user_id)
        )

        # P1-34: 如果有 cursor，添加过滤条件
        if after_message_id is not None:
            stmt = stmt.where(ChatMessage.id > after_message_id)

        stmt = stmt.order_by(ChatMessage.created_at.asc()).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    
    async def count_messages(
        self,
        session_id: str,
        principal: AuthPrincipal
    ) -> int:
        """统计 Session 的消息数量（强制 Ownership Check）"""
        # 先检查 Session Ownership
        session = await self.get_session(session_id, principal)
        if session is None:
            return 0
        
        stmt = select(func.count(ChatMessage.id)).where(
            ChatMessage.session_id == session_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()
