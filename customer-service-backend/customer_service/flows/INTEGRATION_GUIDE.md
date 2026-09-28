# Intent Flow 集成指南

## 概览

Intent Flow 架构已完成实现，包含 4 个核心 Flow：

1. **ProductQueryFlow** - 商品查询
2. **PromotionQueryFlow** - 促销查询
3. **UrgeOrderPaymentFlow** - 催拍催付
4. **ChitchatFlow** - 闲聊

## 集成到 LangGraph

### 1. 在应用启动时注册 Flow

在 `customer_service/main.py` 或应用入口添加：

```python
from customer_service.flows import (
    IntentFlowRegistry,
    ProductQueryFlow,
    PromotionQueryFlow,
    UrgeOrderPaymentFlow,
    ChitchatFlow,
)

def register_flows():
    """注册所有 Intent Flow"""
    IntentFlowRegistry.register(ProductQueryFlow())
    IntentFlowRegistry.register(PromotionQueryFlow())
    IntentFlowRegistry.register(UrgeOrderPaymentFlow())
    IntentFlowRegistry.register(ChitchatFlow())
    
    logger.info(f"✅ Registered flows: {IntentFlowRegistry.list_all()}")

# 在应用启动时调用
@app.on_event("startup")
async def startup_event():
    register_flows()
```

### 2. 在 LangGraph 中添加 Flow 执行节点

在 `customer_service/graph/nodes.py` 中添加：

```python
from customer_service.flows.registry import IntentFlowRegistry

async def execute_intent_flow_node(state: AgentState) -> AgentState:
    """
    执行 Intent Flow
    
    此节点根据 current_intent 查找并执行对应的 Flow，
    将 Flow 返回的结构化数据存入 state.flow_context
    """
    intent = state.get("current_intent")
    session_id = state.get("session_id", "unknown")
    
    if not intent:
        logger.warning(f"[{session_id}] No intent found in state")
        return state
    
    # 获取 Flow
    flow = IntentFlowRegistry.get(intent)
    if not flow:
        logger.warning(f"[{session_id}] ⚠️ No flow registered for intent: {intent}")
        state["flow_context"] = {
            "error": f"No flow for intent: {intent}",
            "fallback": True,
        }
        return state
    
    try:
        # 执行 Flow
        logger.info(f"[{session_id}] Executing flow: {intent}")
        flow_result = await flow.execute(state)
        
        # 将结果存入 state
        state["flow_context"] = flow_result
        logger.info(f"[{session_id}] ✅ Flow completed: {intent}")
        
    except Exception as e:
        logger.error(f"[{session_id}] ❌ Flow execution error: {e}", exc_info=True)
        state["flow_context"] = {
            "error": str(e),
            "fallback": True,
        }
    
    return state
```

### 3. 在 Graph 中添加节点和边

在 `customer_service/graph/graph.py` 中：

```python
from customer_service.graph.nodes import execute_intent_flow_node

# 构建 Graph
workflow = StateGraph(AgentState)

# 添加节点
workflow.add_node("intent_classification", intent_classification_node)
workflow.add_node("execute_flow", execute_intent_flow_node)  # 新增
workflow.add_node("generate_response", generate_response_node)

# 添加边
workflow.add_edge(START, "intent_classification")
workflow.add_edge("intent_classification", "execute_flow")  # 新增
workflow.add_edge("execute_flow", "generate_response")
workflow.add_edge("generate_response", END)
```

### 4. 更新 LLM Response 生成节点

在 `generate_response_node` 中使用 Flow 结果：

```python
async def generate_response_node(state: AgentState) -> AgentState:
    """生成最终用户响应"""
    session_id = state.get("session_id")
    intent = state.get("current_intent")
    flow_context = state.get("flow_context", {})
    
    # 构建 LLM Prompt
    system_prompt = f"""你是一个电商客服助手。
    
当前意图: {intent}
Flow 上下文: {json.dumps(flow_context, ensure_ascii=False, indent=2)}

请根据上述信息生成友好、准确的用户回复。
"""
    
    # 调用 LLM
    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        *state["messages"],
    ])
    
    state["messages"].append(AIMessage(content=response.content))
    return state
```

## Flow 执行流程

```
用户消息
    ↓
Intent 分类
    ↓
执行对应 Flow (execute_intent_flow_node)
    ├─ ProductQueryFlow → 返回商品列表、检索模式
    ├─ PromotionQueryFlow → 返回促销信息
    ├─ UrgeOrderPaymentFlow → 返回转化策略
    └─ ChitchatFlow → 返回闲聊类型
    ↓
LLM 生成响应 (基于 flow_context)
    ↓
返回用户
```

## 测试

```python
import pytest
from customer_service.graph.state import AgentState
from customer_service.flows import ProductQueryFlow

@pytest.mark.asyncio
async def test_product_flow_integration():
    """测试 ProductQueryFlow 集成"""
    state = AgentState(
        session_id="test-123",
        messages=[HumanMessage(content="我想看黑色的连衣裙")],
        current_intent="product_query",
    )
    
    # 执行 Flow
    flow = ProductQueryFlow()
    result = await flow.execute(state)
    
    assert "products" in result
    assert result["retrieval_mode"] in ["direct", "rag", "clarify"]
```

## 注意事项

1. **Flow 返回结构化数据**：Flow 不生成自然语言，只返回结构化数据供 LLM 使用
2. **错误处理**：每个 Flow 应捕获异常并返回降级结果
3. **幂等性**：Flow 应该是幂等的（相同输入 → 相同输出）
4. **独立性**：Flow 之间不应相互调用

## 完成状态

- ✅ IntentFlowRegistry 注册表
- ✅ ProductQueryFlow (商品查询)
- ✅ PromotionQueryFlow (促销查询)
- ✅ UrgeOrderPaymentFlow (催拍催付)
- ✅ ChitchatFlow (闲聊)
- ✅ 所有文件语法验证通过
- ✅ 集成文档完成
