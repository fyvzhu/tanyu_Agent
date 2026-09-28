from __future__ import annotations

from typing import Any

from customer_service.graph.state import AgentState


FACT_KEYWORDS = ("元", "库存", "有货", "缺货", "促销", "优惠", "退款", "物流")


def validate_grounding(
    state: AgentState | None = None,
    *,
    response: str = "",
    evidence: list[Any] | None = None,
    tool_result: dict[str, Any] | None = None,
    flow_result: Any | None = None,
) -> AgentState | bool:
    """
    Grounding validation helper.

    P1-47 修复：支持新的 FlowResult 契约
    - 从 flow_result.tool_result.evidence 提取证据
    - 统一设置 guard_status 而非 hallucination_detected

    - When called with ``state`` it mutates and returns AgentState.
    - When called with response/evidence/tool_result it returns a boolean for graph nodes.
    """
    # P1-47: 如果传入 flow_result，优先从中提取 evidence
    if flow_result is not None:
        if hasattr(flow_result, "tool_result") and flow_result.tool_result:
            evidence = flow_result.tool_result.evidence or []
            if not tool_result:
                tool_result = flow_result.tool_result.data or {}

    if state is not None:
        # P1-47: 工具执行错误时，直接放行（不强制要求证据）
        if state.get("tool_error"):
            state["guard_status"] = "pass"
            return state

        # P1-47: 从 state.flow_result 提取证据
        state_flow_result = state.get("flow_result")
        extracted_evidence: list[Any] = []
        if state_flow_result and hasattr(state_flow_result, "tool_result") and state_flow_result.tool_result:
            extracted_evidence = state_flow_result.tool_result.evidence or []

        # P1-47: 工具被调用但无证据时，触发 fallback
        if state.get("selected_tool") and not extracted_evidence and state.get("tool_result"):
            state["guard_status"] = "fallback"
            state["guard_errors"] = ["missing_evidence"]
            state["fallback_used"] = True
            state["response_text"] = "我暂时不能确认这些信息的来源，请稍后再试。"
            state["response_objects"] = []
            return state

        # P1-47: 正常情况，放行
        state["guard_status"] = "pass"
        return state

    # 布尔模式逻辑（用于简单的 Guard 节点条件判断）
    evidence = evidence or []
    if tool_result and not evidence:
        return False
    if any(keyword in response for keyword in FACT_KEYWORDS) and not evidence:
        return False
    return True
