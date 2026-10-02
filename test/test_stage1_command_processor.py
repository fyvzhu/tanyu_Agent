"""
阶段1测试：CommandProcessor（任务栈统一管理）

测试验证 CommandProcessor 的核心功能：
1. 启动任务
2. 中断和恢复
3. 栈满拒绝
4. 取消任务
5. 完成任务（修复 P0-5）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "customer-service-backend"))

import pytest
from customer_service.tasking.command_processor import TaskCommandProcessor
from customer_service.tasking.commands import (
    StartTaskCommand,
    CancelTaskCommand,
    CompleteTaskCommand,
)
from customer_service.intents.models import BusinessIntent
from customer_service.graph.state import AgentState, TaskStatus


def test_start_task_command():
    """测试：启动任务"""
    processor = TaskCommandProcessor()
    state: AgentState = {"turn_id": "test_001"}
    
    commands = [
        StartTaskCommand(intent=BusinessIntent.PRODUCT_QUERY, entities={"color": "红色"})
    ]
    
    state = processor.run(state, commands, "test_001")
    
    # 验证任务已启动
    assert state.get("active_task") is not None
    assert state["active_task"].intent == BusinessIntent.PRODUCT_QUERY
    assert state["active_task"].slots.get("color") == "红色"
    assert state["active_task"].status == TaskStatus.ACTIVE
    print("✅ 启动任务测试通过")


def test_interrupt_task():
    """测试：中断任务"""
    processor = TaskCommandProcessor()
    state: AgentState = {"turn_id": "test_002"}
    
    # 启动第一个任务
    commands1 = [StartTaskCommand(intent=BusinessIntent.PRODUCT_QUERY, entities={})]
    state = processor.run(state, commands1, "test_002")
    task1_id = state["active_task"].task_id
    
    # 启动第二个任务，应该中断第一个
    commands2 = [StartTaskCommand(intent=BusinessIntent.PROMOTION_QUERY, entities={})]
    state = processor.run(state, commands2, "test_003")
    
    # 验证第一个任务被暂停
    assert len(state.get("paused_tasks", [])) == 1
    assert state["paused_tasks"][0].task_id == task1_id
    assert state["paused_tasks"][0].status == TaskStatus.PAUSED
    
    # 验证第二个任务是活跃的
    assert state["active_task"].intent == BusinessIntent.PROMOTION_QUERY
    print("✅ 中断任务测试通过")


def test_stack_full_rejection():
    """测试：栈满拒绝"""
    processor = TaskCommandProcessor()
    state: AgentState = {"turn_id": "test_003", "paused_tasks": []}
    
    # 启动第一个任务
    commands1 = [StartTaskCommand(intent=BusinessIntent.PRODUCT_QUERY, entities={})]
    state = processor.run(state, commands1, "test_003")
    
    # 启动第2、3、4个任务，填满栈
    for i, intent in enumerate([
        BusinessIntent.PROMOTION_QUERY,
        BusinessIntent.LOGISTICS_QUERY,
        BusinessIntent.URGE_ORDER_PAYMENT,
    ]):
        commands = [StartTaskCommand(intent=intent, entities={})]
        state = processor.run(state, commands, f"test_00{4+i}")
    
    # 此时应该有3个暂停任务
    assert len(state.get("paused_tasks", [])) == 3
    
    # 尝试启动第5个任务，应该被拒绝
    commands5 = [StartTaskCommand(intent=BusinessIntent.SIZE_RECOMMEND, entities={})]
    state = processor.run(state, commands5, "test_007")

    # 验证仍然是第4个任务，第5个未启动
    assert state["active_task"].intent == BusinessIntent.URGE_ORDER_PAYMENT
    assert len(state.get("paused_tasks", [])) == 3
    assert state["task_transition"].action == "continue"  # 保持当前任务
    assert "max_paused_tasks_exceeded" in state["task_transition"].reason
    assert "system_message" in state
    print("✅ 栈满拒绝测试通过")


def test_cancel_task():
    """测试：取消任务"""
    processor = TaskCommandProcessor()
    state: AgentState = {"turn_id": "test_004"}
    
    # 启动两个任务
    commands1 = [StartTaskCommand(intent=BusinessIntent.PRODUCT_QUERY, entities={})]
    state = processor.run(state, commands1, "test_004")
    
    commands2 = [StartTaskCommand(intent=BusinessIntent.PROMOTION_QUERY, entities={})]
    state = processor.run(state, commands2, "test_005")
    
    # 取消当前任务
    commands_cancel = [CancelTaskCommand(reason="user_canceled")]
    state = processor.run(state, commands_cancel, "test_006")
    
    # 验证第二个任务被取消，第一个任务恢复
    assert state["active_task"].intent == BusinessIntent.PRODUCT_QUERY
    assert state["active_task"].status == TaskStatus.ACTIVE
    assert len(state.get("paused_tasks", [])) == 0
    print("✅ 取消任务测试通过")


def test_complete_task():
    """测试：完成任务（修复 P0-5）"""
    processor = TaskCommandProcessor()
    state: AgentState = {"turn_id": "test_005"}
    
    # 启动两个任务
    commands1 = [StartTaskCommand(intent=BusinessIntent.PRODUCT_QUERY, entities={})]
    state = processor.run(state, commands1, "test_005")
    
    commands2 = [StartTaskCommand(intent=BusinessIntent.PROMOTION_QUERY, entities={})]
    state = processor.run(state, commands2, "test_006")
    
    # 完成当前任务
    commands_complete = [CompleteTaskCommand()]
    state = processor.run(state, commands_complete, "test_007")
    
    # 验证第二个任务被完成，第一个任务恢复
    assert state["completed_task_snapshot"].intent == BusinessIntent.PROMOTION_QUERY
    assert state["completed_task_snapshot"].status == TaskStatus.COMPLETED
    assert state["active_task"].intent == BusinessIntent.PRODUCT_QUERY
    assert state["active_task"].status == TaskStatus.ACTIVE
    print("✅ 完成任务测试通过（P0-5修复）")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
