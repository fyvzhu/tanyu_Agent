"""
Task Command Processor - 任务命令处理器

参考 ecommerce-customer-service/task/command/processor.py
设计原则：
- 统一的任务栈操作入口
- 命令模式：验证器输出命令，处理器执行命令
- 生成系统消息（中断提示、恢复提示等）

修复的问题：
- P0-5: 任务完成后调用 complete_current()
- P0-6: 闲聊不创建持久Task
"""
from __future__ import annotations

import uuid
from loguru import logger

from customer_service.graph.state import (
    AgentState,
    TaskFrame,
    TaskStatus,
    TaskTransition,
)
from customer_service.tasking.commands import (
    TaskCommand,
    StartTaskCommand,
    ContinueTaskCommand,
    SetSlotsCommand,
    ResumeTaskCommand,
    CancelTaskCommand,
    CompleteTaskCommand,
)
from customer_service.intents.models import BusinessIntent


class TaskCommandProcessor:
    """
    任务命令处理器
    
    参考 ecommerce-customer-service/CommandProcessor
    统一管理所有任务栈操作
    """
    
    MAX_PAUSED_TASKS = 3
    
    def run(
        self,
        state: AgentState,
        commands: list[TaskCommand],
        turn_id: str,
    ) -> AgentState:
        """
        执行命令列表
        
        Args:
            state: 当前状态
            commands: 命令列表
            turn_id: 当前轮次ID
            
        Returns:
            更新后的状态
        """
        for command in commands:
            state = self._apply(state, command, turn_id)
        return state
    
    def _apply(
        self,
        state: AgentState,
        command: TaskCommand,
        turn_id: str,
    ) -> AgentState:
        """
        应用单个命令
        """
        if isinstance(command, StartTaskCommand):
            return self._handle_start_task(state, command, turn_id)
        elif isinstance(command, ContinueTaskCommand):
            return self._handle_continue_task(state, turn_id)
        elif isinstance(command, SetSlotsCommand):
            return self._handle_set_slots(state, command)
        elif isinstance(command, ResumeTaskCommand):
            return self._handle_resume_task(state, command, turn_id)
        elif isinstance(command, CancelTaskCommand):
            return self._handle_cancel_task(state, command, turn_id)
        elif isinstance(command, CompleteTaskCommand):
            return self._handle_complete_task(state, turn_id)
        else:
            logger.warning(f"未知命令类型: {type(command)}")
            return state
    
    def _handle_start_task(
        self,
        state: AgentState,
        command: StartTaskCommand,
        turn_id: str,
    ) -> AgentState:
        """
        启动任务
        
        参考 CommandProcessor._handle_start_flow
        """
        task_id = str(uuid.uuid4())

        new_task = TaskFrame(
            task_id=task_id,
            intent=command.intent,
            status=TaskStatus.ACTIVE,
            created_turn_id=turn_id,
            last_turn_id=turn_id,
            slots=command.entities,  # 使用 slots 而不是 entities
        )
        
        # 检查是否有 active_task
        active_task = state.get("active_task")
        old_task_id = None
        
        if active_task:
            # 如果当前任务就是要启动的任务，不重复启动
            if active_task.intent == command.intent:
                logger.info(f"[CommandProcessor] 任务已存在，不重复启动: {command.intent.value}")
                return self._handle_continue_task(state, turn_id)
            
            old_task_id = active_task.task_id
            logger.info(
                f"[CommandProcessor] 中断当前任务: task_id={active_task.task_id}, "
                f"intent={active_task.intent.value}"
            )
            
            # 检查暂停栈是否已满
            paused_tasks = state.get("paused_tasks", [])
            if len(paused_tasks) >= self.MAX_PAUSED_TASKS:
                logger.warning(
                    f"[CommandProcessor] ⚠️ 暂停栈已满 ({self.MAX_PAUSED_TASKS})"
                )
                # 拒绝启动新任务，保持当前任务不变
                state["task_transition"] = TaskTransition(
                    action="continue",
                    old_task_id=None,
                    new_task_id=active_task.task_id,
                    reason="max_paused_tasks_exceeded"
                )
                # 生成系统消息提示栈满
                state["system_message"] = "抱歉，当前有太多未完成的任务，请先完成或取消一些任务后再试。"
                return state

            # 暂停当前任务
            active_task.paused_from_status = active_task.status
            active_task.status = TaskStatus.PAUSED
            active_task.pause_reason = "new_task_started"
            paused_tasks.append(active_task)
            state["paused_tasks"] = paused_tasks

            # 生成中断系统消息
            state["system_message"] = self._generate_interrupted_message(
                interrupted_intent=active_task.intent,
                started_intent=command.intent,
            )

        # 设置新任务为 active
        state["active_task"] = new_task
        state["task_transition"] = TaskTransition(
            action="start",
            old_task_id=old_task_id,
            new_task_id=task_id,
            reason="new_intent_recognized"
        )

        logger.info(
            f"[CommandProcessor] ✅ 启动任务: task_id={task_id}, intent={command.intent.value}"
        )

        return state

    def _handle_continue_task(
        self,
        state: AgentState,
        turn_id: str,
    ) -> AgentState:
        """继续当前任务"""
        active_task = state.get("active_task")
        if not active_task:
            logger.warning("[CommandProcessor] 没有 active_task，无法继续")
            return state

        active_task.last_turn_id = turn_id

        state["task_transition"] = TaskTransition(
            action="continue",
            old_task_id=None,
            new_task_id=active_task.task_id,
            reason="continuing_current_task"
        )

        logger.info(
            f"[CommandProcessor] ➡️ 继续任务: task_id={active_task.task_id}, "
            f"intent={active_task.intent.value}"
        )

        return state

    def _handle_set_slots(
        self,
        state: AgentState,
        command: SetSlotsCommand,
    ) -> AgentState:
        """设置槽位"""
        active_task = state.get("active_task")
        if not active_task:
            logger.warning("[CommandProcessor] 没有 active_task，无法设置槽位")
            return state

        # 更新槽位
        if not active_task.slots:
            active_task.slots = {}
        active_task.slots.update(command.slots)

        logger.info(
            f"[CommandProcessor] 📝 设置槽位: {list(command.slots.keys())}"
        )

        return state

    def _handle_resume_task(
        self,
        state: AgentState,
        command: ResumeTaskCommand,
        turn_id: str,
    ) -> AgentState:
        """
        恢复暂停任务

        参考 CommandProcessor._handle_resume_flow
        """
        paused_tasks = state.get("paused_tasks", [])

        # 确定要恢复的任务
        if command.intent:
            # 指定恢复某个意图
            target_task = None
            target_index = None
            for i, task in enumerate(paused_tasks):
                if task.intent == command.intent:
                    target_task = task
                    target_index = i
                    break

            if not target_task:
                logger.warning(f"[CommandProcessor] 未找到暂停的任务: {command.intent.value}")
                return state
        else:
            # 恢复栈顶（最近暂停的）
            if not paused_tasks:
                logger.warning("[CommandProcessor] 没有暂停的任务可恢复")
                return state
            target_task = paused_tasks[-1]
            target_index = len(paused_tasks) - 1

        # 如果有 active_task，需要先中断它
        active_task = state.get("active_task")
        old_task_id = None

        if active_task:
            # 如果要恢复的就是当前任务，直接返回
            if active_task.intent == target_task.intent:
                logger.info(f"[CommandProcessor] 任务已是活跃状态: {target_task.intent.value}")
                return state

            old_task_id = active_task.task_id

            # 中断当前任务
            active_task.paused_from_status = active_task.status
            active_task.status = TaskStatus.PAUSED
            active_task.pause_reason = "resume_other_task"
            paused_tasks.append(active_task)

            # 生成中断系统消息
            state["system_message"] = self._generate_interrupted_message(
                interrupted_intent=active_task.intent,
                started_intent=target_task.intent,
            )

        # 恢复目标任务
        paused_tasks.pop(target_index)
        target_task.status = target_task.paused_from_status or TaskStatus.ACTIVE
        target_task.paused_from_status = None
        target_task.pause_reason = None
        target_task.last_turn_id = turn_id

        state["active_task"] = target_task
        state["paused_tasks"] = paused_tasks
        state["resumed_task_snapshot"] = target_task
        state["resumed_this_turn"] = True

        state["task_transition"] = TaskTransition(
            action="resume",
            old_task_id=old_task_id,
            new_task_id=target_task.task_id,
            reason="resume_paused_task"
        )

        # 生成恢复系统消息
        if not old_task_id:
            state["system_message"] = f"好的，我们继续{self._intent_display_name(target_task.intent)}。"

        logger.info(
            f"[CommandProcessor] 🔄 恢复任务: task_id={target_task.task_id}, "
            f"intent={target_task.intent.value}"
        )

        return state

    def _handle_cancel_task(
        self,
        state: AgentState,
        command: CancelTaskCommand,
        turn_id: str,
    ) -> AgentState:
        """
        取消任务

        参考 CommandProcessor.handle_cancel_flow
        """
        active_task = state.get("active_task")
        if not active_task:
            logger.warning("[CommandProcessor] 没有 active_task，无法取消")
            return state

        active_task.status = TaskStatus.CANCELED
        active_task.last_turn_id = turn_id

        logger.info(
            f"[CommandProcessor] ❌ 取消任务: task_id={active_task.task_id}, "
            f"intent={active_task.intent.value}, reason={command.reason}"
        )

        # 恢复暂停任务
        paused_tasks = state.get("paused_tasks", [])
        new_task_id = None

        if paused_tasks:
            resumed_task = paused_tasks.pop()
            resumed_task.status = resumed_task.paused_from_status or TaskStatus.ACTIVE
            resumed_task.paused_from_status = None
            resumed_task.pause_reason = None
            resumed_task.last_turn_id = turn_id

            state["active_task"] = resumed_task
            state["paused_tasks"] = paused_tasks
            state["resumed_task_snapshot"] = resumed_task
            state["resumed_this_turn"] = True
            new_task_id = resumed_task.task_id

            # 生成恢复消息
            state["system_message"] = f"已取消。我们继续{self._intent_display_name(resumed_task.intent)}。"

            logger.info(
                f"[CommandProcessor] 🔄 恢复任务: task_id={resumed_task.task_id}, "
                f"intent={resumed_task.intent.value}"
            )
        else:
            state["active_task"] = None
            state["system_message"] = "已取消。"
            logger.info("[CommandProcessor] 📭 任务已取消，无暂停任务")

        state["task_transition"] = TaskTransition(
            action="cancel",
            old_task_id=active_task.task_id,
            new_task_id=new_task_id,
            reason=command.reason
        )

        return state

    def _handle_complete_task(
        self,
        state: AgentState,
        turn_id: str,
    ) -> AgentState:
        """
        完成任务（修复 P0-5）
        """
        active_task = state.get("active_task")
        if not active_task:
            logger.warning("[CommandProcessor] 没有 active_task，无法完成")
            return state

        active_task.status = TaskStatus.COMPLETED
        active_task.last_turn_id = turn_id
        state["completed_task_snapshot"] = active_task

        logger.info(
            f"[CommandProcessor] ✅ 完成任务: task_id={active_task.task_id}, "
            f"intent={active_task.intent.value}"
        )

        # 恢复暂停任务
        paused_tasks = state.get("paused_tasks", [])
        new_task_id = None

        if paused_tasks:
            resumed_task = paused_tasks.pop()
            resumed_task.status = resumed_task.paused_from_status or TaskStatus.ACTIVE
            resumed_task.paused_from_status = None
            resumed_task.pause_reason = None
            resumed_task.last_turn_id = turn_id

            state["active_task"] = resumed_task
            state["paused_tasks"] = paused_tasks
            state["resumed_task_snapshot"] = resumed_task
            state["resumed_this_turn"] = True
            new_task_id = resumed_task.task_id

            # 生成恢复消息
            state["system_message"] = f"好的。我们继续{self._intent_display_name(resumed_task.intent)}。"

            logger.info(
                f"[CommandProcessor] 🔄 恢复任务: task_id={resumed_task.task_id}, "
                f"intent={resumed_task.intent.value}"
            )
        else:
            state["active_task"] = None
            logger.info("[CommandProcessor] 📭 所有任务已完成")

        state["task_transition"] = TaskTransition(
            action="complete",
            old_task_id=active_task.task_id,
            new_task_id=new_task_id,
            reason="task_completed"
        )

        return state

    # ===== 辅助方法 =====

    @staticmethod
    def _generate_interrupted_message(
        interrupted_intent: BusinessIntent,
        started_intent: BusinessIntent,
    ) -> str:
        """生成中断系统消息"""
        interrupted_name = TaskCommandProcessor._intent_display_name(interrupted_intent)
        started_name = TaskCommandProcessor._intent_display_name(started_intent)
        return f"好的，{interrupted_name}稍后继续。现在先为您{started_name}。"

    @staticmethod
    def _intent_display_name(intent: BusinessIntent) -> str:
        """意图显示名称"""
        mapping = {
            BusinessIntent.PRODUCT_QUERY: "查询商品",
            BusinessIntent.SIZE_RECOMMEND: "推荐尺码",
            BusinessIntent.URGE_ORDER_PAYMENT: "催拍催付",
            BusinessIntent.URGE_SHIPPING: "催发货",
            BusinessIntent.PROMOTION_QUERY: "查询优惠",
            BusinessIntent.LOGISTICS_QUERY: "查询物流",
            BusinessIntent.RETURN: "退货",
            BusinessIntent.EXCHANGE: "换货",
            BusinessIntent.CHITCHAT: "闲聊",
        }
        return mapping.get(intent, intent.value)

