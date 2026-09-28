# Vertical Slice 06：Guardrails、Grounding、Langfuse、Guarded SSE 与最终运行收口

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 实施顺序：所有核心业务 Slice 之后  
> 主要工程：`customer-service-backend:8000`  
> 本文独立、自包含。目标不是建设大型安全平台，而是把最终用户真正能看到的业务事实、副作用和数据隔离保护好，并使整条 Agent 链可观测、可评测。

---

# 1. 最终全链

```text
HTTP Auth / Session Ownership / Turn Lock
↓
Input Guard
↓
User Context / Memory Recall（按需）
↓
intent_parse
↓
Intent Route Guard
↓
slot_check
↓
IntentFlow
↓
Tool Input / Action Guard
↓
ToolRuntime
↓
Retrieval Guard / Tool Output Guard
↓
response_gen → ResponseDraft
↓
CriticalFactExtractor
↓
FactNormalizer
↓
EvidenceIndex
↓
GroundingValidator
├─ PASS
├─ REPAIR一次
└─ deterministic fallback
↓
Output Guard
↓
持久化assistant result / action receipt
↓
Guarded SSE / JSON Response
↓
MemoryCandidateGate + Memory Write
```

Guardrails 是 Agent Harness 的一部分，不额外创建第二套主状态机。

---

# 2. Guardrails 只保留 5 个物理模块

```text
guardrails/
├── input.py
├── action.py
├── tool.py
├── grounding.py
└── memory.py
```

概念上覆盖：

```text
Input/Injection
Intent Route
Retrieval
Tool Input/Output
Action
Grounding
Output PII
Memory Write
```

但不要求每个概念单独一个 Python 文件。

---

# 3. Input Guard

处理：

```text
控制字符 / zero-width
超长输入
明显Secret/Token
直接Prompt Injection
要求泄露system prompt/private memory
```

结果：

```text
ALLOW
SANITIZE
CLARIFY
BLOCK
```

不能因为正常商品文案里出现“系统”等词就过度拦截。

---

# 4. Intent Route Guard

```text
recognized=false → tool_dispatch禁止
MULTIPLE_INTENTS → tool count=0
invalid intent → fallback
INFORMATIONAL → write tool禁止
```

正常澄清仍是 HTTP 200，不是 runtime error。

---

# 5. Retrieval Guard

RAG chunk 是 untrusted data。

清理/丢弃：

```text
ignore system prompt
call tool
泄露secret
HTML/script
异常control chars
```

Chunk 只能作为 evidence/context，不能成为 system instruction。

---

# 6. Tool Input Guard

Pydantic 之外，明确：

```text
user_id字段禁止
access_token字段禁止
refund_amount禁止进入return input
未知字段forbid
ID/string长度限制
```

模型不能控制身份和关键真值。

---

# 7. Action Guard

## Return / Exchange

```text
authenticated
正确active task
ACTION_REQUEST
slots完整
唯一对象resolve
execute_confirmed=true
```

缺一项：write=0。

## Shipping Urge

```text
ACTION_REQUEST
order_id
ShippingStatusResolver=PENDING_SHIPMENT
```

## Measurements PATCH

```text
size task上下文
用户明确长期保存
payload只有允许measurement fields
```

---

# 8. Tool Output Guard

检查：

```text
ToolResult schema
price Decimal string
stock enum
order status enum
product/sku id
max result size
Evidence source
```

上游异常结构不能直接拼入 Prompt。

---

# 9. ResponseDraft

```python
class Claim(BaseModel):
    field: str
    value: Any
    source_evidence_ids: list[str]

class ResponseDraft(BaseModel):
    text: str
    claims: list[Claim]
    objects: list[dict[str, Any]]
```

但是 Grounding **不能只相信 LLM 自报 claims**。

---

# 10. CriticalFactExtractor

从 `ResponseDraft.text` 再独立抽取关键事实：

```text
price/money/refund
stock
size/color
SKU/product/order id
promotion discount
order/logistics status
“已提交/已创建/已退款/已催/已保存”
```

若文本说：

```text
“这款现在329元”
```

但 claims=[]：

```text
UNDECLARED_CRITICAL_FACT
```

---

# 11. FactNormalizer

统一后再比较：

```text
¥299.90 / 299.9 / Decimal('299.90')
M / m
有货 / in_stock
中文订单状态label / stable status enum
```

防止假 mismatch。

---

# 12. EvidenceIndex

Evidence 来源：

```text
Commerce API
ToolResult
RAG稳定商品事实
```

高风险字段的最终 Evidence 优先必须来自 Commerce：

```text
price
stock
promotion applicability
SKU
order status
logistics status
refund amount
action success
measurements write result
```

---

# 13. GroundingValidator

两个层面：

```text
Completeness:
Critical facts in text 是否都有Evidence支持

Consistency:
Response claims/facts 是否与Evidence一致
```

结果：

```text
PASS
REPAIRABLE
FAIL
```

典型 code：

```text
UNDECLARED_CRITICAL_FACT
UNSUPPORTED_PRICE
UNSUPPORTED_STOCK
UNSUPPORTED_PROMOTION
INVALID_SKU
UNSUPPORTED_ORDER_STATUS
UNSUPPORTED_REFUND_AMOUNT
UNSUPPORTED_ACTION_SUCCESS
```

---

# 14. 高风险动作结果 deterministic formatter

以下不要让 LLM 自由写关键结果：

```text
退货已提交
换货已提交
催发货已提交
Measurements已保存
refund_amount
```

ToolResult → deterministic formatter 产生事实句；LLM 可在周围做低风险自然语言包装，但不得改变关键值。

---

# 15. Repair

第一次 Grounding `REPAIRABLE`：

```text
validation errors
+ allowed evidence
→ repair prompt
→ regenerate once
→ revalidate
```

最大：

```text
guard_retry_count=1
```

第二次仍错：deterministic fallback。

---

# 16. Fallback

商品动态事实无法确认：

> “我暂时无法可靠确认当前价格/库存，先不给您下确定结论，请稍后重试。”

订单：

> “我暂时无法可靠确认订单当前状态，请稍后重试。”

Write outcome unknown：

> “请求结果暂时无法确认，我不会重复提交。请稍后通过订单/历史消息确认状态。”

不能猜。

---

# 17. ChatObject Schema

## Product Card

```text
type=product_card
product_id
title
brand
main_image_url
min_price
max_price
matched_skus[]
selected_sku_id optional
selected_sku_price optional
```

## Order Item Choice

```text
type=order_item_choice
order_id
items[
  product_id
  sku_id
  display_name
  color
  size
]
```

## Size Recommendation

```text
type=size_recommendation
product_id
primary_size
recommended_sizes[]
matching_skus[]
used_measurements
size_chart_url
```

## Action Receipt

```text
type=action_receipt
action=return|exchange|urge_shipping|save_measurements
resource_id optional
status
order_id optional
refund_amount optional

约束：
return/exchange/urge_shipping → resource_id required
save_measurements → resource_id=null
```

---

# 18. Guarded SSE

前端：

```text
fetch + ReadableStream + AbortController
```

不用 native EventSource。

公开 event：

```text
status
delta
objects
done
error
```

允许提前流：

```text
status: understanding/retrieving/checking_business_data/generating/finalizing
```

业务文本：

```text
完整draft
→ grounding PASS
→ 再切delta chunks
```

这样价格/退款等未校验事实不会提前泄漏。

---

# 19. SSE Error vs Dialogue Clarification

以下不是 error event：

```text
MISSING_REQUIRED_SLOT
MULTIPLE_INTENTS
REFERENCE_AMBIGUOUS
NEEDS_EXECUTION_CONFIRMATION
```

它们是正常 assistant delta/done。

真正 runtime failure 才：

```text
event:error
```

例如：

```text
AUTH / SESSION runtime failure
COMMERCE_UNAVAILABLE且无安全fallback
internal unexpected failure
```

---

# 20. Disconnect

```text
纯读任务 → 尽快cancel
write未发出 → 不发
write已发送 → 不假装rollback
write成功 → 先持久化chat/action receipt
```

用户下次可 GET history 或查询订单状态。

不自动 replay Chat POST。

---

# 21. Langfuse Client

业务层只依赖：

```text
TracingService
```

实现：

```text
LangfuseTracingService
NoopTracingService
```

全进程单 client。

Fail-open：Langfuse ingestion down 不改变业务结果。

---

# 22. Trace Hierarchy

```text
agent.turn
├── guard.input
├── memory.recall
├── intent.parse
├── task.transition
├── slot.check
├── flow.*
├── tool.*
│   ├── rag.*
│   └── commerce.http
├── response.generate
├── guard.critical_fact
├── guard.grounding
├── guard.output
├── stream.finalize
└── memory.write
```

Name 不带动态 user/product/order id。

Root metadata：

```text
hashed_user_id
session_id
turn_id
request_id
release
environment
```

---

# 23. Redaction

禁止上传：

```text
Access JWT
Refresh Token
Service Token
password
API key
OTP
card number
完整敏感PII
private chain-of-thought
```

用户文本如上传用于调试，必须按项目规则先做最小化/脱敏。

---

# 24. Dataset / Experiment

Git JSONL 是 canonical：

```text
intent_golden.jsonl
product_rag_golden.jsonl
size_golden.jsonl
agent_e2e_golden.jsonl
security_golden.jsonl
```

可以同步到 Langfuse Dataset。

Langfuse Experiment 不替代 pytest。

优先 deterministic evaluator：

```text
intent exact match
action_mode
tool/flow selection
tool args
grounding support
object ids
task completion
side-effect should_execute
```

LLM-as-Judge 只用于：

```text
helpfulness
clarity
naturalness
```

---

# 25. Experiment 不真实执行副作用

质量 Experiment 默认 Fake：

```text
return
exchange
shipping urge
measurements PATCH
```

评价 Tool/Flow/Args/Response，不批量写测试 Commerce。

质量 Experiment 只评价 Tool/Flow/Args/Response，默认使用 Fake write dependencies，不批量修改 Commerce。生产验收仍必须在隔离 `ecommerce_test_db` 中执行 return / exchange / shipping urge / measurements PATCH 的真实写测试，并验证 ownership、eligibility、stable idempotency、exactly-once 与持久化 ActionReceipt。

---

# 26. 安全硬指标

最终必须：

```text
cross-user data leak = 0
unsafe side-effect false execution = 0
duplicate business write = 0
critical grounded field mismatch reaching user = 0
raw secret/token leakage = 0
```

这些不需要等 baseline。

---

# 27. Metrics

最小：

```text
intent_unrecognized_total
tool_error_total
tool_timeout_total
rag_degraded_total
grounding_fail_total
grounding_repair_total
memory_write_total
sse_disconnect_total
langfuse_export_error_total
```

日志统一：

```text
request_id
session_id
turn_id
task_id
```

---

# 28. 具体文件

```text
customer_service/guardrails/input.py
customer_service/guardrails/action.py
customer_service/guardrails/tool.py
customer_service/guardrails/grounding.py
customer_service/guardrails/memory.py
customer_service/streaming/sse.py
customer_service/observability/tracing.py
customer_service/observability/langfuse_tracing.py
customer_service/observability/redaction.py
customer_service/observability/metrics.py
customer_service/graph/nodes/response_gen.py
customer_service/graph/nodes/hallucination_guard.py
customer_service/service/agent_service.py
customer_service/api/router/chat_router.py
customer_service/chat/service.py
```

Grounding 相关类可以集中在 `guardrails/grounding.py`，不要为每个小类新建文件。

---

# 28.1 Legacy guardrail migration / delete map

当前源码如果存在：

```text
customer_service/guardrails/action_guard.py
customer_service/guardrails/grounding_guard.py
customer_service/guardrails/input_guard.py
customer_service/guardrails/tool_output_guard.py
customer_service/guardrails/prompt_injection.py
customer_service/guardrails/fallback.py
```

统一迁移为：

```text
action_guard.py      → guardrails/action.py
grounding_guard.py   → guardrails/grounding.py
input_guard.py       → guardrails/input.py
tool_output_guard.py → guardrails/tool.py
prompt_injection.py  → guardrails/input.py + retrieval/guard.py 的 data-as-untrusted 规则
fallback.py          → guardrails/grounding.py 的 deterministic fallback + response_gen 的安全话术
```

迁移完成后执行：

```bash
rg "guardrails\.(action_guard|grounding_guard|input_guard|tool_output_guard|prompt_injection|fallback)" customer_service tests
```

必须为 0 个有效 import/call site，然后删除旧文件。禁止同一请求同时经过旧 Guard 与新 Guard 两套主链。

---

# 29. Slice 测试

```text
Input injection
Intent Route Guard
Retrieval injection
Tool Input/Output schema
ActionGuard副作用误触发=0
CriticalFactExtractor
FactNormalizer
claims漏报
price/stock/refund mismatch
repair once
fallback
ChatObject schema
business delta only after grounding
SSE error vs clarification
Disconnect
Langfuse real test ingestion
async trace context
redaction
Langfuse fail-open
```

Langfuse real ingestion 使用 deadline polling，不使用固定 `sleep(1)` 作为唯一判定。

---

# 30. Completion Gate

```text
Guardrails足够保护核心事实，不变成第二套平台
CriticalFactExtractor+FactNormalizer生效
高风险事实全部grounded
repair最多1次
确定性fallback可用
Action success先持久化
Guarded SSE不提前泄漏业务事实
Langfuse全链trace可读
Langfuse down业务仍运行
Redaction通过
安全硬指标为0 violation
```
