# 探域电商售前 Agent：总体架构、Living Contract 与 Vertical Slice 开发总纲

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 适用工程：`ecommerce-service-backend`、`customer-service-backend`，以及后续 `customer-service-frontend`  
> 本文独立、自包含。开发者只拿到本文，也应能理解项目目标、服务边界、最终架构、开发顺序和每个 Vertical Slice 的验收方式。

---

# 1. 项目目标

本项目复刻“探域电商售前 Agent”的核心能力。目标不是建设通用 Agent 平台，而是用尽量清晰、可测试、可维护的方式实现下列 9 个业务意图：

```text
product_query         商品咨询
size_recommend        尺码推荐
urge_order_payment    催拍催付
promotion_query       促销查询
logistics_query       物流询问
return                退货退款
exchange              换货：同商品换颜色/尺码，不退款
chitchat              闲聊
urge_shipping         催发货
```

`other / unknown / low_confidence / out_of_scope` 不是 BusinessIntent。无法可靠识别时统一：

```text
recognized=false
intent=null
```

项目的技术重点按优先级排列：

| 优先级 | 模块 | 要求 |
|---|---|---|
| 1 | Intent + Task Context | 必须稳定，支持多轮、打断、恢复、澄清 |
| 1 | Tool Runtime + Intent Flow | 必须稳定，Tool 调用可控，副作用安全 |
| 1 | Memory + User Context | 用户隔离清楚，结构化信息与语义记忆不混淆 |
| 2 | Product RAG | 完整实现 Hybrid Retrieval，但不做过度复杂的检索平台 |
| 2 | Size Recommendation | 使用 Commerce 配置的 Range Rules + `RangeBasedSizeRecommendationService`，LLM 不计算尺码 |
| 3 | Guardrails / Grounding | 保护关键价格、库存、订单、退款、副作用事实 |
| 3 | Langfuse | tracing + dataset + experiment，不替代 pytest |
| 3 | SSE | Guarded Streaming，保证用户不会先看到未校验业务事实 |

---

# 2. 两个后端的职责边界

```text
customer-service-frontend :5173
      ├──────────────→ ecommerce-service-backend :8001
      └──────────────→ customer-service-backend  :8000
                                │
                                └── HTTP ───────→ ecommerce-service-backend :8001
```

## 2.1 `ecommerce-service-backend:8001`

唯一 Commerce Truth，负责：

```text
Auth / Access JWT / Refresh Token
User Profile / Preferences / Measurements
Product / SKU / Size Chart
Promotion
Order / Order Item
Logistics
Return / Exchange / Shipping Urge
Idempotency
Static Product Images
Internal Product Truth API
```

8001 必须拥有并最终校验：

```text
订单归属
库存
价格
促销有效性
退货/换货 eligibility
退款金额
催发货 eligibility
副作用幂等
```

## 2.2 `customer-service-backend:8000`

唯一 Agent Orchestration，负责：

```text
Chat Session / Chat Message
LangGraph
Task Stack
Intent / Entity / Slot
IntentFlowRegistry
ToolRuntime
Product RAG
RangeBasedSizeRecommendationService
Memory / User Context
Guardrails / Grounding
Langfuse
SSE
```

8000 禁止：

```text
直接连接 ecommerce_db
导入 Commerce ORM
复制订单 eligibility 规则
计算 refund_amount
把 Qdrant/ES 中的旧价格、库存当真值
让 LLM 自己决定 user_id
```

---

# 3. 开发方式：Living Contract，而不是 Phase 硬冻结

本项目在开发完成前不采用：

```text
先把8001所有字段永久冻死
→ 8000发现缺字段也不能改
→ 只能在Agent里补兼容逻辑
```

采用：

```text
职责边界固定
↓
定义当前 HTTP / Runtime Contract
↓
按 Vertical Slice 开发
↓
如果同一 Slice 暴露跨服务 Contract 缺口
↓
一次 coordinated change 同步修改：
  8001实现
  8001测试
  API Contract
  8000 EcommerceClient
  Agent Flow / Tool
  Slice测试
↓
Cross-Service E2E 全通过
↓
生成 OpenAPI v1.0 Snapshot
↓
正式 Contract Freeze
```

因此开发期“可以改 Contract”，但有两个硬约束：

1. **不能破坏服务 ownership。** 例如 Agent 缺订单 eligibility，正确做法是给 Commerce Order Detail 增加 eligibility，而不是让 Agent 复制 Commerce 规则。
2. **任何跨服务修改必须成组提交。** 不允许只改 8001 不改 8000 Client/Test，也不允许文档和代码长期漂移。

---

# 4. 最终开发文档与施工顺序

最终文档按 Vertical Slice 编排，文档顺序就是开发顺序：

```text
00 总体架构 / Living Contract
        ↓
01 Foundation：Auth + Chat + LangGraph + Task + Intent + ToolRuntime骨架
        ↓
02 Product Slice：商品咨询 + 促销 + 催拍催付 + Product RAG + 基础闲聊
        ↓
03 Size Slice：Range-Based 尺码推荐 + Measurements + SKU/Stock 真值校验
        ↓
04 Order Slice：订单 + 物流 + 催发货 + 退货 + 换货 + 幂等
        ↓
05 Memory Slice：用户上下文 + 语义Memory + 个性化 + 用户隔离
        ↓
06 Finalization：Guardrails + Grounding + Langfuse + SSE
        ↓
08 Cross-Service E2E / Eval
        ↓
OpenAPI v1.0 Freeze
```

`07_api_runtime_contract.md` 是完整 Contract 文档，在每个 Slice 实施时同步维护；开发者不需要等最后才看它。

每一个 Slice 文档内部都必须包含：

```text
业务目标
当前源码问题
Commerce改造
Agent改造
跨服务Contract
具体文件
核心场景
Unit/Component/Integration/Slice-E2E
Completion Gate
明确不做什么
```

不再把“开发文档”和“测试文档”拆成两套平行文档。

---

# 5. LangGraph 主架构固定为五节点

```text
START
  ↓
intent_parse
  ↓
slot_check
  ├─ 缺槽位 / 澄清 / 等待确认 → response_gen
  └─ READY → tool_dispatch
                 ↓
             response_gen
                 ↓
        hallucination_guard
                 ↓
                END
```

固定节点：

```text
intent_parse
slot_check
tool_dispatch
response_gen
hallucination_guard
```

不创建：

```text
9个Intent Node
第二套Supervisor
第二套Flow YAML主状态机
无限Agent Loop
```

业务差异通过普通 Python 层表达：

```text
IntentPolicy
SlotPolicy
IntentFlowRegistry
ToolRegistry
PromptRegistry
```

---

# 6. 单任务 + 暂停 / 压栈 / 恢复

核心规则：

> 一个用户 Turn 最多推进一个可执行 BusinessIntent；跨 Turn 可以被新任务打断，并在新任务完成后恢复。

典型场景：

```text
T1 用户：我要退货
→ return Task
→ 缺 order_id

T2 用户：O1001
→ 继续 return
→ 缺 reason

T3 用户：先帮我查另一个订单 O2002 到哪了
→ pause return
→ push paused_tasks
→ start logistics_query
→ logistics完成
→ pop/resume return
→ 本Turn只提示“刚才退货还差原因”

T4 用户：尺码太小
→ 继续原return
```

同一句多个独立 Intent：

```text
“这个有优惠吗，顺便查O2物流”
→ recognized=false
→ intent=null
→ reason=MULTIPLE_INTENTS
→ 询问先处理哪一个
```

不能在同一 Turn 自动执行两个 Tool。

---

# 7. AgentState：长期状态与 Turn 临时状态分开

Persistent Conversation State：

```text
active_task
paused_tasks
session_user_context
conversation_focus
pending_intent_selection
```

`pending_confirmation` 只存在于：

```text
active_task.pending_confirmation
```

不能再在 AgentState 顶层维护第二份。

Transient Turn State 每次新 Turn 开始必须清理：

```text
current_message
turn_id
intent_result
entities
tool_result
response_draft
task_transition
resumed_this_turn
guard_retry_count
fallback_used
```

由 `TurnInitializer` 在进入 Graph 前统一初始化，不额外增加第六个 Graph Node。

---

# 8. Intent 与业务 Flow 分离

`IntentPolicy` 只回答：

```text
该Intent允许哪些Tool
是否可能产生副作用
是否要求ACTION_REQUEST
是否要求最终执行确认
```

`IntentFlowRegistry` 回答：

```text
识别到这个Intent之后，到底按什么确定性流程执行
```

例如：

```text
urge_shipping
→ ShippingFlow
→ 先查订单真实状态
→ INFORMATIONAL只答状态
→ ACTION_REQUEST + pending_shipment 才创建催发货
→ 已进入物流则返回物流Evidence
```

LLM 不自由规划 Tool。

---

# 9. 催拍催付最终定义

`urge_order_payment` 是正常用户消息触发的 BusinessIntent，不增加客服/运营“点击催一下”的专用 API。

典型表达：

```text
“这个值得买吗？”
“有点贵，我再想想”
“我有点犹豫要不要下单”
“这个适合我吗，我还没决定”
```

执行：

```text
Intent = urge_order_payment
↓
UrgeOrderPaymentFlow
↓
结合：
  当前商品
  用户当前需求
  商品卖点
  当前促销
  可用的显式偏好 / semantic memory
↓
只调用一次response LLM
↓
生成个性化催单话术
```

**不保留 `urge_order_payment_tool`。** 该能力没有独立外部 I/O，本质是 Flow 内证据聚合 + response generation。

---

# 10. Size Recommendation 最终定义

最终唯一正式算法：

```text
Range-Based Size Recommendation
```

明确不做：

```text
不接 Faslet / True Fit / Cabina 等外部 Size MCP
不训练新的 Size ML 模型
不让 LLM 计算尺码
不把历史 size_recommend.py 的隐式算法当正式 Contract
不从商品成衣尺码 rows 自动推导人体适配范围
不使用 nearest-distance 猜码
```

职责固定：

```text
Commerce :8001
→ SizeChart rows：商品尺码事实
→ products.size_recommendation_rules：用户适配 Range 业务规则
→ SKU / Stock 真值
→ user_measurements 持久化真值

Agent :8000
→ Session measurement overrides / confirmed fields
→ RangeBasedSizeRecommendationService
→ [min,max) 确定性范围匹配
→ SKU / Stock 再验证

LLM
→ 只负责询问、确认和解释
→ 不参与数值匹配与选码
```

Commerce 本次必须增加一个可空 MySQL JSON 字段：

```text
products.size_recommendation_rules JSON NULL
```

字段内容固定为：

```text
policy=range_match
required_measurements[]
rules[]
```

每个条件统一使用：

```text
[min,max)
min inclusive
max exclusive
```

一个 Rule 的多个 measurement condition 使用 AND。若多个最高 `priority` Rule 同时命中，合并并去重 `recommended_sizes`；最终候选大于 1 时 `primary_size=null`，禁止 `candidate[0]`。推荐尺码缺货时仍保留算法推荐结果，只追加缺货原因，不偷偷改荐其他尺码。

历史文件：

```text
customer_service/tools/size_recommend.py
```

只允许迁移其中可复用的单位换算、参数校验、SKU helper、错误处理和有价值测试样本。最终该 Tool 必须变薄为：

```text
Commerce I/O
→ RangeBasedSizeRecommendationService
→ SKU / Stock Truth
→ Evidence
```

旧隐式算法分支必须删除，不能与 Range Matcher 形成第二套尺码真值。

---

# 11. Product RAG 最终定义

RAG 是 `product_query` 等商品能力内部子系统，不是独立 Agent。

先分流：

```text
已有明确 product_id / 唯一 focused product
→ Commerce Direct Path

发现型商品咨询
→ ProductRetrievalService
```

Adaptive Retrieval：

```text
Stage 0: 指代解析 / Hard Filters提取
↓
Stage 1: Original/Resolved Query
         Qdrant Dense + ES BM25
↓
Commerce Truth Validation
↓
候选足够？
├─ 是 → 返回
└─ 否 → Stage 2 Multi-query（原query + 最多2个改写）
                ↓
             再召回
                ↓
        仍不足且HyDE显式开启
                ↓
             Stage 3 HyDE
```

默认：

```env
RAG_ENABLE_HYDE=false
```

Preferences / Memory 默认是 soft personalization，不自动变成 hard filter；只有当前 Turn 用户明确说“只要黑色”“预算不超过400”才作为硬约束。

---

# 12. Memory 与用户信息管理

只实现必要的四层：

```text
1. AuthPrincipal                身份
2. LangGraph checkpoint         当前Session任务状态
3. Commerce structured context  Profile/Preferences/Measurements
4. Agent semantic memory        MySQL canonical + Qdrant候选索引
```

不实现：

```text
通用RBAC平台
多租户tenant体系
User Context插件平台
第二套Identity系统
用户资料Redis缓存系统
```

长期 semantic memory scope 只有：

```text
user_id
```

Session scope 由：

```text
thread_id = f"{user_id}:{session_id}"
```

处理。

---

# 13. Profile / Preferences / Measurements

Commerce 概念：

```text
User Profile Aggregate
├── Profile
├── Preferences
└── Measurements
```

Agent 权限：

```text
Profile       → read-only
Preferences   → read-only
Measurements  → read；用户明确确认长期保存时可PATCH
```

精确 Measurements：

```text
当前用户消息
> Session measurement overrides
> Commerce user_measurements
```

不得用 Qdrant semantic memory 中的“体重57kg”作为尺码计算真值。

---

# 14. Tool Harness：重点实现但不平台化

保留：

```text
ToolRegistry
Pydantic args/result
Intent allowlist
ActionGuard
deadline
timeout
read retry
write stable idempotency
concurrency semaphore
ToolError
Evidence
Tool Output Guard
Tracing
Fallback
```

不实现：

```text
复杂通用Circuit Breaker平台
插件市场
动态Provider系统
模型自由Tool Planner
```

最终有 8 个业务 Tool：

```text
product_search_tool
selling_point_tool
size_recommend_tool
promotion_query_tool
logistics_query_tool
return_request_tool
exchange_request_tool
urge_shipping_tool
```

`urge_order_payment` 没有独立 Tool；`chitchat` 没有 Tool。

---

# 15. Guardrails 与 Grounding

重点防：

```text
副作用误执行
价格/库存/退款/订单状态幻觉
跨用户数据
RAG注入
Tool输入/输出异常
Secret/PII泄漏
```

Response 流程：

```text
response_gen
→ ResponseDraft(text, claims, objects)
→ CriticalFactExtractor(text)
→ FactNormalizer
→ EvidenceIndex
→ GroundingValidator
├─ PASS
├─ REPAIR一次
└─ deterministic fallback
```

关键副作用成功消息优先 deterministic formatter。

---

# 16. Langfuse

Langfuse 贯穿运行链路，但不是业务依赖：

```text
tracing
prompt/model/version metadata
dataset
experiment
badcase回流
```

Langfuse 故障：

```text
fail-open
业务继续
```

严禁上传：

```text
Access/Refresh Token
Service Token
password
OTP
完整敏感PII
private chain-of-thought
```

---

# 17. 基础设施与端口

```text
ecommerce-service-backend :8001
customer-service-backend  :8000
customer-service-frontend :5173
MySQL                     :3306
Redis 8+                  :6379
Qdrant                    :6333
Elasticsearch             :9200
TEI / BGE-M3              :8080
Langfuse                  :按部署配置
```

不用 SeaweedFS；商品图片使用 Commerce StaticFiles。

---

# 18. 认证固定边界

8001 使用 RS256 private key 签 Access JWT：

```text
iss=tanyu-ecommerce-service
aud=tanyu-services
sub=user_id
type=access
```

8000 使用 public key 本地验证，不在每次 Chat 请求调用 `/auth/me`。

Internal Commerce API：

```http
Authorization: Bearer <ECOMMERCE_SERVICE_TOKEN>
```

所有 user-scoped Commerce API 使用当前用户 Access JWT。

---

# 19. 数据库与迁移

Commerce：

```text
保留当前业务表
开发期允许必要的向后兼容 Contract 字段调整
本次已冻结的 coordinated change：products.size_recommendation_rules JSON NULL
使用现有轻量 additive scripts / import validation
```

`products.size_recommendation_rules` 是商品业务数据，不是 Agent Memory，也不是由 LLM 或 SizeChart rows 运行时推导的数据；无配置时 `/size-chart` 返回 `recommendation=null`，Agent 只能展示尺码表，不能声称已完成可靠推荐。

Agent：

```text
Alembic
0001 chat runtime
0002 product index manifest
0003 user memory
```

在线 I/O 全部 async；离线脚本可以 sync。

---

# 20. 测试原则

每个 Vertical Slice 自带测试：

```text
Unit
Component
Integration
Slice E2E
```

最终 `08_cross_service_e2e_eval.md` 负责全项目：

```text
9 Intent E2E
Task中断恢复
RAG
Size
Memory
用户隔离
Guardrails
Langfuse Experiment
副作用exactly-once
故障降级
```

硬安全 Gate：

```text
cross-user data leak = 0
unsafe side-effect false execution = 0
duplicate business write = 0
critical grounded fact mismatch reaching user = 0
raw secret/token leakage = 0
```

---

# 21. 最终 Freeze 条件

只有同时满足：

```text
01~06 Slice Completion Gate 全部通过
Cross-Service E2E通过
OpenAPI Contract Test通过
9 Intent关键路径通过
安全硬Gate为0 violation
```

才：

```text
导出 openapi-commerce-v1.json
导出 openapi-agent-v1.json
Tag v1.0
Contract Freeze
```

在此之前，Contract 是 Living Contract，但所有改动必须 coordinated。

---

# 22. 明确禁止的过度开发

```text
❌ 9个独立Agent
❌ 9个LangGraph业务节点
❌ 通用Agent平台
❌ 第三方Size MCP主依赖
❌ 新Size ML训练/Serving
❌ BGE sparse + ColBERT + reranker全家桶
❌ 默认HyDE
❌ 通用RBAC/ABAC平台
❌ 第二套Redis任务状态
❌ Tool插件市场
❌ 自研通用Circuit Breaker平台
❌ Agent直接访问Commerce DB
❌ 生产LLM自由选择任意Tool
```

项目应该保持：功能完整、边界清楚、重点模块做深、辅助模块适度。
