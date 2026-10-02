"""
LangGraph 节点 - Tool Dispatch
根据 01_slice_foundation 文档 #13 定义

核心职责：
- 根据 Intent 和 Policy 调用相应的 Tool
- 执行 Flow（IntentFlowRegistry）
- 返回 FlowResult（统一 Schema）

P0 修复：从 config 获取 runtime context，不从 state 获取
P0-1 修复：统一使用 state["flow_result"]，不再使用 state["tool_result"]

阶段3修复（文档第72-77行）：
- 区分配置错误、下游故障、业务空结果
- 使用统一的 FlowStatus 枚举
- 不在此处调用 complete_current()（应在 Guard 检查后）
- 明确记录错误类型，不吞异常
"""
from __future__ import annotations

from typing import Any

from loguru import logger
from langgraph.types import RunnableConfig

from customer_service.graph.state import AgentState, TaskStatus
from customer_service.intents.models import BusinessIntent
from customer_service.flows import IntentFlowRegistry
from customer_service.flows.models import FlowResult, FlowStatus
from customer_service.context.runtime import AgentRuntimeContext
from customer_service.tools.models import ToolResult, ToolError


async def tool_dispatch_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    节点 3: Tool Dispatch

    逻辑：
    1. 检查 Task 状态是否为 READY
    2. 根据 Intent 调用对应的 Flow
    3. 执行 Tool 并返回结果

    阶段3修复：
    - 缺 runtime 返回 CONFIGURATION_ERROR（不只是跳过）
    - Flow 未注册返回 UNSUPPORTED_FLOW（不是 None）
    - 异常捕获后返回明确的错误状态（不只是字符串）
    - 不在此处调用 complete_current()（留给 Guard 后处理）
    """
    # 阶段3修复：从 config 提取 runtime，缺失时返回配置错误
    configurable = config.get("configurable", {})
    runtime: AgentRuntimeContext = configurable.get("runtime")

    turn_id = state.get("turn_id", "unknown")

    if not runtime:
        logger.error(f"[{turn_id}] ❌ config 中缺少 runtime context，这是配置错误")
        # 阶段3修复：返回明确的配置错误状态
        state["flow_result"] = FlowResult(
            ready_for_response=False,
            status=FlowStatus.CONFIGURATION_ERROR,
            dialogue_reason="configuration_error",
            tool_result=ToolResult(
                tool_name="system",
                ok=False,
                error=ToolError(
                    code="MISSING_RUNTIME",
                    message="Runtime context is required but not provided",
                    retryable=False
                )
            )
        )
        return state

    session_id = runtime.session_id
    active_task = state.get("active_task")

    logger.info(f"[{session_id}:{turn_id}] === 节点 3: Tool Dispatch 开始 ===")

    if not active_task:
        logger.warning(f"[{session_id}:{turn_id}] ⚠️ 没有 active_task，跳过 Tool Dispatch")
        return state

    # P0 修复: 处理从 Redis 恢复的 LangChain 序列化格式
    if isinstance(active_task, dict):
        from customer_service.tasking.models import TaskFrame
        # 检查是否是 LangChain 序列化格式 (包含 'lc', 'type', 'kwargs')
        if 'kwargs' in active_task and 'lc' in active_task:
            active_task = TaskFrame(**active_task['kwargs'])
        else:
            active_task = TaskFrame(**active_task)
        state["active_task"] = active_task

    # 检查 Task 状态
    if active_task.status != TaskStatus.READY:
        logger.info(f"[{session_id}:{turn_id}] Task 状态为 {active_task.status}，跳过 Tool Dispatch")
        state["flow_result"] = None
        return state

    # 获取 Intent 对应的 Flow
    intent_name = active_task.intent.value
    flow = IntentFlowRegistry.get(intent_name)

    # 阶段3修复：Flow 未注册返回 UNSUPPORTED_FLOW，不是 None
    if not flow:
        logger.warning(f"[{session_id}:{turn_id}] ⚠️ Intent {intent_name} 没有对应的 Flow，能力未开放")
        state["flow_result"] = FlowResult(
            ready_for_response=False,
            status=FlowStatus.UNSUPPORTED_FLOW,
            dialogue_reason="unsupported",
            tool_result=ToolResult(
                tool_name=intent_name,
                ok=False,
                error=ToolError(
                    code="FLOW_NOT_REGISTERED",
                    message=f"Intent '{intent_name}' has no registered Flow implementation",
                    retryable=False,
                    details={"intent": intent_name}
                )
            )
        )
        logger.info(f"[{session_id}:{turn_id}] === 节点 3: Tool Dispatch 完成（Flow未注册）===")
        return state

    # 执行 Flow
    try:
        logger.info(f"[{session_id}:{turn_id}] 🚀 执行 Flow: {intent_name}")
        flow_result = await flow.execute(state, runtime)

        state["flow_result"] = flow_result
        logger.info(f"[{session_id}:{turn_id}] ✅ Flow 执行完成: {intent_name}")

        # DEBUG: 记录 flow_result 的详细信息
        if flow_result:
            logger.info(f"[{session_id}:{turn_id}] [DEBUG] flow_result.status: {flow_result.status}")
            logger.info(f"[{session_id}:{turn_id}] [DEBUG] flow_result.ready_for_response: {flow_result.ready_for_response}")
            if flow_result.tool_result:
                logger.info(f"[{session_id}:{turn_id}] [DEBUG] tool_result.ok: {flow_result.tool_result.ok}")
                if flow_result.tool_result.error:
                    logger.warning(f"[{session_id}:{turn_id}] [DEBUG] tool_result.error: {flow_result.tool_result.error.code} - {flow_result.tool_result.error.message}")
            if flow_result.objects:
                logger.info(f"[{session_id}:{turn_id}] [DEBUG] objects count: {len(flow_result.objects)}")

            # 阶段3修复：不在这里调用 complete_current()
            # 根据文档第52行："在确认本轮成功且回复不会被 Guard 拒绝后，才调用 complete_current()"
            # 任务完成的判定应该在 response_gen + Guard 检查之后
        else:
            logger.warning(f"[{session_id}:{turn_id}] [DEBUG] flow_result is None!")

    except Exception as e:
        # 阶段3修复：异常捕获后返回明确的错误状态
        logger.error(f"[{session_id}:{turn_id}] ❌ Flow 执行异常: {intent_name} - {str(e)}", exc_info=True)

        # 判断是否可重试（简单规则：超时、网络错误可重试）
        error_msg = str(e).lower()
        retryable = any(keyword in error_msg for keyword in ["timeout", "503", "502", "connection", "network"])

        state["flow_result"] = FlowResult(
            ready_for_response=False,
            status=FlowStatus.RETRYABLE_ERROR if retryable else FlowStatus.PERMANENT_ERROR,
            dialogue_reason="error",
            tool_result=ToolResult(
                tool_name=intent_name,
                ok=False,
                error=ToolError(
                    code="FLOW_EXECUTION_ERROR",
                    message=str(e),
                    retryable=retryable,
                    details={"intent": intent_name, "exception_type": type(e).__name__}
                )
            )
        )

    logger.info(f"[{turn_id}] === 节点 3: Tool Dispatch 完成 ===")

    return state
