"""
LangGraph 节点 - Tool Dispatch
根据 01_slice_foundation 文档 #13 定义

核心职责：
- 根据 Intent 和 Policy 调用相应的 Tool
- 执行 Flow（IntentFlowRegistry）
- 返回 FlowResult（统一 Schema）

P0 修复：从 config 获取 runtime context，不从 state 获取
P0-1 修复：统一使用 state["flow_result"]，不再使用 state["tool_result"]
"""
from __future__ import annotations

from typing import Any

from loguru import logger
from langgraph.types import RunnableConfig

from customer_service.graph.state import AgentState, TaskStatus
from customer_service.intents.models import BusinessIntent
from customer_service.flows import IntentFlowRegistry
from customer_service.context.runtime import AgentRuntimeContext


async def tool_dispatch_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    节点 3: Tool Dispatch

    逻辑：
    1. 检查 Task 状态是否为 READY
    2. 根据 Intent 调用对应的 Flow
    3. 执行 Tool 并返回结果

    Slice 02 完整版：
    - 调用 IntentFlowRegistry 获取对应的 Flow
    - 执行 Flow.execute(state, runtime)
    - 将结果存入 state["tool_result"]

    P0-1 修复：从 config["configurable"]["runtime"] 获取完整的 AgentRuntimeContext
    """
    # P0-1 修复：从 config 提取完整的 runtime context
    configurable = config.get("configurable", {})
    runtime: AgentRuntimeContext = configurable.get("runtime")

    if not runtime:
        logger.error("❌ config 中缺少 runtime context，无法执行 Tool Dispatch")
        return state

    turn_id = state.get("turn_id", "unknown")
    session_id = runtime.session_id
    active_task = state.get("active_task")

    logger.info(f"[{session_id}:{turn_id}] === 节点 3: Tool Dispatch 开始 ===")

    if not active_task:
        logger.warning(f"[{session_id}:{turn_id}] ⚠️ 没有 active_task，跳过 Tool Dispatch")
        return state

    # 检查 Task 状态
    if active_task.status != TaskStatus.READY:
        logger.info(f"[{session_id}:{turn_id}] Task 状态为 {active_task.status}，跳过 Tool Dispatch")
        state["flow_result"] = None
        return state

    # 获取 Intent 对应的 Flow
    intent_name = active_task.intent.value
    flow = IntentFlowRegistry.get(intent_name)

    if not flow:
        logger.warning(f"[{session_id}:{turn_id}] ⚠️ Intent {intent_name} 没有对应的 Flow，跳过")
        state["flow_result"] = None
        logger.info(f"[{session_id}:{turn_id}] === 节点 3: Tool Dispatch 完成 ===")
        return state

    # 执行 Flow（P0 修复：传递 runtime）
    try:
        logger.info(f"[{session_id}:{turn_id}] 🚀 执行 Flow: {intent_name}")
        flow_result = await flow.execute(state, runtime)

        # P0-1 修复：统一使用 state["flow_result"]
        state["flow_result"] = flow_result
        logger.info(f"[{session_id}:{turn_id}] ✅ Flow 执行成功: {intent_name}")

        # DEBUG: 记录 flow_result 的详细信息
        if flow_result:
            logger.info(f"[{session_id}:{turn_id}] [DEBUG] flow_result type: {type(flow_result)}")
            logger.info(f"[{session_id}:{turn_id}] [DEBUG] flow_result.ready_for_response: {flow_result.ready_for_response}")
            if flow_result.tool_result:
                logger.info(f"[{session_id}:{turn_id}] [DEBUG] flow_result.tool_result exists")
            if flow_result.objects:
                logger.info(f"[{session_id}:{turn_id}] [DEBUG] flow_result.objects count: {len(flow_result.objects)}")
        else:
            logger.warning(f"[{session_id}:{turn_id}] [DEBUG] flow_result is None!")

    except Exception as e:
        logger.error(f"[{session_id}:{turn_id}] ❌ Flow 执行失败: {intent_name} - {e}", exc_info=True)
        state["flow_result"] = None
        state["tool_error"] = str(e)

    logger.info(f"[{turn_id}] === 节点 3: Tool Dispatch 完成 ===")

    return state
