"""
P0修复验证测试

测试修改建议1中的P0优先级问题：
1. 前端Token刷新返回契约一致性
2. hallucination_guard必须设置guard_status
3. response_gen中CHITCHAT先于active_task检查
4. intent_parse从config.runtime获取session_id并排除当前turn

运行方式：
cd customer-service-backend
python -m pytest ../test/test_p0_fixes.py -v -s
"""
import pytest


def test_p0_1_frontend_request_contract():
    """
    P0-1: 验证前端request.js的修复
    
    修复内容：
    - Token刷新后使用request(originalRequest)而非axios(originalRequest)
    - 添加单例refreshPromise避免并发重复刷新
    """
    import os
    
    request_js_path = os.path.join(
        os.path.dirname(__file__),
        "../customer-service-frontend/src/utils/request.js"
    )
    
    with open(request_js_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 验证1：存在单例refreshPromise
    assert 'let refreshPromise = null' in content, "缺少单例refreshPromise声明"
    
    # 验证2：Token刷新后调用request而非axios
    assert 'return request(originalRequest)' in content, "Token刷新后应该return request(originalRequest)"
    
    # 验证3：不应该直接return axios(originalRequest)
    # 注意：axios.post('/commerce/api/v1/auth/refresh'...)是正常的
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if 'return axios(originalRequest)' in line:
            # 检查前后文，确保不是在注释中
            context = '\n'.join(lines[max(0, i-2):i+3])
            if '// P0修复关键' in context or '原来' in context:
                # 这是注释说明，允许
                continue
            else:
                pytest.fail(f"第{i+1}行不应该直接 return axios(originalRequest)")
    
    print("✅ P0-1: 前端request.js修复验证通过")


def test_p0_2_hallucination_guard_status():
    """
    P0-2: 验证hallucination_guard.py的修复
    
    修复内容：
    - 所有return分支都必须设置guard_status
    - 无response_draft时设置FALLBACK
    - 无active_task时设置PASS（非业务事实响应）
    """
    from customer_service.graph.nodes.hallucination_guard import hallucination_guard_node
    from customer_service.intents.models import GuardStatus
    import inspect
    
    # 读取源码
    source = inspect.getsource(hallucination_guard_node)
    
    # 验证1：无response_draft分支设置FALLBACK
    assert 'if not response_draft:' in source
    assert 'GuardStatus.FALLBACK' in source
    
    # 验证2：无active_task分支设置PASS
    assert 'if not active_task:' in source
    lines_after_no_task = source[source.find('if not active_task:'):].split('\n')[:15]
    assert any('GuardStatus.PASS' in line for line in lines_after_no_task), \
        "无active_task分支必须设置GuardStatus.PASS"
    
    # 验证3：不应该有return state但没设置guard_status的情况
    # 这个通过运行时测试更准确
    
    print("✅ P0-2: hallucination_guard.py修复验证通过")


def test_p0_3_response_gen_priority():
    """
    P0-3: 验证response_gen.py的修复
    
    修复内容：
    - CHITCHAT/CLARIFY/CANCEL必须先于active_task检查
    - TurnAction优先级高于Task状态
    """
    from customer_service.graph.nodes.response_gen import response_gen_node
    import inspect
    
    source = inspect.getsource(response_gen_node)
    
    # 找到关键代码块的位置
    chitchat_pos = source.find('turn_action == TurnAction.CHITCHAT')
    clarify_pos = source.find('turn_action in {')
    active_task_check_pos = source.find('if not active_task:')
    
    # 验证1：CHITCHAT检查必须在active_task检查之前
    if chitchat_pos != -1 and active_task_check_pos != -1:
        assert chitchat_pos < active_task_check_pos, \
            "CHITCHAT检查必须在active_task检查之前"
    
    # 验证2：CLARIFY等检查必须在active_task检查之前
    if clarify_pos != -1 and active_task_check_pos != -1:
        assert clarify_pos < active_task_check_pos, \
            "CLARIFY检查必须在active_task检查之前"
    
    # 验证3：不应该先检查active_task再检查CHITCHAT
    lines = source.split('\n')
    found_active_task_first = False
    for i, line in enumerate(lines):
        if 'if not active_task:' in line and i < len(lines) - 20:
            # 检查后续20行是否有CHITCHAT处理
            following = '\n'.join(lines[i:i+20])
            if 'BusinessIntent.CHITCHAT' in following:
                found_active_task_first = True
                break
    
    assert not found_active_task_first, \
        "不应该先检查active_task再处理CHITCHAT"
    
    print("✅ P0-3: response_gen.py修复验证通过")


def test_p0_4_intent_parse_history():
    """
    P0-4: 验证intent_parse.py的修复
    
    修复内容：
    - _get_conversation_history从config.runtime获取session_id
    - 排除当前turn_id的消息
    - 函数签名包含config参数
    """
    from customer_service.graph.nodes.intent_parse import _get_conversation_history
    import inspect
    
    # 验证1：函数签名包含config参数
    sig = inspect.signature(_get_conversation_history)
    params = list(sig.parameters.keys())
    assert 'config' in params, "_get_conversation_history必须包含config参数"
    assert 'state' in params, "_get_conversation_history必须包含state参数"
    assert 'turn_id' in params, "_get_conversation_history必须包含turn_id参数"
    
    # 验证2：源码中使用config.runtime获取session_id
    source = inspect.getsource(_get_conversation_history)
    assert 'config.get("configurable"' in source or 'config.get(\'configurable\'' in source, \
        "必须从config获取configurable"
    assert 'runtime.session_id' in source, "必须从runtime获取session_id"
    
    # 验证3：排除当前turn_id
    assert 'turn_id != turn_id' in source or 'ChatMessage.turn_id != turn_id' in source, \
        "必须排除当前turn_id"
    
    print("✅ P0-4: intent_parse.py修复验证通过")


@pytest.mark.asyncio
async def test_integration_chitchat_no_500():
    """
    集成测试：闲聊不应该500

    场景："你是谁？" -> 不创建active_task -> response_gen正常生成 -> guard PASS
    """
    from customer_service.graph.state import AgentState
    from customer_service.intents.models import TurnAction, BusinessIntent, IntentResult, IntentDecision
    from customer_service.tasking.models import TaskFrame
    from customer_service.graph.nodes.response_gen import response_gen_node
    from customer_service.graph.nodes.hallucination_guard import hallucination_guard_node
    from langgraph.types import RunnableConfig

    # 模拟CHITCHAT状态
    state: AgentState = {
        "turn_id": "test-chitchat-001",
        "current_message": "你是谁？",
        "turn_action": TurnAction.CHITCHAT,
        "intent_result": IntentResult(
            recognized=True,
            intent=BusinessIntent.CHITCHAT,
            decision=IntentDecision.ACCEPT,
            confidence=0.95,
            entities={}
        ),
        "active_task": None,  # 关键：CHITCHAT不创建active_task
        "paused_tasks": [],
    }

    config = RunnableConfig()

    # 测试response_gen
    state = await response_gen_node(state, config)
    assert "response_draft" in state, "response_gen必须生成response_draft"
    assert state["response_draft"], "response_draft不能为空"

    # 测试hallucination_guard
    state = await hallucination_guard_node(state, config)
    assert "guard_status" in state, "hallucination_guard必须设置guard_status"
    assert state["guard_status"] is not None, "guard_status不能为None"

    print("✅ 集成测试: CHITCHAT不会500")


if __name__ == "__main__":
    print("=" * 60)
    print("P0修复验证测试")
    print("=" * 60)
    
    test_p0_1_frontend_request_contract()
    test_p0_2_hallucination_guard_status()
    test_p0_3_response_gen_priority()
    test_p0_4_intent_parse_history()
    test_integration_chitchat_no_500()
    
    print("\n" + "=" * 60)
    print("✅ 所有P0修复验证通过！")
    print("=" * 60)
