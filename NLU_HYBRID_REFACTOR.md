# NLU_HYBRID_REFACTOR.md

> **用途**：本文件是一份可直接交给 Augment 执行的独立、自包含改造说明。  
> **目标项目**：`tanyu_Agent / customer-service-backend`  
> **核心目标**：在不推翻现有 LangGraph 主架构的前提下，补齐“规则 + LLM 混合意图识别与实体抽取”，并保持“意图置信度决策 + 槽位完整性检查 + 条件边分流”的职责边界清晰、可测试、可回退。  
> **最高原则**：不得另起一套 NLU、LLM Client、Task 或 Routing 体系；优先复用项目现有 `IntentClassifier / StructuredLLMClassifier / IntentDecisionValidator / slot_check / routing / infrastructure.llm`。

---

# 1. 改造背景与当前问题

当前项目已经具备较完整的 LangGraph 骨架，主链路包括：

```text
intent_parse
    ↓
slot_check
    ↓
tool_dispatch
    ↓
response_gen
    ↓
hallucination_guard
```

项目还已经具备：

- `IntentClassifier`
- `StructuredLLMClassifier`
- `IntentDecisionValidator`
- 规则实体抽取器
- `slot_check`
- `route_after_intent`
- `route_after_slot_check`
- `customer_service.infrastructure.llm.get_llm()`
- Task / Redis Checkpoint / DialogueFrame 等多轮上下文基础设施

但是当前 NLU 层仍存在以下关键缺口。

## 1.1 LLM 意图识别只存在“骨架”，没有真正接入运行链路

当前 `IntentClassifier` 已经预留：

```python
IntentClassifier(use_llm: bool = False)
```

以及类似：

```python
classify_with_llm(...)
```

的混合逻辑入口，但当前生产链路仍主要调用：

```python
IntentClassifier().classify(...)
```

即默认：

```text
use_llm = False
```

所以真实运行时主要还是：

```text
关键词/规则分类
    ↓
规则置信度
    ↓
Validator
```

而不是：

```text
规则分类
    ↓
低/中置信度
    ↓
真实 LLM
    ↓
融合
```

## 1.2 `StructuredLLMClassifier` 的真实 LLM 调用未完成

当前项目已有：

- Pydantic Structured Schema
- Prompt
- `intent`
- `entities`
- `confidence`
- `text_span`

等结构设计。

但真实模型调用仍是 TODO / Mock，不能把它视为已完成的 LLM NLU。

因此本次改造必须真正实现：

```text
StructuredLLMClassifier
        ↓
复用 get_llm()
        ↓
ainvoke / structured output
        ↓
Pydantic 校验
        ↓
返回真实 intent + entities + confidence
```

## 1.3 当前主实体抽取器本质上还是纯规则

目前规则实体抽取已经可以识别多种确定性实体，例如：

```text
product_id
order_id
sku_id
price
color
size
height
weight
waist
bust
hip
fit_preference
```

但本项目希望重点支持的五类核心商品实体是：

```text
product_name
brand
price
size
color
```

当前主要缺口是：

```text
product_name  ❌ 缺少稳定的混合抽取
brand         ❌ 缺少稳定的混合抽取
LLM entity    ❌ 尚未真正接入
Entity Fusion ❌ 尚未实现
```

因此不能继续只靠 Regex/Keyword 扩展。

---

# 2. 本次改造的最终目标

完成后，NLU 应形成下面的整体结构：

```text
                         Current Message
                                │
                                ▼
                        Context Resolver
                                │
                      已解析上下文/历史任务
                                │
                                ▼
                 ┌─────────────────────────┐
                 │ Rule NLU                │
                 │                         │
                 │ 1. Rule Intent          │
                 │ 2. Rule Entity          │
                 └────────────┬────────────┘
                              │
                     confidence / margin
                     entity completeness
                              │
                              ▼
                      Hybrid NLU Policy
                 ┌────────────┼────────────┐
                 │            │            │
               HIGH         MEDIUM        LOW
                 │            │            │
            Rule直接用     调用LLM      调用LLM
                 │            │            │
                 └──────┬─────┴─────┬──────┘
                        │           │
                        ▼           ▼
                  LLM Intent   LLM Entities
                        │           │
                        └─────┬─────┘
                              ▼
                        Entity Fusion
                              │
                              ▼
                    Final NLU Result
             intent/confidence/entities/source
                              │
                              ▼
                IntentDecisionValidator
                     │                  │
                  CLARIFY             ACCEPT
                     │                  │
                  respond           slot_check
                                        │
                           ┌────────────┴────────────┐
                           │                         │
                     missing_slots                 READY
                           │                         │
                        respond                tool_dispatch
```

---

# 3. 必须保持不变的架构边界

本次改造不是重构整个 Agent。Augment 必须遵守以下边界。

## 3.1 不允许重写 LangGraph 主图

保留当前：

```text
intent_parse
slot_check
tool_dispatch
response_gen
hallucination_guard
```

以及现有条件边体系。

允许修改：

```text
intent_parse 内部的 NLU 调用方式
NLU Schema
Hybrid NLU Policy
Entity Fusion
测试
日志
```

不允许因为参考其他 GitHub 项目，就把现有 StateGraph 改成另外一种框架。

## 3.2 不允许新增第二套 LLM Infrastructure

必须复用：

```python
customer_service.infrastructure.llm.get_llm()
```

不要新增：

```text
OpenAIClient
LLMService2
HybridLLMClient
CustomChatClient
```

之类重复实现。

## 3.3 不允许让 Routing 直接承担 NLU 阈值策略

错误做法：

```python
def route_after_intent(state):
    if state["confidence"] > 0.85:
        return "slot_check"
```

正确职责：

```text
Classifier / Hybrid Policy
        ↓
Validator
        ↓
TurnAction
        ↓
Routing
```

即 `route_after_intent()` 应消费：

```text
TurnAction.ACCEPT
TurnAction.CLARIFY
TurnAction.OUT_OF_SCOPE
...
```

而不是自己解释 NLU confidence。

## 3.4 不允许让 LLM 直接操作 Task / Tool

LLM NLU 只负责：

```text
intent
entities
confidence
ambiguity
```

不能直接：

```text
启动 Task
暂停 Task
调用 Tool
修改 Redis
修改订单
```

Task、Slot、Tool 继续由现有业务层负责。

---

# 4. 推荐新增/改造的核心数据结构

建议统一定义实体候选结构。如果项目已有类似模型，优先复用，不重复创建。

```python
from typing import Any, Literal
from pydantic import BaseModel, Field


class EntityCandidate(BaseModel):
    name: str
    value: Any
    normalized_value: Any | None = None

    source: Literal[
        "rule",
        "llm",
        "context",
        "catalog",
        "fusion",
    ]

    confidence: float = Field(
        ge=0.0,
        le=1.0,
    )

    text_span: str | None = None

    validated: bool = False
```

LLM 输出建议统一成：

```python
class LLMEntity(BaseModel):
    name: str
    value: str
    confidence: float = Field(ge=0.0, le=1.0)
    text_span: str | None = None


class StructuredIntentGoal(BaseModel):
    intent: BusinessIntent
    confidence: float = Field(ge=0.0, le=1.0)
    text_span: str | None = None
    entities: list[LLMEntity] = Field(default_factory=list)


class StructuredNLUOutput(BaseModel):
    goals: list[StructuredIntentGoal] = Field(default_factory=list)
    is_out_of_scope: bool = False
    needs_clarification: bool = False
    reasoning: str | None = None
```

注意：

> `reasoning` 只用于日志调试，不能把 LLM 自由文本 reasoning 当业务控制依据。

真正控制流程的只能是结构化字段。

---

# 5. 规则实体抽取必须继续保留

规则不是“旧实现”，而是 Hybrid NLU 的第一层。

必须继续保留对确定性实体的 Regex / Dictionary 抽取。

尤其下面这些实体，规则优先级必须高于 LLM：

| 实体 | 推荐方式 | 是否允许 LLM 覆盖显式规则值 |
|---|---|---:|
| `product_id` | Regex + 业务校验 | 否 |
| `order_id` | Regex + 业务校验 | 否 |
| `sku_id` | Regex + 业务校验 | 否 |
| `price` | Regex / 数字解析 | 否 |
| `size` | Regex + 枚举 | 原则上否 |
| `color` | 字典/同义词 | 原则上否 |
| `brand` | 品牌词典/商品目录 + LLM | Exact 结果不可覆盖 |
| `product_name` | 商品目录/检索 + LLM | Exact 结果不可覆盖 |

规则 extractor 每个实体最好都返回：

```text
value
source=rule
confidence
text_span
validated
```

不要继续只返回：

```python
{
    "color": "黑色"
}
```

否则后面无法做冲突融合与可解释测试。

---

# 6. LLM Entity Extraction 的职责

LLM 主要解决规则难以稳定处理的自然语言表达。

例如：

```text
“那个 Just Natural 的防雨外套”
“刚才第一件衣服”
“Puma 那款黑色运动鞋”
“要便宜一点的”
“有没有偏宽松一点的”
```

LLM 可以输出：

```json
{
  "intent": "product_query",
  "confidence": 0.86,
  "entities": [
    {
      "name": "brand",
      "value": "Just Natural",
      "confidence": 0.93
    },
    {
      "name": "product_name",
      "value": "防雨外套",
      "confidence": 0.82
    }
  ]
}
```

但是：

> LLM 抽到 `product_name="防雨外套"` 并不代表业务 Product 已经解析完成。

后面还必须进入：

```text
ProductReferenceResolver
    ↓
MySQL / ES / 商品目录
    ↓
唯一商品 / 多候选 / 无匹配
```

因此不要把：

```text
LLM Entity Extraction
```

和：

```text
Product Resolution
```

混成一个模块。

---

# 7. `StructuredLLMClassifier` 必须完成真实调用

禁止继续保留 Mock：

```python
await asyncio.sleep(...)
return fake_json
```

必须复用：

```python
from customer_service.infrastructure.llm import get_llm
```

推荐优先使用模型的 structured output：

```python
class StructuredLLMClassifier:

    def __init__(self, ...):
        self.llm = get_llm()
        self.structured_llm = (
            self.llm.with_structured_output(
                StructuredNLUOutput
            )
        )

    async def classify(
        self,
        prompt: str,
        timeout: float = 8.0,
    ) -> StructuredNLUOutput:

        result = await asyncio.wait_for(
            self.structured_llm.ainvoke(prompt),
            timeout=timeout,
        )

        return StructuredNLUOutput.model_validate(result)
```

如果当前模型或 Provider 不支持：

```python
with_structured_output(...)
```

才允许使用：

```text
ainvoke
→ JSON 提取
→ StructuredNLUOutput.model_validate_json()
```

但无论哪种方式：

> LLM 自由文本都不能直接进入 AgentState 作为 IntentResult。

---

# 8. Prompt 必须包含的上下文

LLM NLU Prompt 不要只传：

```text
current_message
```

至少应包含：

```text
current_message
recent_history（精简）
active_task.intent
active_task.status
active_task.missing_slots
conversation_focus
dialogue_frame.last_business_intent
dialogue_frame.last_focus
rule_intent_candidate
rule_confidence
rule_entities
```

建议构造：

```python
nlu_context = {
    "current_message": current_message,

    "active_task": {
        "intent": ...,
        "status": ...,
        "missing_slots": ...,
    },

    "conversation_focus": ...,

    "last_business_intent": ...,

    "rule_result": {
        "intent": ...,
        "confidence": ...,
        "margin": ...,
        "entities": ...,
    },

    "recent_messages": recent_messages[-6:],
}
```

注意：

> 不要把整个 Redis State 或几十轮原始聊天全部塞给 LLM。

---

# 9. Hybrid Intent Policy：什么时候调用 LLM

不要每一句都调用 LLM。

建议新增统一策略模块，例如：

```text
customer_service/intents/hybrid_policy.py
```

如果当前已有合适模块，则直接放入现有 intents/policies 中。

推荐初始策略：

```text
HIGH:
    confidence >= 0.85
    AND margin >= 0.20
    AND 无歧义

MEDIUM:
    confidence >= 0.60
    但没有达到 HIGH

LOW:
    confidence < 0.60
    OR margin < 0.08
```

注意：

> 这些阈值必须做成配置项，不允许散落硬编码在多个文件中。

例如：

```python
class HybridNLUSettings:
    rule_high_confidence: float = 0.85
    rule_medium_confidence: float = 0.60
    rule_min_margin: float = 0.08
    llm_accept_confidence: float = 0.75
```

初期建议：

```text
HIGH → 默认不为意图调用 LLM

MEDIUM → LLM 验证/融合

LOW → LLM 作为主要语义判定来源

规则高置信度，但是核心实体缺失
→ 可以仅为实体补全调用 LLM
```

因此 `needs_llm` 不能只看 Intent confidence。

应该同时考虑：

```text
intent_confidence
intent_margin
ambiguity
required entity completeness
context unresolved
```

---

# 10. 不允许简单平均 Rule 与 LLM Confidence

禁止：

```python
final_confidence = (
    rule_confidence + llm_confidence
) / 2
```

因为两种 confidence 并不是同一概率空间。

推荐决策规则。

## 10.1 Rule HIGH，LLM 未调用

```text
Final Intent = Rule Intent
Final Confidence = Rule Confidence
Source = rule
```

## 10.2 Rule MEDIUM，LLM 与 Rule 一致

例如：

```text
Rule:
promotion_query 0.72

LLM:
promotion_query 0.91
```

可以：

```text
Final Intent = promotion_query
Source = rule+llm
Confidence = max(rule, llm)，但设置上限
```

例如：

```python
final_confidence = min(
    max(rule_confidence, llm_confidence) + 0.03,
    0.98,
)
```

这里的 `+0.03` 只是初始建议，必须通过测试集校准。

## 10.3 Rule 与 LLM 冲突

例如：

```text
Rule:
product_query 0.69

LLM:
promotion_query 0.92
```

不允许直接简单以 LLM 覆盖规则。

推荐策略：

```text
如果：
LLM >= 0.85
AND Rule < 0.75
AND Context 支持 LLM

→ 可采用 LLM

否则：
→ CLARIFY
```

尤其：

```text
两个结果都 >= 0.80
但 intent 不一致
```

必须优先：

```text
CLARIFY
```

不能静默选择一个。

---

# 11. Entity Fusion 必须独立实现

建议新增：

```text
customer_service/intents/entity_fusion.py
```

如果已有同职责文件，复用现有模块。

接口示例：

```python
class EntityFusionService:

    def merge(
        self,
        rule_entities: list[EntityCandidate],
        llm_entities: list[EntityCandidate],
        context_entities: list[EntityCandidate],
    ) -> dict[str, EntityCandidate]:
        ...
```

融合顺序建议：

```text
Validated Exact Rule
        >
Catalog Exact
        >
Context Confirmed
        >
Rule Dictionary / Regex
        >
High-confidence LLM
        >
Low-confidence LLM
```

---

# 12. 五类核心实体的具体融合规则

## 12.1 `price`

规则：

```text
“300以内”
“不要超过500”
“200到400”
```

Regex/数字解析明确时：

```text
Rule > LLM
```

LLM 只能帮助判断语义：

```text
max_price
min_price
price_range
```

不能把：

```text
“300以内”
```

改成：

```text
500
```

## 12.2 `size`

明确：

```text
S
M
L
XL
37
38
39
```

时规则优先。

LLM 可用于理解：

```text
“大一码”
“宽松点”
“和平时一样”
```

但这些最好提取为：

```text
fit_preference
size_adjustment
```

而不是直接生成未经依据的最终 size。

## 12.3 `color`

品牌/商品已知颜色词典中精确命中时：

```text
Dictionary > LLM
```

LLM 用于：

```text
“偏米白”
“深一点的蓝”
“和刚才那个颜色一样”
```

## 12.4 `brand`

优先级：

```text
商品品牌字典 Exact
        >
Catalog Resolver
        >
LLM
```

例如：

```text
Puma
ADIDAS
Peter England
Turtle
```

如果商品数据中存在该品牌：

```text
validated = True
```

LLM 不允许覆盖已验证品牌。

## 12.5 `product_name`

不能只依赖 Regex。

推荐流程：

```text
Rule/Dictionary Candidate
        +
LLM Candidate
        ↓
ProductReferenceResolver
        ↓
MySQL/ES Exact/Fuzzy
        ↓
0 个 → 澄清
1 个 → resolved product_id
多个 → Candidate Selection
```

---

# 13. `product_id / order_id / sku_id` 必须禁止 LLM 幻觉

LLM 可以输出它从用户原文中看到的 ID。

但必须满足：

```text
1. 原文中实际出现；
或
2. Context 中已经确认；
或
3. Resolver 从业务数据解析得到。
```

禁止：

```text
LLM 自己生成一个 product_id
LLM 自己猜一个 order_id
LLM 自己补一个 sku_id
```

最终进入 Tool 前必须进行业务验证。

---

# 14. `IntentClassifier` 的建议改造方式

保留现有 Rule classifier。

建议统一提供一个异步入口：

```python
async def classify_hybrid(
    self,
    message: str,
    *,
    history: str | None = None,
    context: dict | None = None,
) -> HybridIntentResult:
    ...
```

内部：

```text
1. rule_classifier.classify()
2. rule_entity_extractor.extract()
3. hybrid_policy.should_call_llm()
4. 必要时 StructuredLLMClassifier.classify()
5. entity_fusion.merge()
6. intent_fusion
7. 返回统一 HybridIntentResult
```

建议输出：

```python
class HybridIntentResult(BaseModel):
    intent: BusinessIntent | None
    confidence: float

    source: Literal[
        "rule",
        "llm",
        "rule+llm",
        "context",
    ]

    margin: float | None = None
    ambiguous: bool = False

    entities: dict[str, EntityCandidate]

    llm_called: bool = False
    fallback_used: bool = False
```

---

# 15. `intent_parse_node` 应如何接入

当前节点不要继续：

```python
classifier = IntentClassifier()
result = classifier.classify(...)
```

应改为：

```python
classifier = get_intent_classifier()

hybrid_result = await classifier.classify_hybrid(
    current_message,
    history=history_str,
    context=nlu_context,
)
```

随后统一转换成项目现有：

```text
IntentClassificationResult
IntentDecisionValidator
```

即：

```text
Hybrid NLU
    ↓
现有 Result Adapter
    ↓
IntentDecisionValidator
    ↓
TurnAction
```

不要让 HybridClassifier 绕过 Validator。

---

# 16. Context Resolver 与 Hybrid NLU 的边界

项目正在补 `Context Resolver / DialogueFrame`。

两者职责必须分开。

## Context Resolver

负责：

```text
“那29570呢？”
“那黑色呢？”
“还是刚才那个”
“我刚问了什么？”
```

这类：

```text
历史继承
指代消解
Task continuation
Conversation Meta
```

## Hybrid NLU

负责：

```text
当前语句表达了什么业务意图？
当前语句包含哪些实体？
语义是否明确？
置信度如何？
```

因此推荐：

```text
Context Resolver
        ↓
resolved context
        ↓
Hybrid NLU
        ↓
Validator
```

不要让 LLM Classifier 再自己实现一套 Task Resume。

---

# 17. Slot Check 不需要推翻

保留现有：

```python
REQUIRED_SLOTS = {
    ...
}
```

以及：

```text
missing_slots
WAITING_SLOT
READY
```

逻辑。

完整链路继续是：

```text
Hybrid NLU
    ↓
Validator
    ↓
ACCEPT
    ↓
Task Start/Continue
    ↓
Slot Check
    ├── missing → WAITING_SLOT → respond
    └── complete → READY → tool_dispatch
```

---

# 18. 条件边的最终职责

## `route_after_intent`

只负责：

```text
TurnAction.ACCEPT
TurnAction.CLARIFY
TurnAction.OUT_OF_SCOPE
TurnAction.CANCEL
...
```

示意：

```python
def route_after_intent(state):
    action = state["turn_action"]

    if action == TurnAction.ACCEPT:
        return "check_slots"

    return "respond"
```

## `route_after_slot_check`

只负责：

```text
missing_slots?
Task READY?
```

示意：

```python
def route_after_slot_check(state):

    active_task = state.get("active_task")

    if not active_task:
        return "respond"

    if active_task.missing_slots:
        return "respond"

    if active_task.status != TaskStatus.READY:
        return "respond"

    return "execute"
```

禁止把：

```text
LLM confidence threshold
```

重新塞进 Routing。

---

# 19. LLM 失败必须 Fail Soft，而不是让聊天接口 500

需要覆盖：

```text
LLM timeout
LLM 429
LLM 500
LLM invalid JSON
Pydantic validation error
网络异常
```

策略：

```text
如果 Rule HIGH：
LLM 失败不影响最终结果

如果 Rule MEDIUM：
LLM 失败 → 使用 Rule + Validator
若 Rule 不足以 ACCEPT → CLARIFY

如果 Rule LOW：
LLM 失败 → CLARIFY
```

禁止：

```text
LLM 挂了
    ↓
整个 /messages 返回 500
```

---

# 20. 必须加入可观测日志

每一轮 Intent Parse 至少打印：

```text
rule_intent
rule_confidence
rule_margin
rule_entities

llm_called
llm_intent
llm_confidence
llm_entities

fusion_result

final_intent
final_confidence

turn_action
missing_slots
```

示例：

```text
[NLU]
rule_intent=promotion_query
rule_confidence=0.72
margin=0.18

llm_called=true
llm_intent=promotion_query
llm_confidence=0.91

entity_sources={
  product_id: rule,
  product_name: llm
}

final_intent=promotion_query
final_confidence=0.94
source=rule+llm

turn_action=ACCEPT
```

注意：

> 不要记录 JWT、密码、完整隐私字段。

---

# 21. 建议修改/新增文件

Augment 执行前必须先确认当前仓库真实路径，不允许因为文件名略有变化而创建重复模块。

预计涉及：

```text
customer_service/
├── intents/
│   ├── classifier.py
│   ├── entity_extractor.py
│   ├── structured_llm_classifier.py
│   ├── validator.py
│   ├── policies.py
│   │
│   ├── hybrid_policy.py          # 建议新增
│   └── entity_fusion.py          # 建议新增
│
├── graph/
│   └── nodes/
│       └── intent_parse.py
│
├── infrastructure/
│   └── llm.py                    # 复用，原则上不重写
│
└── config/
    └── ...                       # 增加 Hybrid NLU 阈值配置
```

如果项目已有同职责模块：

> 必须修改现有模块，不得创建重复类。

---

# 22. 推荐开发步骤

必须按小步执行，并且每一步测试通过再继续。

## Step 1：仅完成当前代码审计

先输出：

```text
当前 classifier 调用链
当前 entity extractor
当前 validator
当前 routing
当前 slot_check
当前 get_llm
当前 structured classifier
```

确认：

```text
哪些是真实实现
哪些是 Mock
哪些已经接线
哪些未接线
```

这一阶段禁止改代码。

## Step 2：补齐 LLM Structured Output

只修改：

```text
StructuredLLMClassifier
```

完成真实：

```text
get_llm()
structured output
timeout
schema validation
fallback
```

测试通过再继续。

## Step 3：新增 LLM Entity + Entity Fusion

完成：

```text
Rule Entity
+
LLM Entity
+
EntityCandidate
+
EntityFusionService
```

先独立单测，不接 LangGraph。

## Step 4：完成 Hybrid Intent Policy

实现：

```text
Rule HIGH
Rule MEDIUM
Rule LOW
```

以及：

```text
should_call_llm
intent fusion
conflict → clarify
```

必须完全单测。

## Step 5：把 Hybrid NLU 接入 `intent_parse`

只替换：

```text
NLU 内部调用方式
```

不要动：

```text
slot_check
tool_dispatch
response_gen
hallucination_guard
```

## Step 6：验证 Validator + Conditional Edge

确认：

```text
HybridResult
→ Validator
→ TurnAction
→ route_after_intent
```

以及：

```text
SlotCheck
→ missing_slots
→ route_after_slot_check
```

## Step 7：真实端到端测试

必须连接当前真实：

```text
LLM
MySQL
Redis
商品数据
LangGraph
```

不能只做 Mock。

---

# 23. 必须新增的单元测试

至少包括以下场景。

## A. Rule 高置信度，不调用 LLM

输入：

```text
查询订单 O20260811000004 的物流
```

预期：

```text
rule intent = logistics_query
LLM called = false
order_id = rule
ACCEPT
```

## B. Rule 中置信度，LLM 同意

输入：

```text
这个现在有活动吗？
```

有商品上下文。

预期：

```text
Rule medium
LLM called
LLM = promotion_query
final = promotion_query
```

## C. Rule 与 LLM 冲突

预期：

```text
不能静默选择
→ CLARIFY
```

## D. LLM Timeout

预期：

```text
HTTP 不得 500
根据规则置信度：
Rule 足够 → Rule
Rule 不足 → CLARIFY
```

## E. 规则实体不可被 LLM 覆盖

输入：

```text
29570 黑色 M 码
```

LLM 即使返回：

```text
product_id=15970
```

最终必须：

```text
product_id=29570
source=rule
```

## F. Brand 抽取

输入：

```text
有没有 Puma 的运动鞋？
```

预期：

```text
brand=Puma
```

并能通过品牌目录校验。

## G. Product Name 抽取

输入：

```text
Just Natural 中性防雨夹克有活动吗？
```

预期至少得到：

```text
brand=Just Natural
product_name=中性防雨夹克
intent=promotion_query
```

随后交给 ProductReferenceResolver。

## H. Price 抽取

输入：

```text
推荐300元以内的夹克
```

预期：

```text
max_price=300
source=rule
```

## I. 多轮 Context 不得被 Hybrid NLU 破坏

对话：

```text
用户：最近有什么促销？
AI：请提供商品编号
用户：15970
AI：当前没有促销
用户：那29570呢？
```

预期：

```text
Context Resolver 继承 promotion_query
product_id=29570
不得识别为 chitchat
```

## J. Slot Check 仍然工作

输入：

```text
我想查物流
```

预期：

```text
intent=logistics_query
missing_slots=["order_id"]
WAITING_SLOT
respond
不得 tool_dispatch
```

---

# 24. 必须新增的集成测试

至少覆盖：

```text
规则 HIGH → 不调用 LLM
规则 MEDIUM → LLM
规则 LOW → LLM
LLM timeout
LLM invalid output
Rule/LLM intent conflict
Rule/LLM entity conflict
brand
product_name
price
size
color
product_id
order_id
多轮省略追问
缺槽补槽
Task resume
```

建议记录测试指标：

```text
intent accuracy
entity precision
entity recall
clarify rate
LLM call rate
LLM fallback rate
average latency
task completion rate
```

---

# 25. 验收标准

本次改造完成必须同时满足以下条件。

## 架构

- [ ] 未新增第二套 LLM Client
- [ ] 未重写 LangGraph 主图
- [ ] Validator 仍为 NLU Policy → Routing 的中间层
- [ ] SlotCheck 职责未被 LLM 侵入
- [ ] Context Resolver 与 NLU 职责分离

## Intent

- [ ] Rule Classifier 保留
- [ ] Structured LLM 真正调用模型
- [ ] Rule 高置信度可跳过 LLM
- [ ] Medium/Low 可进入 LLM
- [ ] Rule/LLM 冲突不会静默误判
- [ ] LLM 异常不会让 Chat API 直接 500

## Entity

- [ ] `product_name`
- [ ] `brand`
- [ ] `price`
- [ ] `size`
- [ ] `color`

五类核心实体均支持。

同时：

- [ ] `product_id/order_id/sku_id` 不允许被 LLM 幻觉覆盖
- [ ] 实体带 `source/confidence`
- [ ] 存在明确 Entity Fusion
- [ ] Product Name 最终通过业务 Resolver 验证

## Routing

- [ ] Intent confidence 通过 Classifier/Validator 转成 TurnAction
- [ ] Routing 不直接硬编码 LLM 阈值
- [ ] 缺槽 → respond
- [ ] 槽位完整 → tool_dispatch
- [ ] 原有条件边正常工作

## 测试

- [ ] 新增单测
- [ ] 新增集成测试
- [ ] 真实 LLM 测试通过
- [ ] Redis/MySQL 实际环境测试通过
- [ ] 多轮追问测试通过

---

# 26. 推荐参考的 GitHub 项目

以下项目只用于参考设计，不允许直接整体搬入当前工程。

## 26.1 AgenticX

仓库：

https://github.com/DemonDamon/AgenticX

重点参考：

```text
examples/agenticx-for-intent-recognition/tools/hybrid_extractor.py
examples/agenticx-for-intent-recognition/tools/rule_extractor.py
examples/agenticx-for-intent-recognition/tools/llm_extractor.py
```

借鉴：

```text
Rule + LLM + 多来源实体融合
不同实体类型不同权重
冲突解决
```

注意：

> 示例 LLMExtractor 中部分调用是演示/Mock，不要照搬其 LLM Client。

## 26.2 ai-pipeline-orchestrator

仓库：

https://github.com/emmanuel-adu/ai-pipeline-orchestrator

借鉴：

```text
keyword/rule first
confidence threshold
LLM fallback
hybrid mode
```

适合当前项目的：

```text
Rule HIGH → skip LLM
Rule LOW → LLM
```

思想。

## 26.3 ag-advisor-agentic-ai

仓库：

https://github.com/Sanjeeda-Jeba/ag-advisor-agentic-ai

重点参考：

```text
src/tools/tool_matcher.py
src/tools/llm_intent_classifier.py
```

借鉴：

```text
高置信度规则直接返回
低置信度 LLM
中间区间 Rule + LLM 联合决策
```

## 26.4 lastmile-ai/mcp-agent

仓库：

https://github.com/lastmile-ai/mcp-agent

重点参考：

```text
src/mcp_agent/workflows/intent_classifier/intent_classifier_llm.py
```

借鉴：

```text
Structured LLM Intent
confidence
extracted_entities
Pydantic/结构化输出
```

## 26.5 Redis banking-agent-semantic-routing-demo

仓库：

https://github.com/redis-developer/banking-agent-semantic-routing-demo

重点参考：

```text
router_bank.py
orchestrator.py
```

借鉴：

```text
Intent
Confidence
Required Slots
Missing Slots
Conditional Routing
```

这是与当前：

```text
intent_parse → slot_check → conditional edge
```

最接近的参考之一。

## 26.6 LangGraph 官方文档仓库

仓库：

https://github.com/langchain-ai/docs

重点搜索：

```text
add_conditional_edges
StateGraph
routing
```

用于确认：

```text
Graph Edge 读取 State
Routing Function 返回下一节点
```

的官方使用方式。

---

# 27. 明确禁止的改造方式

Augment 不得：

```text
❌ 删除现有 Rule Classifier
❌ 所有请求都强制调用 LLM
❌ 让 LLM 直接决定 Tool
❌ 让 LLM 自己生成 product_id/order_id
❌ 在 routing.py 重复实现一套 confidence policy
❌ 重新写第二套 Slot Manager
❌ 用 dict.update() 直接覆盖 Rule Entity
❌ 因为参考 GitHub 项目就重写整个 Agent
❌ 用 Mock LLM 通过最终验收
❌ LLM 出错时让 API 返回 500
❌ 跳过单测直接改整个 Intent 模块
```

---

# 28. 最终目标状态

本次完成后，应形成：

```text
User Message
      │
      ▼
Context Resolver
      │
      ▼
Rule Intent + Rule Entity
      │
      ▼
Hybrid NLU Policy
      │
      ├── High → Rule
      │
      ├── Medium → Rule + LLM
      │
      └── Low → LLM
      │
      ▼
Entity Fusion
      │
      ▼
Final Structured NLU Result
      │
      ▼
IntentDecisionValidator
      │
      ├── Clarify → Response
      │
      └── Accept
              │
              ▼
           Task
              │
              ▼
          Slot Check
         ┌────┴─────┐
         │          │
     Missing       Ready
         │          │
      Respond   Tool Dispatch
```

这个结构同时满足：

```text
规则的稳定性
+
LLM 的泛化性
+
置信度控制
+
槽位完整性分流
+
多轮上下文继承
+
可测试
+
可观测
+
可降级
```

并且不会破坏现有项目已经搭好的 LangGraph、Task、Redis Checkpoint、Validator 和 ToolRuntime 体系。

---

# 29. Augment 执行要求

Augment 在真正改代码前，必须先输出一份“当前代码审计结果”，至少说明：

```text
1. 当前 IntentClassifier 的真实调用路径
2. StructuredLLMClassifier 哪些函数仍是 Mock/TODO
3. 当前 EntityExtractor 支持哪些实体
4. 当前 get_llm() 的初始化方式
5. 当前 Validator 如何消费 confidence
6. 当前 route_after_intent 如何工作
7. 当前 slot_check / route_after_slot_check 如何工作
8. 本次准备修改哪些文件
9. 本次不会修改哪些文件
10. 是否发现本文档与当前代码不一致
```

如果发现当前仓库已经发生变化：

> 必须以当前代码事实为准，先说明差异，再按本文档的“职责边界与最终目标”适配；不得机械创建重复类或重复文件。

每完成一个阶段：

```text
修改
→ 新增测试
→ 执行测试
→ 通过
→ 再进入下一阶段
```

禁止一次性大范围改完再统一排错。

---

# 30. 最终审核结论

本次 NLU 改造的重点不是“增加一个 LLM API 调用”。

真正要补齐的是：

```text
规则 Intent
+
真实 Structured LLM Intent
+
规则 Entity
+
真实 LLM Entity
+
Entity Fusion
+
Hybrid Confidence Policy
+
Validator
+
Slot Completeness
+
Conditional Routing
```

其中：

```text
Validator
Slot Check
Conditional Routing
LangGraph 主图
LLM Infrastructure
```

当前项目已有较好的基础，应优先复用。

真正需要新增或补齐的核心只有：

```text
1. StructuredLLMClassifier 的真实 LLM 调用
2. Hybrid Intent Policy
3. LLM Entity Extraction
4. Entity Fusion
5. product_name / brand 等实体能力
6. intent_parse 对 Hybrid NLU 的正式接线
7. 完整测试与可观测日志
```

执行本文件时，应以“小步修改、每步测试、保持现有职责边界”为最高原则。
