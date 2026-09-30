"""
TaskContextManager - Slice 01 Foundation
根据 01_slice_foundation 文档 #16 定义

核心职责：
- Task Stack 管理（纯确定性）
- start / continue / pause / resume / complete / cancel
- LIFO 栈操作
"""
from __future__ import annotations

import uuid
from typing import Literal

from loguru import logger

from customer_service.graph.state import (
    AgentState,
    TaskFrame,
    TaskStatus,
    TaskTransition,
)
from customer_service.intents.models import BusinessIntent


class TaskContextManager:
    """
    Task Stack 纯确定性管理器

    - 不调用 LLM
    - 不访问数据库
    - 只操作 AgentState 中的 Task 栈
    """

    MAX_PAUSED_TASKS = 3

    @staticmethod
    def _ensure_task_frame(task: TaskFrame | dict | None) -> TaskFrame | None:
        """
        确保 task 是 TaskFrame 对象，而不是 LangChain 序列化的字典

        从 Redis 恢复时，TaskFrame 会被序列化为：
        {'lc': 2, 'type': 'constructor', 'id': [...], 'kwargs': {...}}
        """
        if task is None:
            return None
        if isinstance(task, TaskFrame):
            return task
        if isinstance(task, dict):
            # LangChain 序列化格式
            if 'kwargs' in task:
                return TaskFrame(**task['kwargs'])
            # 普通字典格式
            return TaskFrame(**task)
        return task
    
    @staticmethod
    def start_task(
        state: AgentState,
        intent: BusinessIntent,
        turn_id: str,
    ) -> AgentState:
        """
        启动新 Task
        
        - 如果有 active_task，先暂停它
        - 创建新的 active_task
        """
        task_id = str(uuid.uuid4())
        
        new_task = TaskFrame(
            task_id=task_id,
            intent=intent,
            status=TaskStatus.ACTIVE,
            created_turn_id=turn_id,
            last_turn_id=turn_id,
        )
        
        # 如果有 active_task，先暂停
        old_task_id = None
        if state.get("active_task"):
            old_task = state["active_task"]
            old_task_id = old_task.task_id  # 保存旧任务 ID
            logger.info(
                f"📦 [TaskMgr] 暂停旧任务: task_id={old_task.task_id}, "
                f"intent={old_task.intent}"
            )

            # 检查 paused stack 是否已满
            paused_tasks = state.get("paused_tasks", [])
            if len(paused_tasks) >= TaskContextManager.MAX_PAUSED_TASKS:
                logger.warning(
                    f"⚠️ [TaskMgr] Paused stack 已满 "
                    f"({TaskContextManager.MAX_PAUSED_TASKS})，"
                    f"拒绝启动新任务"
                )
                # 不启动新任务，返回澄清信号
                state["task_transition"] = TaskTransition(
                    action="pause",
                    old_task_id=old_task.task_id,
                    new_task_id=None,
                    reason="max_paused_tasks_exceeded"
                )
                return state

            # 暂停旧任务
            old_task.paused_from_status = old_task.status
            old_task.status = TaskStatus.PAUSED
            old_task.pause_reason = "new_task_started"

            paused_tasks.append(old_task)
            state["paused_tasks"] = paused_tasks

        # 设置新任务为 active
        state["active_task"] = new_task
        state["task_transition"] = TaskTransition(
            action="start",
            old_task_id=old_task_id,
            new_task_id=task_id,
            reason="new_intent_recognized"
        )
        
        logger.info(
            f"✅ [TaskMgr] 启动新任务: task_id={task_id}, intent={intent}"
        )
        
        return state
    
    @staticmethod
    def continue_current(state: AgentState, turn_id: str) -> AgentState:
        """
        继续当前 Task
        
        - 更新 last_turn_id
        """
        if not state.get("active_task"):
            logger.warning("⚠️ [TaskMgr] 没有 active_task，无法继续")
            return state
        
        active_task = state["active_task"]
        active_task.last_turn_id = turn_id
        
        state["task_transition"] = TaskTransition(
            action="continue",
            old_task_id=None,
            new_task_id=active_task.task_id,
            reason="continuing_current_task"
        )
        
        logger.info(
            f"➡️ [TaskMgr] 继续当前任务: task_id={active_task.task_id}, "
            f"intent={active_task.intent}"
        )
        
        return state
    
    @staticmethod
    def complete_current(state: AgentState, turn_id: str) -> AgentState:
        """
        完成当前 Task

        - 将 active_task 标记为 COMPLETED
        - 如果有 paused_tasks，恢复最近的一个
        """
        if not state.get("active_task"):
            logger.warning("⚠️ [TaskMgr] 没有 active_task，无法完成")
            return state

        # 确保 active_task 是 TaskFrame 对象
        active_task = TaskContextManager._ensure_task_frame(state["active_task"])
        active_task.status = TaskStatus.COMPLETED
        active_task.last_turn_id = turn_id
        state["active_task"] = active_task
        
        # 保存快照
        state["completed_task_snapshot"] = active_task
        
        logger.info(
            f"✅ [TaskMgr] 完成任务: task_id={active_task.task_id}, "
            f"intent={active_task.intent}"
        )
        
        # 恢复 paused task
        paused_tasks = state.get("paused_tasks", [])
        if paused_tasks:
            # LIFO pop - 确保反序列化
            resumed_task = TaskContextManager._ensure_task_frame(paused_tasks.pop())
            resumed_task.status = resumed_task.paused_from_status or TaskStatus.ACTIVE
            resumed_task.paused_from_status = None
            resumed_task.pause_reason = None
            resumed_task.last_turn_id = turn_id

            state["active_task"] = resumed_task
            state["paused_tasks"] = paused_tasks
            state["resumed_task_snapshot"] = resumed_task
            state["resumed_this_turn"] = True

            logger.info(
                f"🔄 [TaskMgr] 恢复暂停任务: task_id={resumed_task.task_id}, "
                f"intent={resumed_task.intent}"
            )
        else:
            # 没有 paused task，清空 active
            state["active_task"] = None
            logger.info("📭 [TaskMgr] 所有任务已完成，无 paused task")

        # 获取新的 active_task 的 task_id（如果有的话）
        new_active = state.get("active_task")
        new_task_id = new_active.task_id if new_active else None

        state["task_transition"] = TaskTransition(
            action="complete",
            old_task_id=active_task.task_id,
            new_task_id=new_task_id,
            reason="task_completed"
        )

        return state

    @staticmethod
    def cancel_current(state: AgentState, turn_id: str, reason: str = "user_canceled") -> AgentState:
        """
        取消当前 Task

        - 将 active_task 标记为 CANCELED
        - 如果有 paused_tasks，恢复最近的一个
        """
        if not state.get("active_task"):
            logger.warning("⚠️ [TaskMgr] 没有 active_task，无法取消")
            return state

        # 确保 active_task 是 TaskFrame 对象
        active_task = TaskContextManager._ensure_task_frame(state["active_task"])
        active_task.status = TaskStatus.CANCELED
        active_task.last_turn_id = turn_id
        state["active_task"] = active_task

        logger.info(
            f"❌ [TaskMgr] 取消任务: task_id={active_task.task_id}, "
            f"intent={active_task.intent}, reason={reason}"
        )

        # 恢复 paused task（与 complete 逻辑相同）
        paused_tasks = state.get("paused_tasks", [])
        if paused_tasks:
            # 确保 paused_tasks 中的项也是 TaskFrame 对象
            resumed_task = TaskContextManager._ensure_task_frame(paused_tasks.pop())
            resumed_task.status = resumed_task.paused_from_status or TaskStatus.ACTIVE
            resumed_task.paused_from_status = None
            resumed_task.pause_reason = None
            resumed_task.last_turn_id = turn_id

            state["active_task"] = resumed_task
            state["paused_tasks"] = paused_tasks
            state["resumed_task_snapshot"] = resumed_task
            state["resumed_this_turn"] = True

            logger.info(
                f"🔄 [TaskMgr] 恢复暂停任务: task_id={resumed_task.task_id}, "
                f"intent={resumed_task.intent}"
            )
        else:
            state["active_task"] = None
            logger.info("📭 [TaskMgr] 任务已取消，无 paused task")

        # 获取新的 active_task 的 task_id（如果有的话）
        new_active = state.get("active_task")
        new_task_id = new_active.task_id if new_active else None

        state["task_transition"] = TaskTransition(
            action="cancel",
            old_task_id=active_task.task_id,
            new_task_id=new_task_id,
            reason=reason
        )

        return state

    @staticmethod
    def find_paused_by_intent(state: AgentState, intent: BusinessIntent) -> TaskFrame | None:
        """
        在 paused_tasks 中查找指定 Intent 的 Task
        """
        paused_tasks = state.get("paused_tasks", [])
        for task in paused_tasks:
            if task.intent == intent:
                return task
        return None
