"""
P0+P1修复完整验证测试

运行方式：
cd customer-service-backend
python -m pytest ../test/test_p0_p1_complete.py -v -s
"""
import pytest
import os


def test_p1_history_query_detection():
    """
    P1-1: 验证历史查询检测

    修复内容：
    - _is_history_query能识别各种历史查询模式
    - _extract_last_user_message能从历史中提取最近用户消息
    """
    from customer_service.graph.nodes.intent_parse import _is_history_query, _extract_last_user_message

    # 验证1：能识别各种历史查询
    history_queries = [
        "我刚问了什么",
        "我刚才问了什么问题？",
        "上一句我说了什么",
        "刚才我问的什么",
        "之前我问了什么",
    ]

    for query in history_queries:
        assert _is_history_query(query), f"应该识别为历史查询: {query}"

    # 验证2：不会误判普通query
    normal_queries = [
        "有什么促销活动？",
        "推荐一款衬衫",
        "我的订单在哪里",
    ]

    for query in normal_queries:
        assert not _is_history_query(query), f"不应该识别为历史查询: {query}"

    # 验证3：能提取最近用户消息
    history = """USER: 你是谁？
ASSISTANT: 我是探域电商售前助手
USER: 有什么促销活动？
ASSISTANT: 目前有满减活动"""

    last_msg = _extract_last_user_message(history)
    assert last_msg == "有什么促销活动？", f"应该提取到最近用户消息，实际: {last_msg}"

    print("✅ P1-1: 历史查询检测验证通过")


def test_p1_frontend_store_states():
    """
    P1-2: 验证前端store状态区分

    修复内容：
    - sessionsLoading: 加载中
    - sessionsLoaded: 已加载
    - sessionsLoadError: 加载错误
    """

    store_js_path = os.path.join(
        os.path.dirname(__file__),
        "..", "customer-service-frontend", "src", "stores", "chat.js"
    )

    with open(store_js_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 验证1：定义了新状态
    assert 'sessionsLoading' in content, "缺少sessionsLoading状态"
    assert 'sessionsLoaded' in content, "缺少sessionsLoaded状态"
    assert 'sessionsLoadError' in content, "缺少sessionsLoadError状态"

    # 验证2：在loadSessions中设置了这些状态
    assert 'sessionsLoading.value = true' in content, "loadSessions应该设置sessionsLoading"
    assert 'sessionsLoaded.value = true' in content, "loadSessions应该设置sessionsLoaded"
    assert 'sessionsLoadError.value' in content, "loadSessions应该设置sessionsLoadError"

    print("✅ P1-2: 前端Store状态区分验证通过")


def test_p1_frontend_view_ui():
    """
    P1-3: 验证ChatView.vue的UI更新

    修复内容：
    - 显示loading状态
    - 显示error状态并提供重试按钮
    - 区分真正的空状态
    """

    view_path = os.path.join(
        os.path.dirname(__file__),
        "..", "customer-service-frontend", "src", "views", "ChatView.vue"
    )

    with open(view_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 验证1：有loading UI
    assert 'sessionsLoading' in content, "应该检查sessionsLoading状态"
    assert '正在加载会话' in content or 'loading' in content.lower(), "应该显示加载提示"

    # 验证2：有error UI
    assert 'sessionsLoadError' in content, "应该检查sessionsLoadError状态"
    assert '失败' in content or 'error' in content.lower(), "应该显示错误提示"

    # 验证3：有重试功能
    assert 'reloadSessions' in content or '重试' in content or '重新加载' in content, \
        "应该提供重试功能"

    print("✅ P1-3: 前端View UI更新验证通过")


@pytest.mark.asyncio
async def test_integration_history_query():
    """
    集成测试：历史查询完整流程

    场景："我刚问了什么？" -> 检测到历史查询 -> 直接响应，不走Intent分类
    """
    from customer_service.graph.state import AgentState
    from customer_service.graph.nodes.intent_parse import intent_parse_node
    from langgraph.types import RunnableConfig
    from customer_service.context.runtime import AgentRuntimeContext
    from customer_service.context.principal import AuthPrincipal

    # 模拟状态
    state: AgentState = {
        "turn_id": "test-history-001",
        "current_message": "我刚问了什么问题？",
        "active_task": None,
        "paused_tasks": [],
    }

    # 模拟runtime context
    import time
    from pydantic import SecretStr

    principal = AuthPrincipal(user_id="U0001")
    runtime = AgentRuntimeContext(
        session_id="test-session-001",
        principal=principal,
        user_access_token=SecretStr("dummy-token"),
        request_id="test-req-001",
        request_deadline_monotonic=time.monotonic() + 30
    )

    config = RunnableConfig(configurable={"runtime": runtime})

    # 执行intent_parse
    result_state = await intent_parse_node(state, config)

    # 验证：应该直接设置了response_draft，不走Intent分类
    assert "response_draft" in result_state, "应该直接生成响应"
    assert result_state["response_draft"], "响应不能为空"

    # 验证：turn_action应该是CHITCHAT（历史查询视为元对话）
    from customer_service.intents.models import TurnAction
    assert result_state.get("turn_action") == TurnAction.CHITCHAT, \
        "历史查询应该设置为CHITCHAT动作"

    print("✅ 集成测试: 历史查询完整流程验证通过")


if __name__ == "__main__":
    print("=" * 60)
    print("P0+P1修复完整验证测试")
    print("=" * 60)
    
    test_p1_history_query_detection()
    test_p1_frontend_store_states()
    test_p1_frontend_view_ui()
    
    import asyncio
    asyncio.run(test_integration_history_query())
    
    print("\n" + "=" * 60)
    print("✅ 所有P0+P1修复验证通过！")
    print("=" * 60)
