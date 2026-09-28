# Vertical Slice 01：Foundation —— Auth、Chat、LangGraph、Task、Intent 与 ToolRuntime 骨架

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 实施顺序：第一个开发 Slice  
> 涉及工程：`ecommerce-service-backend:8001` + `customer-service-backend:8000`  
> 本文独立、自包含。完成后，系统必须可以完成“登录 → 创建 Chat Session → 发一条消息 → LangGraph 运行 → 得到安全回复”。本文只施工 Foundation；未在本文施工范围内实现的商品/订单业务能力不得用伪造 Commerce 数据或默认 Mock 冒充完成。

---

# 1. Slice 业务目标

本 Slice 不追求一次把商品/订单业务做完，而是建立后续所有 Slice 共用的稳定底座：

```text
Commerce Auth
↓
RS256 Access JWT
↓
Agent 本地验签
↓
Chat Session / Message
↓
LangGraph 五节点
↓
Task Stack / Turn State
↓
Intent structured classification
↓
IntentFlowRegistry / ToolRuntime 接口骨架
↓
response_gen / basic guard
```

最小 E2E：

```text
POST 8001 /auth/login
→ Access JWT
→ POST 8000 /chat/sessions
→ POST /messages {"message":"你好"}
→ chitchat
→ assistant reply
→ chat_messages持久化
```

---

# 2. 当前源码基线

当前 Agent 已有：

```text
customer_service/api/app.py
customer_service/api/dependencies.py
customer_service/api/router/chat_router.py
customer_service/api/schema.py
customer_service/clients/ecommerce.py
customer_service/config/config.py
customer_service/graph/builder.py
customer_service/graph/state.py
customer_service/graph/routing.py
customer_service/graph/nodes/intent_parse.py
customer_service/graph/nodes/slot_check.py
customer_service/graph/nodes/tool_dispatch.py
customer_service/graph/nodes/response_gen.py
customer_service/graph/nodes/hallucination_guard.py
customer_service/tools/base.py
customer_service/tools/registry.py
```

历史代码需要解决：

```text
配置/端口漂移
JWT边界不统一
生产checkpoint不能使用InMemorySaver
Chat SSE历史为假流式/不完整
State没有明确Persistent/Transient生命周期
Intent分类规则/LLM结构化边界不完整
缺少Task Stack正式模型
缺少Session ownership
Tool Runtime参数存在但未真正执行timeout/retry等
Tracing可能no-op
```

---

# 3. Commerce：认证与用户基础接口

## 3.1 Access JWT

8001：

```env
JWT_ALGORITHM=RS256
JWT_ISSUER=tanyu-ecommerce-service
JWT_AUDIENCE=tanyu-services
JWT_PRIVATE_KEY_PATH=./secrets/jwt_private.pem
JWT_PUBLIC_KEY_PATH=./secrets/jwt_public.pem
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
```

Token claims：

```text
sub=<user_id>
type=access
iss=tanyu-ecommerce-service
aud=tanyu-services
iat
exp
```

8000 只使用 public key。

## 3.2 Refresh Token

使用 opaque token：

```text
raw token → HttpOnly cookie
SHA-256(raw) → refresh_token_sessions
rotation
revocation
```

接口：

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/auth/me
```

## 3.3 User Structured Context

本 Slice 建立接口与表，但 Agent 业务使用在后续 Slice 深化：

```text
GET/PATCH /api/v1/users/me/profile
GET/PUT   /api/v1/users/me/preferences
GET/PATCH /api/v1/users/me/measurements
```

概念：

```text
User Profile Aggregate
├── Profile
├── Preferences
└── Measurements
```

Agent 权限最终固定为：

```text
Profile/Preferences read-only
Measurements explicit-confirmed write-back only
```

---

# 4. Commerce 数据库改造

新增：

```text
user_profiles
user_preferences
refresh_token_sessions
idempotency_records
```

`idempotency_records` 可以在本 Slice 建表，但真正副作用行为在 Order Slice 验收。

保持当前业务表兼容：

```text
users
user_auth
user_measurements
products
product_skus
orders
order_items
...
```

Commerce 开发期不是硬冻结；若后续 Slice 发现合理 Contract 缺口，可 coordinated change。

---

# 5. Agent Settings

建议统一：

```env
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=development

ECOMMERCE_API_BASE_URL=http://127.0.0.1:8001
ECOMMERCE_SERVICE_TOKEN=...

JWT_ALGORITHM=RS256
JWT_PUBLIC_KEY_PATH=./secrets/jwt_public.pem
JWT_ISSUER=tanyu-ecommerce-service
JWT_AUDIENCE=tanyu-services

AGENT_ASYNC_DATABASE_URL=mysql+aiomysql://.../customer_service_db
AGENT_SYNC_DATABASE_URL=mysql+pymysql://.../customer_service_db

REDIS_URL=redis://127.0.0.1:6379/0
LANGGRAPH_CHECKPOINT_TTL_MINUTES=1440
MAX_PAUSED_TASKS=3

LLM_BASE_URL=...
LLM_API_KEY=...
LLM_MODEL=...

ENABLE_LANGFUSE=true
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_BASE_URL=...
LANGFUSE_ENVIRONMENT=development
```

依赖版本使用 lockfile 固定。

---

# 6. LLM Call Profiles

不要所有调用共用随机参数。

最低配置：

```text
intent_classifier:
  temperature = 0 / very low
  structured output
  short timeout

entity_supplement:
  temperature = 0 / very low

response_generation:
  controlled low temperature

memory_extract / guard_repair:
  temperature = 0 / very low
```

本文不要求把 provider 做成通用插件平台。

---

# 7. AuthPrincipal 与 RuntimeContext

身份唯一来源：

```text
JWT.sub
```

```python
class AuthPrincipal(BaseModel):
    user_id: str
```

Runtime-only：

```python
class AgentRuntimeContext(BaseModel):
    principal: AuthPrincipal
    request_id: str
    session_id: str
    turn_id: str | None
    request_deadline_monotonic: float
    user_access_token: SecretStr
```

禁止进入：

```text
LangGraph persistent state
Prompt
Memory
Qdrant
Langfuse raw payload
ToolResult
```

任何 LLM-exposed Tool Args 都不能包含：

```text
user_id
access_token
service_token
```

---

# 8. 8000 RS256 本地验签

使用固定：

```text
algorithms=["RS256"]
iss
aud
exp
sub
type=access
```

8000 不在每次请求调用 8001 `/auth/me`。

错误 Access Token → HTTP 401。

---

# 9. Agent MySQL + Alembic

从本 Slice 开始使用 Alembic，不用 runtime `create_all()` 替代迁移。

```text
alembic/
  versions/
    0001_chat_runtime.py
```

## `chat_sessions`

```text
session_id PK
user_id NOT NULL
channel NOT NULL DEFAULT 'web'
status active/closed
created_at
updated_at
last_active_at

INDEX(user_id,last_active_at)
```

## `chat_messages`

```text
message_id PK
session_id NOT NULL
user_id NOT NULL
turn_id NOT NULL
role user/assistant
content TEXT
objects_json JSON/TEXT NULL
created_at

INDEX(session_id,created_at,message_id)
INDEX(user_id,session_id)
```

---

# 10. Chat Session Isolation

所有 session repository 查询直接带：

```sql
WHERE session_id=:session_id
  AND user_id=:authenticated_user_id
```

非本人/不存在：统一 404。

关闭 session：

```text
status=closed
删除对应LangGraph checkpoint thread
chat_messages保留，可由owner继续GET历史
禁止继续POST message
semantic memory不因关闭session删除
```

Checkpoint 自然 TTL 过期但 Session 仍 active 时：

```text
历史消息仍在
下一Turn以无当前Task状态继续
不要从聊天历史自动重建Task Stack
```

---

# 11. 每 Session Turn 串行化

避免同一个 session 同时写 LangGraph state。

推荐 Redis lock：

```text
chat-turn-lock:{user_id}:{session_id}
```

策略：

```text
短TTL
finally release
第二个并发Turn → 409 TURN_IN_PROGRESS
```

Chat POST 不做自动网络重放；若客户端不确定是否成功，先 GET history 判断。

---

# 12. Redis LangGraph Checkpointer

生产：

```text
Redis 8+
AsyncRedisSaver
```

```text
thread_id = f"{user_id}:{session_id}"
```

配置 TTL，并在读取时 refresh。

Session DELETE：

```text
adelete_thread(thread_id)
```

`InMemorySaver` 只允许 unit tests / isolated dev。

---

# 13. 五节点 Graph

```text
intent_parse
slot_check
tool_dispatch
response_gen
hallucination_guard
```

普通补槽不使用 LangGraph `interrupt()`：

```text
WAITING_SLOT
→ response_gen提问
→ END
→ 下一条用户消息作为新的Graph input从START进入
```

这样才能识别用户是在回答槽位，还是突然切换新任务。

---

# 13.1 Foundation 核心共享 Schema

以下类型是本项目 Runtime Contract 的正式最小定义；不得只写类型名让开发者自行猜字段。实现时可以增加内部非序列化字段，但不能改变这里的业务语义。

```python
from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field

class SessionUserContext(BaseModel):
    measurement_overrides: dict[str, float] = Field(default_factory=dict)
    confirmed_measurement_fields: set[str] = Field(default_factory=set)

class ConfirmationKind(str, Enum):
    EXECUTE_RETURN = "execute_return"
    EXECUTE_EXCHANGE = "execute_exchange"
    CONFIRM_STORED_MEASUREMENTS = "confirm_stored_measurements"
    SAVE_MEASUREMENTS = "save_measurements"

class PendingConfirmation(BaseModel):
    kind: ConfirmationKind
    payload: dict[str, Any] = Field(default_factory=dict)
    created_turn_id: str

class EvidenceItem(BaseModel):
    source_type: Literal["commerce_api", "rag", "memory", "derived"]
    source_name: str
    reference_id: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

class ToolResult(BaseModel):
    tool_name: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    error: ToolError | None = None
    side_effect: bool = False

class ToolExecutionContext(BaseModel):
    runtime: AgentRuntimeContext = Field(exclude=True)
    intent: "BusinessIntent"
    task_id: str | None = None
    action_mode: "ActionMode | None" = None

class ToolSpec(BaseModel):
    name: str
    allowed_intents: tuple["BusinessIntent", ...]
    side_effect: bool
    timeout_seconds: float
    retry_policy: Literal["none", "read_once_retry", "write_same_idempotency_key"]
    args_model: type[BaseModel]
    result_model: type[BaseModel]
```

固定约束：

```text
PendingConfirmation 只进入 TaskFrame.pending_confirmation
SessionUserContext 只保存 Session 级 measurement override/confirmed-field 状态
ToolExecutionContext.runtime 不持久化、不进入 LLM
ToolResult 不允许携带 access_token/service_token/user_id 注入参数
EvidenceItem 只承载可用于 grounding 的已校验事实和来源
```

---

# 14. AgentState：单一真值

## 14.1 Persistent

```python
class AgentState(TypedDict, total=False):
    active_task: TaskFrame | None
    paused_tasks: list[TaskFrame]
    session_user_context: SessionUserContext
    conversation_focus: FocusRef | None
    pending_intent_selection: PendingIntentSelection | None
    # transient字段也在同一TypedDict中，但每Turn重置
```

只保留一个全局指代对象：

```python
class FocusRef(BaseModel):
    entity_type: Literal["product", "order"]
    entity_id: str
```

不要同时维护：

```text
AgentState.focused_object
TaskFrame.focused_object
```

Task 业务对象放 `TaskFrame.slots`。

## 14.2 Transient

```text
current_message
turn_id
intent_result
entities
tool_result
response_draft
task_transition
completed_task_snapshot
resumed_task_snapshot
resumed_this_turn
guard_retry_count
fallback_used
```

`TurnInitializer` 每次新 Turn 重置 transient 字段。

---

# 15. Task 模型

```python
class TaskStatus(str, Enum):
    ACTIVE = "active"
    WAITING_SLOT = "waiting_slot"
    WAITING_CONFIRMATION = "waiting_confirmation"
    READY = "ready"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"
```

```python
class TaskFrame(BaseModel):
    task_id: str
    intent: BusinessIntent
    status: TaskStatus
    slots: dict[str, Any]
    missing_slots: list[str]
    action_mode: ActionMode | None
    side_effect: bool
    execute_confirmed: bool
    pending_confirmation: PendingConfirmation | None
    paused_from_status: TaskStatus | None
    pause_reason: str | None
    created_turn_id: str
    last_turn_id: str
```

`pending_confirmation` **只存在 TaskFrame 中**。

---

# 16. Task Stack

`TaskContextManager` 纯确定性：

```text
start
continue_current
pause_and_switch
resume
cancel
complete
complete_and_resume
find_paused
```

Pause：

```text
paused_from_status = old.status
status=PAUSED
paused_tasks.append(old)
active_task=new
```

Resume：

```text
LIFO pop
恢复paused_from_status
resumed_this_turn=true
```

若恢复的是尚未真正提交的副作用 READY Task：

```text
execute_confirmed=false
→ WAITING_CONFIRMATION
```

完成新任务并恢复旧任务的同一 Turn 不再继续执行旧 Tool，只提示旧任务下一步。

`MAX_PAUSED_TASKS=3`，超过时澄清用户先完成/取消现有任务。

---

# 17. TaskCancelResolver

不是第 10 个 Intent。

当前有 active task 时优先识别：

```text
算了
不办了
先不退了
先不换了
不用催了
```

→ active task `CANCELED`。

如果 paused stack 非空：恢复上一任务。

---

# 18. 9 个 Intent

```python
class BusinessIntent(str, Enum):
    PRODUCT_QUERY = "product_query"
    SIZE_RECOMMEND = "size_recommend"
    URGE_ORDER_PAYMENT = "urge_order_payment"
    PROMOTION_QUERY = "promotion_query"
    LOGISTICS_QUERY = "logistics_query"
    RETURN = "return"
    EXCHANGE = "exchange"
    CHITCHAT = "chitchat"
    URGE_SHIPPING = "urge_shipping"
```

做法 B：

```text
recognized=true + intent=<enum>
或
recognized=false + intent=null
```

---

# 19. ActionMode

保持简单：

```python
class ActionMode(str, Enum):
    INFORMATIONAL = "informational"
    ACTION_REQUEST = "action_request"
```

否定/假设最终归入 INFORMATIONAL 或 Cancel Cue，不创建更多 ActionMode enum。

Hard negatives：

```text
“我不是要退，只是问问怎么退” → return + INFORMATIONAL
“如果以后要换货怎么办”        → exchange + INFORMATIONAL
“先别催发货”                    → cancel/INFORMATIONAL，write=0
“如果还没发就帮我催”            → urge_shipping + ACTION_REQUEST + condition
```

---

# 20. Intent Pipeline

```text
Normalize
↓
TaskCancel / PendingConfirmation / PendingIntentSelection 优先解析
↓
Deterministic high-precision rules
↓
Structured LLM classifier
↓
Entity supplement
↓
IntentDecision
```

输出：

```python
class IntentDecision(str, Enum):
    ACCEPT = "accept"
    CLARIFY = "clarify"
    OUT_OF_SCOPE = "out_of_scope"
    CLASSIFIER_FAILURE = "classifier_failure"
```

保留 `confidence / second_confidence / margin` 作为 classifier signal 和评测数据，但不把它描述成校准概率。最终语义必须唯一，低置信度不能同时映射两个 Decision enum。

```python
class IntentFallbackReason(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    OUT_OF_SCOPE = "out_of_scope"
    CLASSIFIER_FAILURE = "classifier_failure"
    MULTIPLE_INTENTS = "multiple_intents"
```

固定映射：

```text
ACCEPT
→ 可靠识别到一个 BusinessIntent
→ recognized=true, intent=<enum>

CLARIFY
→ 仍有业务候选，但 confidence/margin 不足以执行
→ recognized=false, intent=null
→ fallback_reason=LOW_CONFIDENCE
→ 可以携带 candidate_intents 供下一 Turn 澄清

OUT_OF_SCOPE
→ classifier 明确判断用户请求不属于 9 个 BusinessIntent 的业务范围
→ recognized=false, intent=null
→ fallback_reason=OUT_OF_SCOPE

CLASSIFIER_FAILURE
→ LLM/API 调用失败、超时，或 structured output/schema parse 真正失败
→ recognized=false, intent=null
→ fallback_reason=CLASSIFIER_FAILURE
```

可配置阈值只提供 DecisionEngine 信号：

```text
>=0.75 且 margin>=0.15 → 可进入 ACCEPT 候选
0.55~0.75 或 margin太小 → CLARIFY
<0.55 且仍有 plausible business candidate → CLARIFY / LOW_CONFIDENCE
<0.55 且无可靠业务候选 → recognized=false, intent=null, decision=CLARIFY, fallback_reason=LOW_CONFIDENCE
```

`OUT_OF_SCOPE` 和 `CLASSIFIER_FAILURE` 只能由各自明确语义触发，禁止用 `<0.55` 直接代替。阈值只能由 Golden Dataset 调整，不使用未经验证的历史指标。

---

# 21. MULTIPLE_INTENTS

```python
class PendingIntentSelection(BaseModel):
    candidate_intents: list[BusinessIntent]
    original_turn_id: str
```

产生多个独立目标：

```text
recognized=false
intent=null
reason=MULTIPLE_INTENTS
→ 保存PendingIntentSelection
```

下一 Turn 选择成功/明确开启其他任务/取消：清空。

一个目标的 prerequisite 不算多 Intent，例如：

```text
“查一下，如果没发就帮我催”
→ urge_shipping + ACTION_REQUEST
```

---

# 22. IntentPolicy 与 IntentFlowRegistry 接口

IntentPolicy 只描述“允许什么”：

```python
class IntentPolicy(BaseModel):
    intent: BusinessIntent
    allowed_tools: tuple[str, ...]
    can_write: bool
    requires_action_request: bool
    requires_execute_confirmation: bool
```

最终唯一 Policy Matrix：

| BusinessIntent | allowed_tools | can_write | requires_action_request | requires_execute_confirmation |
|---|---|---:|---:|---:|
| `product_query` | `product_search_tool`, `selling_point_tool` | false | false | false |
| `size_recommend` | `size_recommend_tool` | false | false | false |
| `urge_order_payment` | 无业务 Tool | false | false | false |
| `promotion_query` | `promotion_query_tool` | false | false | false |
| `logistics_query` | `logistics_query_tool` | false | false | false |
| `return` | `return_request_tool` | true | true | true |
| `exchange` | `exchange_request_tool` | true | true | true |
| `chitchat` | 无业务 Tool | false | false | false |
| `urge_shipping` | `urge_shipping_tool` | true | true | false |

说明：

```text
return/exchange 的 INFORMATIONAL 对话不会执行 write；真正执行必须 ACTION_REQUEST + final confirmation。
urge_shipping 的 write 必须 ACTION_REQUEST，但不增加第二次 execute confirmation。
PATCH /api/v1/users/me/measurements 是 UserContextWriteService 的受控 post-action，不是 LLM Tool，因此不进入 allowed_tools。
```

Flow 接口：

```python
class FlowResult(BaseModel):
    ready_for_response: bool
    tool_result: ToolResult | None
    dialogue_reason: str | None
    objects: list[dict[str, Any]]

class IntentFlow(Protocol):
    async def execute(...) -> FlowResult:
        ...

class IntentFlowRegistry:
    def register(self, intent: BusinessIntent, flow: IntentFlow) -> None:
        ...
    def get(self, intent: BusinessIntent) -> IntentFlow:
        ...
```

最终 Registry 必须恰好覆盖 9 个 BusinessIntent，且全项目只能有一个 `customer_service/flows/registry.py` 主 Registry：

```text
PRODUCT_QUERY      → ProductQueryFlow
SIZE_RECOMMEND     → SizeRecommendFlow
URGE_ORDER_PAYMENT → UrgeOrderPaymentFlow
PROMOTION_QUERY    → PromotionQueryFlow
LOGISTICS_QUERY    → LogisticsQueryFlow
RETURN             → ReturnFlow
EXCHANGE           → ExchangeFlow
CHITCHAT           → ChitchatFlow
URGE_SHIPPING      → ShippingFlow
```

本文施工范围只建立 Registry/Policy/Runtime 基础设施与 Foundation 可验证闭环；不得为尚未施工的业务能力伪造 Commerce 结果。最终项目完成时必须满足上述 9/9 Registry 覆盖。

---

# 23. ToolRuntime 骨架

本 Slice 只建立统一入口：

```text
ToolRegistry
ToolSpec
ToolExecutionContext
ToolResult
ToolError
EvidenceItem
ToolRuntime.execute()
```

必须支持接口：

```text
Intent allowlist
Pydantic args/result validation
ActionGuard hook
deadline
timeout
concurrency semaphore
retry hook
output guard hook
tracing hook
```

不实现复杂 Circuit Breaker。

---

# 24. Chat API

```text
POST   /api/v1/chat/sessions
POST   /api/v1/chat/sessions/{session_id}/messages
POST   /api/v1/chat/sessions/{session_id}/messages:stream
GET    /api/v1/chat/sessions/{session_id}/messages
DELETE /api/v1/chat/sessions/{session_id}
```

本文至少要实现同步消息接口完整闭环，并冻结 SSE wire contract。任何公开 SSE 的业务 `delta` 都必须遵守“完整 draft → grounding PASS → 切分 delta”的 Guarded Streaming 语义；Foundation 阶段如果暂不开放业务流式输出，可以只发送 `status` + 最终 `done`，但禁止发送未经 grounding 的业务文本。

---

# 25. Request-ID

8000 / 8001 都：

```text
读取 X-Request-ID
缺失则生成 UUID
response回写
```

8000→8001 继续转发。

---

# 26. EcommerceClient 基础

8000 访问 8001 的唯一 HTTP Adapter：

```python
class EcommerceClient:
    # auth-independent/public catalog
    async def list_products(...): ...
    async def get_product(...): ...
    async def get_product_skus(...): ...
    async def get_size_chart(...): ...

    # user scoped
    async def get_profile(...): ...
    async def get_preferences(...): ...
    async def get_measurements(...): ...
    async def patch_measurements(...): ...
    async def get_order(...): ...
    async def get_logistics(...): ...
    async def get_promotions(...): ...

    # internal service scoped
    async def batch_get_products(...): ...
    async def filter_skus(...): ...
    async def get_knowledge_card(...): ...

    # write
    async def create_return(...): ...
    async def create_exchange(...): ...
    async def create_shipping_urge(...): ...
```

Credential 自动由 method 选择：

```text
public → no auth
user scoped → current user Bearer
internal → Service Token
```

Tool 不自行拼 URL。

---

# 27. Prompt 基础

最小目录：

```text
customer_service/prompts/
├── _shared/
├── intent/classify.jinja2
├── entity/supplement.jinja2
├── clarification/missing_slots.jinja2
├── response/chitchat.jinja2
├── loader.py
├── registry.py
└── schemas.py
```

PromptRegistry 返回：

```text
name
version
template_hash
rendered
```

后续 Slice 按业务增加薄模板。

---

# 28. Langfuse Foundation

从 Foundation 就初始化统一：

```text
TracingService
LangfuseTracingService
NoopTracingService
ObservabilityRedactor
```

全进程一个 Langfuse client。

此 Slice 至少产生：

```text
agent.turn
intent.parse
task.transition
slot.check
```

Langfuse down → fail-open。

---

# 29. Readiness

Critical：

```text
Agent MySQL
Redis Checkpointer
LLM
Commerce 8001
```

Degradable：

```text
Qdrant
Elasticsearch
TEI
Langfuse
```

后者故障不因自身原因使核心 Chat readiness 直接失败，但 health details 要报告 degraded。

---

# 30. 精确文件改造

## Commerce

```text
app/core/config.py
app/core/security.py
app/core/request_id.py
app/core/errors.py
app/database.py
app/dependencies.py
app/api/public/auth.py
app/api/public/user.py
app/models/user.py
app/models/auth_session.py
app/models/idempotency.py
app/repositories/user.py
app/repositories/auth_session.py
app/services/auth.py
app/services/user.py
app/schemas/auth.py
app/schemas/users.py
```

## Agent

```text
customer_service/config/config.py
customer_service/api/app.py
customer_service/api/dependencies.py
customer_service/api/router/chat_router.py
customer_service/api/schema.py
customer_service/clients/ecommerce.py
customer_service/graph/state.py
customer_service/graph/builder.py
customer_service/graph/routing.py
customer_service/graph/nodes/*
customer_service/tools/base.py
customer_service/tools/registry.py
```

### Legacy migration / delete map

当前旧文件如果存在：

```text
customer_service/tools/builder.py
```

必须把其中“Tool 构建/查找/执行编排”职责迁移到唯一正式实现：

```text
customer_service/tools/registry.py  → ToolSpec/注册
customer_service/tools/runtime.py   → allowlist/validation/timeout/retry/guard/trace 执行
customer_service/tools/models.py    → ToolResult/ToolError/EvidenceItem
customer_service/tools/context.py   → ToolExecutionContext
```

迁移完成后执行：

```bash
rg "tools\.builder|from customer_service.tools.builder|import customer_service.tools.builder" customer_service tests
```

必须为 0 个有效 import/call site；随后删除旧 `customer_service/tools/builder.py`。禁止同时保留旧 builder 与新 ToolRuntime 两套主执行链。

新增：

```text
alembic.ini
alembic/env.py
alembic/versions/0001_chat_runtime.py

customer_service/context/principal.py
customer_service/context/runtime.py
customer_service/tasking/models.py
customer_service/tasking/manager.py
customer_service/tasking/confirmation.py
customer_service/tasking/turn_initializer.py
customer_service/tasking/cancel_resolver.py
customer_service/intents/models.py
customer_service/intents/classifier.py
customer_service/intents/policies.py
customer_service/intents/decision.py
customer_service/intents/selection.py
customer_service/flows/base.py
customer_service/flows/registry.py
customer_service/tools/runtime.py
customer_service/tools/models.py
customer_service/tools/context.py
customer_service/chat/models.py
customer_service/chat/repository.py
customer_service/chat/service.py
customer_service/observability/tracing.py
customer_service/observability/langfuse_tracing.py
customer_service/observability/redaction.py
```

统一使用 `customer_service/service/`（单数）放 application service，不再新增平行 `services/` 目录。

---

# 31. Slice 测试

## Unit

```text
JWT claims
TurnInitializer
Task pause/resume/cancel
PendingConfirmation
PendingIntentSelection
IntentPolicy
ActionMode hard negatives
ToolRuntime args/result validation
```

## Integration

真实 MySQL + Redis：

```text
Alembic upgrade
chat session ownership
same thread checkpoint persistence
restart recovery
session delete → checkpoint delete
turn lock
```

## Slice E2E

```text
8001 login
→ Access JWT
→ 8000 create session
→ 用户“你好”
→ chitchat
→ response
→ chat history持久化
```

Cross-user：

```text
USER_B不能读/写/删除USER_A session
```

---

# 32. Completion Gate

必须全部满足：

```text
RS256 + Refresh完整
Agent本地验签
Chat Session真实持久化
Session ownership隔离
Redis checkpoint生产可用
五节点唯一主控
Persistent/Transient明确
Task pause/resume/cancel工作
MULTIPLE_INTENTS有PendingIntentSelection
TurnInitializer防旧Turn污染
9 Intent enum统一
ToolRuntime统一入口存在
EcommerceClient是唯一8001 Adapter
Langfuse基础可用且fail-open
Foundation E2E通过
```

本文 Completion Gate 全部通过即表示 Foundation 施工完成；未在本文范围内实现的业务能力仍必须保持显式未完成状态，不能用 Mock/Stub 结果冒充生产能力。
