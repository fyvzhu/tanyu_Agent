"""
Redis Turn Lock - 防止同一 Session 并发写入
根据 01_slice_foundation 文档 #10 定义

核心约束：
- 每个 Session 同时只能处理一个 Turn
- 使用 Redis SET NX EX 实现分布式锁
- 锁超时时间：60 秒（防止死锁）

P1-49 修复：
- 并发冲突时立即返回 False，而不是等待 30 秒
- 使用独立的短 TTL（60秒），而不是复用 checkpoint 的长 TTL
"""
import asyncio
from typing import Optional

from loguru import logger
from redis.asyncio import Redis


class TurnLock:
    """
    Turn 级别的分布式锁
    
    防止同一 Session 并发写入 LangGraph Checkpoint
    """
    
    def __init__(self, redis: Redis, lock_timeout: int = 60):
        """
        Args:
            redis: Redis 客户端
            lock_timeout: 锁超时时间（秒），默认 60 秒
        """
        self.redis = redis
        self.lock_timeout = lock_timeout
    
    def _get_lock_key(self, session_id: str) -> str:
        """获取锁的 Redis Key"""
        return f"turn_lock:session:{session_id}"
    
    async def acquire(
        self,
        session_id: str,
        turn_id: str,
        timeout: float = 0.0,  # P1-49: 默认 0.0，立即返回
        poll_interval: float = 0.1
    ) -> bool:
        """
        获取 Turn Lock

        P1-49 修复：
        - timeout=0.0 表示立即返回，不等待
        - 返回 False 表示有其他 Turn 正在执行
        - 符合 Slice01 并发语义：第二个请求立即返回 409

        Args:
            session_id: Session ID
            turn_id: Turn ID（用于标识锁持有者）
            timeout: 等待超时时间（秒），默认 0.0（立即返回）
            poll_interval: 轮询间隔（秒），默认 0.1 秒

        Returns:
            True: 成功获取锁
            False: 锁已被占用（timeout=0 时）或超时未能获取锁（timeout>0 时）
        """
        lock_key = self._get_lock_key(session_id)

        # P1-49: 尝试获取锁（使用独立的短 TTL）
        acquired = await self.redis.set(
            lock_key,
            turn_id,
            nx=True,
            ex=self.lock_timeout  # 60 秒 TTL
        )

        if acquired:
            logger.debug(f"🔒 Turn Lock 已获取: session_id={session_id}, turn_id={turn_id}")
            return True

        # P1-49: 如果 timeout=0，立即返回 False
        if timeout <= 0:
            current_holder = await self.redis.get(lock_key)
            logger.warning(
                f"⏸️ Turn Lock 锁被占用，立即返回: session_id={session_id}, "
                f"holder={current_holder}, requester={turn_id}"
            )
            return False

        # 如果 timeout > 0，可以等待（保留兼容性，但默认不使用）
        start_time = asyncio.get_event_loop().time()

        while True:
            # 等待后重试
            await asyncio.sleep(poll_interval)

            # 再次尝试获取锁
            acquired = await self.redis.set(
                lock_key,
                turn_id,
                nx=True,
                ex=self.lock_timeout
            )

            if acquired:
                logger.debug(f"🔒 Turn Lock 已获取（等待后）: session_id={session_id}, turn_id={turn_id}")
                return True

            # 检查是否超时
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                current_holder = await self.redis.get(lock_key)
                logger.warning(
                    f"⚠️ Turn Lock 获取超时: session_id={session_id}, "
                    f"turn_id={turn_id}, current_holder={current_holder}, "
                    f"elapsed={elapsed:.2f}s"
                )
                return False
    
    async def release(self, session_id: str, turn_id: str) -> bool:
        """
        释放 Turn Lock
        
        只有持有锁的 Turn 才能释放（使用 Lua 脚本保证原子性）
        
        Args:
            session_id: Session ID
            turn_id: Turn ID（必须匹配当前锁持有者）
        
        Returns:
            True: 成功释放锁
            False: 锁不存在或持有者不匹配
        """
        lock_key = self._get_lock_key(session_id)
        
        # Lua 脚本：只有持有者才能释放锁
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        result = await self.redis.eval(lua_script, 1, lock_key, turn_id)
        
        if result == 1:
            logger.debug(f"🔓 Turn Lock 已释放: session_id={session_id}, turn_id={turn_id}")
            return True
        else:
            logger.warning(
                f"⚠️ Turn Lock 释放失败（持有者不匹配或锁已过期）: "
                f"session_id={session_id}, turn_id={turn_id}"
            )
            return False
    
    async def is_locked(self, session_id: str) -> tuple[bool, Optional[str]]:
        """
        检查 Session 是否被锁定
        
        Returns:
            (is_locked, holder_turn_id)
        """
        lock_key = self._get_lock_key(session_id)
        holder = await self.redis.get(lock_key)
        
        if holder:
            return True, holder.decode() if isinstance(holder, bytes) else holder
        else:
            return False, None
    
    async def force_release(self, session_id: str) -> bool:
        """
        强制释放锁（危险操作，仅用于异常恢复）
        
        Returns:
            True: 锁已删除
            False: 锁不存在
        """
        lock_key = self._get_lock_key(session_id)
        result = await self.redis.delete(lock_key)
        
        if result > 0:
            logger.warning(f"⚠️ Turn Lock 已强制释放: session_id={session_id}")
            return True
        else:
            return False


class TurnLockContext:
    """
    Turn Lock 上下文管理器
    
    使用方式:
    ```python
    async with TurnLockContext(turn_lock, session_id, turn_id):
        # 执行需要锁保护的操作
        pass
    ```
    """
    
    def __init__(
        self,
        turn_lock: TurnLock,
        session_id: str,
        turn_id: str,
        timeout: float = 0.0  # P1-49: 默认立即返回
    ):
        self.turn_lock = turn_lock
        self.session_id = session_id
        self.turn_id = turn_id
        self.timeout = timeout
        self.acquired = False
    
    async def __aenter__(self):
        """进入上下文：获取锁"""
        self.acquired = await self.turn_lock.acquire(
            self.session_id,
            self.turn_id,
            timeout=self.timeout
        )
        
        if not self.acquired:
            raise TimeoutError(
                f"无法获取 Turn Lock: session_id={self.session_id}, "
                f"turn_id={self.turn_id}, timeout={self.timeout}s"
            )
        
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """退出上下文：释放锁"""
        if self.acquired:
            await self.turn_lock.release(self.session_id, self.turn_id)
        
        # 不抑制异常
        return False
