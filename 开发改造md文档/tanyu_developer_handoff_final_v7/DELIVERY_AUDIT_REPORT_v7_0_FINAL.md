# 探域电商售前 Agent：Developer Handoff Final 最终一致性审计报告

> 审计版本：v7.0 Final  
> 日期：2026-09-22  
> 审计范围：`00_overall_architecture_living_contract.md` ～ `08_cross_service_e2e_eval.md`、`README_FINAL_VERTICAL_SLICE_DOCSET.md`  
> 结论：**Developer Handoff Final**。本轮原有 **10 个 P0 + 3 个 P1 已全部关闭；最终复核未发现新的 P0/P1 冲突。**

---

# 1. 本轮冻结原则

本轮不增加新 Agent、新 Graph Node、新基础设施或第二套 Framework，只收口已经确认的项目 Contract。

所有 `00~08` 文档必须满足：

```text
独立
自包含
可单独交给 Codex 执行
```

禁止使用以下方式交代核心实现：

```text
在上一版基础上修改
沿用之前方案
参考前一个 MD
去其他 Slice 才能知道字段/API/Enum/Fixture
```

文档可以说明施工顺序和跨服务依赖，但关键 Schema、Enum、Registry、API、具体文件、测试和 Completion Gate 必须在本文件中给出足够的正式定义。

---

# 2. 10 个 P0 关闭结果

## P0-1：00 总纲旧 Size 算法定义 —— CLOSED

`00` 已冻结为：

```text
Commerce SizeChart rows
+ products.size_recommendation_rules JSON NULL
+ RangeBasedSizeRecommendationService
+ Commerce SKU / Stock truth
```

历史 `customer_service/tools/size_recommend.py` 只可迁移 normalization、validation、SKU helper、错误处理和测试样本；旧隐式算法不再是正式 Contract。

## P0-2：Foundation 核心 Schema 缺失 —— CLOSED

`01` 已给出正式最小 Schema：

```text
SessionUserContext
ConfirmationKind
PendingConfirmation
ToolSpec
ToolExecutionContext
ToolResult
ToolError
EvidenceItem
```

其中 `ConfirmationKind` 固定包含：

```text
EXECUTE_RETURN
EXECUTE_EXCHANGE
CONFIRM_STORED_MEASUREMENTS
SAVE_MEASUREMENTS
```

## P0-3：IntentFlowRegistry 仅注册 4/9 —— CLOSED

最终注册闭环：

```text
02 → PRODUCT_QUERY / PROMOTION_QUERY / URGE_ORDER_PAYMENT / CHITCHAT
03 → SIZE_RECOMMEND
04 → LOGISTICS_QUERY / RETURN / EXCHANGE / URGE_SHIPPING
```

总计：

```text
9 / 9 BusinessIntent
```

并明确全项目只使用：

```text
customer_service/flows/registry.py
```

一个主 `IntentFlowRegistry`。

## P0-4：IntentPolicy 没有最终 9 行 Matrix —— CLOSED

`01` 与 `07` 均已冻结同一 9 行 Matrix，并通过程序化比较一致。

核心值：

```text
product_query      → product_search_tool + selling_point_tool / no write
size_recommend     → size_recommend_tool / no business write
urge_order_payment → no business Tool / no write
promotion_query    → promotion_query_tool / no write
logistics_query    → logistics_query_tool / no write
return             → return_request_tool / action + confirmation
exchange           → exchange_request_tool / action + confirmation
chitchat           → no business Tool
urge_shipping      → urge_shipping_tool / action / no second execute confirmation
```

`save_measurements` 是 `UserContextWriteService` 的受控 post-action，不属于 LLM Business Tool。

## P0-5：真实源码路径错误/遗漏 —— CLOSED

已统一：

```text
app/api/public/user.py
app/models/product.py
app/api/internal/skus.py
```

已确认文档集中不存在：

```text
app/api/public/users.py
app/models/products.py
```

作为正式实现路径。

## P0-6：04 Exchange API 缺 method/path/header —— CLOSED

`04` 已完整冻结：

```http
POST /api/v1/orders/{order_id}/exchange-requests
Authorization: Bearer <USER_ACCESS_TOKEN>
Idempotency-Key: <stable-key>
Content-Type: application/json
```

并明确 request、response、ownership、same-product、stock、eligibility、business conflict、idempotency error 与 validation error。

## P0-7：00 未同步 Size 数据演进字段 —— CLOSED

`00` 已明确：

```text
products.size_recommendation_rules JSON NULL
```

并声明该字段是 Commerce 商品业务数据，不由 LLM 或 SizeChart rows 运行时推导。

## P0-8：Size E2E Fixture alias 缺失 —— CLOSED

`08` 的 deterministic Manifest 已冻结 7 个 Size alias：

```text
SIZE_PRODUCT_SINGLE_RANGE
SIZE_PRODUCT_SHOES_THREE
SIZE_PRODUCT_BOUNDARY
SIZE_PRODUCT_AMBIGUOUS_RANGE
SIZE_PRODUCT_NO_MATCH
SIZE_PRODUCT_RECOMMENDED_OOS
SIZE_PRODUCT_RECOMMENDATION_UNAVAILABLE
```

每个 alias 都绑定明确 E2E Case；测试只消费 alias，不自行硬编码 ID。

## P0-9：ActionReceipt.resource_id 与 save_measurements 冲突 —— CLOSED

统一为：

```text
resource_id optional
```

固定语义：

```text
return/exchange/urge_shipping → resource_id required
save_measurements             → resource_id=null
```

`03 / 06 / 07 / 08` 已同步。

## P0-10：低置信度 IntentDecision 语义不唯一 —— CLOSED

冻结：

```text
ACCEPT
→ recognized=true, intent=<BusinessIntent>

CLARIFY / LOW_CONFIDENCE
→ recognized=false, intent=null

OUT_OF_SCOPE
→ 只有 classifier 明确判断不属于 9 类业务范围

CLASSIFIER_FAILURE
→ 只有 LLM/API/schema parse 真正失败
```

`<0.55` 不再直接映射 `OUT_OF_SCOPE/CLASSIFIER_FAILURE`。

---

# 3. 3 个 P1 关闭结果

## P1-1：旧实现迁移/删除映射不完整 —— CLOSED

### Tool

```text
customer_service/tools/builder.py
→ tools/registry.py + tools/runtime.py + tools/models.py + tools/context.py
```

迁移后必须 `rg` 0 个有效 import/call site，再删除旧文件。

### Memory

```text
memory/manager.py
memory/long_term.py
memory/short_term.py
memory/semantic_memory.py
memory/write_service.py
```

均已在 `05` 给出逐文件职责迁移目标与删除条件，禁止旧 `MemoryManager` 与新 Service 双写。

### Guardrails

```text
guardrails/action_guard.py
guardrails/grounding_guard.py
guardrails/input_guard.py
guardrails/tool_output_guard.py
guardrails/prompt_injection.py
guardrails/fallback.py
```

均已在 `06` 映射到 5 个正式 Guardrail 物理模块，并要求迁移后旧 import/call site 为 0。

## P1-2：依赖其他 Slice 才能理解的表述 —— CLOSED

已删除/改写：

```text
Concrete Flow 从下一 Slice 开始逐个落地
UrgeOrderPaymentFlow 在本 Slice 之后增强为
真实 write correctness 在 Slice04...
```

改为当前文件内直接声明最终接口、施工边界和验收要求。

## P1-3：README / Manifest 过期 —— CLOSED

README 已重写为 v7.0 Developer Handoff Final，并同步：

```text
Range-Based Size Recommendation
products.size_recommendation_rules JSON NULL
9 Intent
8 Tool
9 Flow
ActionReceipt optional resource_id
7 Size fixture aliases
```

`DOCUMENT_MANIFEST.json` 在所有最终文档定稿后重新计算 SHA-256、行数、字节数与 Markdown fence 状态。

---

# 4. 额外细致审核结果

除原 13 项外，本轮又做了以下交叉审核。

## 4.1 Registry

```text
BusinessIntent = 9
IntentFlowRegistry registrations = 9
Tool = 8
LangGraph Node = 5
```

未发现第二个 Flow Registry 设计。

## 4.2 Enum

`OrderStatus` 在 `04 / 07` 保持同一 7 值：

```text
pending_payment
pending_shipment
awaiting_pickup
in_transit
awaiting_receipt
completed
canceled
```

`ConfirmationKind` 在 Foundation / Size / Order 文档中语义一致。

## 4.3 API

对重复出现的 API path 做 method 交叉检查，未发现同一路径的矛盾 method 定义。

重点写 API 在 `04 / 07` 已统一：

```text
POST /api/v1/orders/{order_id}/return-requests
POST /api/v1/orders/{order_id}/exchange-requests
POST /api/v1/orders/{order_id}/shipping-urge-requests
```

均使用 User Bearer + stable `Idempotency-Key`。

## 4.4 Size

全套文档正式计算 Service 名称统一为：

```text
RangeBasedSizeRecommendationService
```

以下仅作为“禁止/历史迁移说明”出现，不再作为第二套主实现：

```text
characterization
nearest-distance
历史 size_recommend.py algorithm
第三方 Size MCP
Size ML
LLM size calculation
```

## 4.5 ActionReceipt

统一：

```text
action=return|exchange|urge_shipping|save_measurements
resource_id optional
```

并明确 `save_measurements` 不创建 resource。

## 4.6 Self-contained

`00~08` 已扫描历史依赖式表达，没有发现要求开发者“先读上一版/前一个 MD 才能知道核心实现”的残留。

## 4.7 Markdown

`00~08` Markdown code fence 全部成对闭合。

---

# 5. 程序化最终检查

最终检查脚本共执行：

```text
128 checks
128 passed
0 failed
```

覆盖：

```text
版本与日期
Markdown fences
历史依赖表述
10 P0 closure
3 P1 closure
核心 Schema
9 Flow Registry
9-row IntentPolicy
真实源码路径
Exchange API
Size fixture aliases
ActionReceipt
Intent low-confidence mapping
Legacy migration maps
OrderStatus
8 Tool
9 Flow
write API idempotency headers
关键 Slice 自包含 Schema
```

---

# 6. 最终结论

本轮最终状态：

```text
P0 open = 0
P1 open = 0
mechanical/contract checks failed = 0
```

因此该文档集可标记为：

```text
Developer Handoff Final
v7.0
```

这表示**文档 Contract 已具备交开发者/Codex 施工的内部一致性**；它不代表代码已经实现。真正代码完成仍必须逐份满足各 MD 的 Unit / Component / Integration / E2E / Completion Gate，并在最终 Cross-Service E2E 全绿后冻结 OpenAPI v1.0 snapshot。
