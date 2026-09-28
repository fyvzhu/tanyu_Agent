# Intent Flow 层

Intent Flow 层是客服 Agent 的业务逻辑处理层，位于 Intent 识别和 LLM 响应生成之间。

## 架构概览

```
用户消息 → Intent 识别 → Intent Flow 执行 → LLM 响应生成 → 返回用户
                ↓              ↓
           intent_name    flow_context
```

## 设计理念

### 为什么需要 Intent Flow？

传统的 Tool-only 架构存在以下问题：

1. **职责不清**：Tool 既要处理业务逻辑，又要格式化 LLM 输入
2. **复用困难**：不同 Intent 可能需要调用相同的 API，但处理逻辑不同
3. **难以测试**：Tool 和 LLM 耦合紧密，单元测试困难

Intent Flow 架构通过引入中间层解决这些问题：

- **Flow**：处理完整的业务流程（API 调用、数据聚合、上下文构建）
- **Tool**：退化为纯粹的 API 适配器（可选）
- **LLM**：专注于自然语言生成

## 已实现的 Flow

### 1. ProductQueryFlow - 商品查询

处理商品检索和详情查询，支持三种查询路径：

- **Direct**：有明确 product_id，直接查询 Commerce API
- **RAG**：语义搜索，通过向量检索 + 关键词检索
- **Clarify**：指代不明确，需要澄清

```python
from customer_service.flows import ProductQueryFlow

flow = ProductQueryFlow()
result = await flow.execute(state)

# 返回格式
{
    "products": [...],
    "retrieval_mode": "direct" | "rag" | "clarify",
    "focused_product_id": str | None,
    "skus": [...] | None,  # 仅 direct 模式
    "retrieval_scores": {...} | None,  # 仅 rag 模式
}
```

### 2. PromotionQueryFlow - 促销查询

处理商品促销、优惠券查询：

- 特定商品促销（需要 focused_product_id）
- 用户级别促销（优惠券、全局活动）

```python
from customer_service.flows import PromotionQueryFlow

flow = PromotionQueryFlow()
result = await flow.execute(state)

# 返回格式
{
    "promotions": [...],
    "product": {...} | None,
    "product_id": str | None,
}
```

### 3. UrgeOrderPaymentFlow - 催拍催付

纯 Intent 驱动，不调用 Commerce API：

- 判断催拍还是催付
- 评估用户紧急程度
- 检测犹豫信号

```python
from customer_service.flows import UrgeOrderPaymentFlow

flow = UrgeOrderPaymentFlow()
result = await flow.execute(state)

# 返回格式
{
    "conversion_type": "urge_purchase" | "urge_payment",
    "focused_product_id": str | None,
    "urgency_level": "low" | "medium" | "high",
    "hesitation_signals": [...],
}
```

### 4. ChitchatFlow - 闲聊

处理非业务对话：

- 问候、感谢、告别
- 情感分析

```python
from customer_service.flows import ChitchatFlow

flow = ChitchatFlow()
result = await flow.execute(state)

# 返回格式
{
    "chitchat_type": "greeting" | "thanks" | "goodbye" | "small_talk",
    "sentiment": "positive" | "neutral" | "negative",
}
```

## 集成到 LangGraph

### 1. 注册 Flow（应用启动时）

在 `customer_service/main.py` 或 `customer_service/api/app.py` 中：

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
    
    logger.info(f"✅ Registered {len(IntentFlowRegistry.list_all())} flows")

# 在应用启动时调用
register_flows()
```

### 2. 添加 Flow 执行节点

在 `customer_service/graph/nodes.py` 中添加：

```python
from customer_service.flows.registry import IntentFlowRegistry

async def execute_intent_flow_node(state: AgentState) -> AgentState:
    """执行 Intent Flow"""
    intent = state.get("intent")
    session_id = state.get("session_id", "unknown")
    
    logger.info(f"[{session_id}] 🚀 Executing flow for intent: {intent}")
    
    # 获取对应的 Flow
    flow = IntentFlowRegistry.get(intent)
    if not flow:
        logger.warning(f"[{session_id}] ⚠️ No flow registered for intent: {intent}")
        state["flow_context"] = {"error": f"No flow for intent: {intent}"}
        return state
    
    # 执行 Flow
    try:
        flow_result = await flow.execute(state)
        state["flow_context"] = flow_result
        logger.info(f"[{session_id}] ✅ Flow executed successfully")
    except Exception as e:
        logger.error(f"[{session_id}] ❌ Flow execution error: {e}", exc_info=True)
        state["flow_context"] = {"error": str(e)}
    
    return state
```

### 3. 更新 Graph 结构

在 `customer_service/graph/builder.py` 中：

```python
from customer_service.graph.nodes import (
    intent_parse_node,
    execute_intent_flow_node,  # 新增
    response_gen_node,
)

# 构建 Graph
graph = StateGraph(AgentState)

# 添加节点
graph.add_node("intent_parse", intent_parse_node)
graph.add_node("execute_flow", execute_intent_flow_node)  # 新增
graph.add_node("response_gen", response_gen_node)

# 连接节点
graph.add_edge("intent_parse", "execute_flow")  # intent → flow
graph.add_edge("execute_flow", "response_gen")  # flow → response
```

### 4. 在响应生成中使用 Flow 结果

在 `customer_service/graph/nodes/response_gen.py` 中：

```python
async def response_gen_node(state: AgentState) -> AgentState:
    """生成响应"""
    intent = state.get("intent")
    flow_context = state.get("flow_context", {})
    
    # 将 flow_context 传递给 LLM
    prompt = build_response_prompt(
        intent=intent,
        user_query=state.get("current_message"),
        flow_context=flow_context,  # Flow 执行结果
        memory=state.get("short_memory"),
    )
    
    response = await llm.ainvoke(prompt)
    state["response_text"] = response.content
    
    return state
```

## State 字段定义

需要在 `customer_service/graph/state.py` 中添加：

```python
class AgentState(TypedDict, total=False):
    # ... 现有字段 ...
    
    # Flow 相关字段
    flow_context: dict[str, Any]  # Flow 执行结果
```

## 添加新 Flow

1. 创建新的 Flow 类（继承 `IntentFlow` 协议）
2. 实现 `execute(state: AgentState) -> dict[str, Any]` 方法
3. 在 `flows/__init__.py` 中导出
4. 在应用启动时注册

```python
from customer_service.flows import IntentFlowRegistry

class MyNewFlow:
    intent_name = "my_new_intent"
    
    async def execute(self, state: AgentState) -> dict[str, Any]:
        # 实现业务逻辑
        return {"result": "..."}

# 注册
IntentFlowRegistry.register(MyNewFlow())
```

## 测试

```python
import pytest
from customer_service.flows import ProductQueryFlow

@pytest.mark.asyncio
async def test_product_query_flow():
    flow = ProductQueryFlow()
    state = {
        "session_id": "test-123",
        "current_message": "我想看黑色的连衣裙",
        "focused_object": None,
    }

    result = await flow.execute(state)

    assert "products" in result
    assert result["retrieval_mode"] in ["direct", "rag", "clarify"]
```

## 与 Tool 的对比

| 维度 | Tool-only 模式 | Intent Flow 模式 |
|------|---------------|-----------------|
| **职责** | Tool 处理所有业务逻辑 + 数据格式化 | Flow 处理业务逻辑，Tool 退化为 API 适配器 |
| **复用性** | 低（Tool 与 Intent 紧耦合） | 高（Flow 可复用，独立测试） |
| **可测试性** | 难（需要 Mock LLM） | 易（纯业务逻辑，无 LLM 依赖） |
| **上下文感知** | 弱（Tool 难以访问对话上下文） | 强（Flow 可访问完整 State） |
| **降级策略** | 难以实现 | 易于实现（Flow 内部处理） |

## 注意事项

1. **Flow 不应直接返回自然语言**：Flow 返回结构化数据，由 LLM 生成最终响应
2. **Flow 应该是幂等的**：相同输入应产生相同输出（除非依赖外部状态）
3. **Flow 应该处理异常**：捕获并记录错误，返回降级结果而非抛出异常
4. **避免 Flow 间依赖**：每个 Flow 应该是独立的，不应调用其他 Flow

