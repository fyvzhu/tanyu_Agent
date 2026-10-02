"""
Task Command Models - 任务命令模型

参考 ecommerce-customer-service/task/command/models.py
设计原则：
- 命令是显式的、可验证的指令
- 每个命令类型对应一种任务栈操作
- 验证器输出命令，处理器执行命令
"""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field

from customer_service.intents.models import BusinessIntent


class TaskCommand(BaseModel):
    """任务命令基类"""
    command_type: str = Field(..., description="命令类型")


class StartTaskCommand(TaskCommand):
    """
    启动任务命令
    
    对应参考代码的 StartFlowCommand
    """
    command_type: Literal["start_task"] = "start_task"
    intent: BusinessIntent = Field(..., description="要启动的业务意图")
    entities: dict = Field(default_factory=dict, description="初始实体")


class ContinueTaskCommand(TaskCommand):
    """
    继续当前任务命令
    
    用户继续当前任务（提供槽位信息、确认等）
    """
    command_type: Literal["continue_task"] = "continue_task"


class SetSlotsCommand(TaskCommand):
    """
    设置槽位命令
    
    对应参考代码的 SetSlotsCommand
    """
    command_type: Literal["set_slots"] = "set_slots"
    slots: dict = Field(..., description="要设置的槽位")


class ResumeTaskCommand(TaskCommand):
    """
    恢复暂停任务命令
    
    对应参考代码的 ResumeFlowCommand
    """
    command_type: Literal["resume_task"] = "resume_task"
    intent: BusinessIntent | None = Field(None, description="要恢复的任务意图，None表示恢复栈顶")


class CancelTaskCommand(TaskCommand):
    """
    取消任务命令
    
    对应参考代码的 CancelFlowCommand
    """
    command_type: Literal["cancel_task"] = "cancel_task"
    reason: str = Field(default="user_canceled", description="取消原因")


class CompleteTaskCommand(TaskCommand):
    """
    完成任务命令
    
    参考代码没有显式的 CompleteCommand，但我们需要
    用于修复 P0-5（任务完成后不调用 complete_current）
    """
    command_type: Literal["complete_task"] = "complete_task"
