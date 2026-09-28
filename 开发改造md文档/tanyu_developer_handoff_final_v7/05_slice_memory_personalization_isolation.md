# Vertical Slice 05：Memory、用户上下文、个性化与用户隔离

> 文档版本：v7.0 — Developer Handoff Final  
> 日期：2026-09-22  
> 实施顺序：核心业务 Slice 之后  
> 涉及工程：主要 `customer-service-backend:8000`，通过 `EcommerceClient` 读取 8001 用户结构化资料  
> 本文独立、自包含。目标是实现真正有价值的跨会话个性化，同时保持用户信息管理简单、可控、不可串用户。

---

# 1. 不建设通用用户权限平台

本项目只有：

```text
一个登录用户
一个Commerce Service
一个Agent Service
```

因此明确不做：

```text
RBAC/ABAC平台
多租户Tenant模型
organization/workspace权限体系
User Context Plugin Framework
第二套Identity系统
用户资料Redis缓存层
```

需要的是清晰的作用域，而不是复杂的权限产品。

---

# 2. 四层上下文

```text
A. AuthPrincipal
   → 当前用户身份

B. LangGraph checkpoint
   → 当前Session任务/槽位/focus/measurements override

C. Commerce structured context
   → Profile / Preferences / Measurements

D. Agent semantic memory
   → Agent MySQL canonical
   → Qdrant candidate index
```

---

# 3. 身份唯一来源

```text
JWT.sub
```

LLM、请求 body、Tool args、Memory query 都不能覆盖 principal.user_id。

所有 repo/service 方法使用 AuthPrincipal 或显式 authenticated user_id，不接受模型决定的 user_id。

---

# 3.1 SessionUserContext 固定 Schema

本文使用的 Session 级身体数据上下文固定为：

```python
class SessionUserContext(BaseModel):
    measurement_overrides: dict[str, float] = Field(default_factory=dict)
    confirmed_measurement_fields: set[str] = Field(default_factory=set)
```

它只表示当前会话的临时覆盖值和“本 Session 已确认仍适用”的 Commerce measurement 字段；它不是长期 semantic memory，也不是 Commerce `user_measurements` 的复制表。

---

# 4. Runtime Context 与 LLM-visible Context 分离

Runtime-only：

```python
class UserContextBundle(BaseModel):
    commerce: CommerceUserContext
    session: SessionUserContext
    semantic_memories: list[MemoryFact]
```

给程序/Tool 使用。

然后：

```python
class PromptUserContext(BaseModel):
    display_name: str | None
    relevant_preferences: list[str]
    relevant_measurements: dict[str, float]
    relevant_memories: list[str]
```

由：

```text
PromptContextBuilder
```

按 Intent 生成最小 LLM 视图。

不要把完整 UserContextBundle JSON 塞进 Prompt。

---

# 5. CommerceUserContext

```python
class CommerceUserContext(BaseModel):
    profile: UserProfile | None
    preferences: list[UserPreference]
    measurements: UserMeasurements | None
```

Agent 权限：

```text
Profile       read-only
Preferences   read-only
Measurements  explicit-confirmed PATCH only
```

---

# 6. UserContextService：按需加载

```python
class UserContextService:
    async def load(..., needs: UserContextNeeds) -> UserContextBundle:
        ...
```

不要每个 Turn 无脑加载全部资料。

建议：

```text
product_query / urge_order_payment
→ preferences + relevant semantic memory

size_recommend
→ measurements

logistics / return / exchange / urge_shipping
→ 默认不需要profile/preferences/measurements

chitchat
→ 通常不加载，除非上下文明确需要
```

必要项可 `asyncio.gather`。

---

# 7. Personalization：硬约束与软偏好

当前 Turn 用户明确说：

```text
“只要黑色”
“预算400以内”
```

→ hard filter。

Commerce Preferences / Semantic Memory：

```text
“喜欢黑色”
“偏好宽松版”
```

→ soft ranking / copy personalization。

除非用户本 Turn 明确要求，否则不能把长期偏好强制变成 hard filter。

这样避免用户只因为“历史喜欢黑色”就永远看不到其他优质候选。

---

# 8. Measurements 特殊规则

精确 Measurements：

```text
Current Message
> Session Override
> Commerce Measurements（对应字段已确认）
```

Semantic Memory 对精确数值不参与尺码计算。

Memory extractor 即使看到：

```text
“我现在57kg”
```

也不能把它作为长期 semantic measurement truth 写入 Qdrant 并供 Size 计算。

长期保存只通过 Commerce PATCH。

---

# 9. Agent Semantic Memory 的范围

适合保存：

```text
偏好宽松
喜欢黑色/藏青
主要用于通勤
通常预算300~500
不喜欢亮色
```

不保存：

```text
Access/Refresh/Service Token
password/OTP/card
当前订单状态
当前库存/价格
refund amount
精确measurements作为尺码真值
系统Prompt/Tool指令
```

---

# 10. Agent DB Migration

Alembic：

```text
0003_user_memory.py
```

## `user_memory_facts`

```text
memory_id PK
user_id NOT NULL
memory_type NOT NULL
memory_key NULL
memory_text TEXT NOT NULL
normalized_value JSON/TEXT NULL
status active/superseded/deleted
importance FLOAT
confidence FLOAT
source_session_id NULL
source_message_id NULL
supersedes_memory_id NULL
vector_sync_status pending/synced/failed
created_at
updated_at

INDEX(user_id,status)
INDEX(user_id,memory_type)
```

## `memory_events`

为了保持实现简单，只做轻量审计/同步记录：

```text
event_id PK
user_id
memory_id NULL
event_type
metadata_json
created_at
```

事件仅：

```text
NEW
DUPLICATE
SUPERSEDE
VECTOR_SYNC_FAILED
VECTOR_SYNCED
```

不建设复杂 Event Sourcing；如果开发中确认无使用价值，可以在 coordinated change 中删除，但当前 Contract 保留它用于调试和向量同步审计。

---

# 11. Memory 只保留三个核心 Service

```text
UserContextService
MemoryRecallService
MemoryWriteService
```

辅助 repository / indexer 是内部实现，不引入通用 provider/plugin 框架。

---

# 12. MemoryRecallService

流程：

```text
当前user_id
+ 当前query/intent
↓
TEI BGE-M3 embed canonical query
↓
Qdrant user_memory
  filter user_id=current_user
  filter status=active
↓
memory_id candidates
↓
Agent MySQL hydrate:
WHERE memory_id=?
AND user_id=?
AND status='active'
↓
relevance/importance budget
↓
top 3~5
```

Qdrant 不是真值。

---

# 13. Qdrant `user_memory`

和 Product RAG 共用 TEI/BGE-M3 dense，但独立 collection：

```text
user_memory
```

Embedding input：

```text
canonical memory_text
```

不 embedding：

```text
整段聊天JSON
Token
完整metadata dump
```

Payload：

```text
memory_id
user_id
memory_type
memory_key
status
importance
confidence
```

Collection dimension 从 TEI 实测，不硬编码猜测。

---

# 14. Memory Write 不每个 Turn 都调用 LLM

在 LLM extraction 前增加轻量：

```text
MemoryCandidateGate
```

高价值触发：

```text
“以后...”
“我喜欢...”
“我不喜欢...”
“平时...”
“预算通常...”
“给我推荐...类型的”
```

优先运行场景：

```text
product_query
urge_order_payment
明确偏好型chitchat
```

通常跳过：

```text
查物流
退货槽位
订单号
确认“可以”
```

减少无意义 LLM 调用。

---

# 15. MemoryWriteService

```text
candidate gate
↓
structured LLM fact extraction
↓
whitelist
↓
secret/PII/instruction filter
↓
normalize
↓
lookup related existing memories
↓
MemoryDecision
↓
MySQL transaction
↓
Qdrant upsert
↓
memory event
```

LLM 不直接操作 DB。

---

# 16. MemoryDecision

```python
class MemoryDecision(str, Enum):
    NEW = "new"
    DUPLICATE = "duplicate"
    SUPERSEDE = "supersede"
    SKIP = "skip"
```

优先 deterministic：

```text
同key+同normalized value → DUPLICATE
同key+用户明确新偏好   → SUPERSEDE
低置信/敏感/推断       → SKIP
```

复杂自然语言冲突再用 LLM judge。

---

# 17. SUPERSEDE 与 stale vector

MySQL：

```text
old.status=superseded
new.status=active
```

如果 Qdrant 删除/更新失败：

```text
vector_sync_status=failed
```

后续 Qdrant 仍命中 old memory：

```text
MySQL hydrate
→ status=superseded
→ drop
```

因此不需要分布式事务。

---

# 18. Rebuild

```text
scripts/rebuild_user_memory_index.py
```

支持：

```text
--user-id
--all
--dry-run
```

只从 Agent MySQL `active` memories 重建 Qdrant。

---

# 19. User Isolation：四个硬边界

## 19.1 Session

```text
chat_sessions WHERE session_id AND user_id
```

## 19.2 Commerce

User Bearer，8001 再校验 order/user ownership。

## 19.3 Agent MySQL Memory

所有 get/list/update/delete 都带 current user_id。

不要设计：

```python
get(memory_id)
```

应该：

```python
get_owned(memory_id, principal)
```

## 19.4 Qdrant

必须 user filter；即使测试故意让 Qdrant 返回别人的 memory_id，MySQL hydrate 仍应 drop。

---

# 20. Prompt Minimal Context

Product Query：

```text
相关soft preferences
相关semantic memories
```

Size：

```text
必要measurements
```

Logistics / Return / Exchange：

```text
默认不带购物偏好/身体数据
```

这既降低隐私暴露，也减少 Prompt token。

---

# 21. UserContext 与催拍催付

UrgeOrderPaymentFlow 的最终个性化上下文固定为：

```text
当前商品
当前用户需求
selling points
promotion
Commerce explicit preferences
relevant semantic memories
```

其中 Preferences/Memory 是 soft personalization，不是硬事实。

---

# 22. 具体文件

```text
alembic/versions/0003_user_memory.py

customer_service/context/user_context.py
customer_service/service/user_context_service.py
customer_service/service/user_context_write_service.py
customer_service/memory/models.py
customer_service/memory/repository.py
customer_service/memory/candidate_gate.py
customer_service/memory/recall.py
customer_service/memory/write.py
customer_service/memory/policy.py
customer_service/memory/index.py
customer_service/memory/prompt_context.py
customer_service/memory/rebuild.py
scripts/rebuild_user_memory_index.py

customer_service/prompts/memory/extract_facts.jinja2
customer_service/prompts/memory/resolve_conflict.jinja2
```

### Legacy memory migration / delete map

当前源码如果存在以下旧实现：

```text
customer_service/memory/manager.py
customer_service/memory/long_term.py
customer_service/memory/short_term.py
customer_service/memory/semantic_memory.py
customer_service/memory/write_service.py
```

必须按职责迁移：

```text
manager.py
→ service/user_context_service.py + memory/recall.py + memory/write.py + memory/policy.py

long_term.py
→ memory/repository.py + memory/write.py + memory/index.py

short_term.py
→ LangGraph Redis checkpoint + TaskFrame + SessionUserContext
→ 不再维护第二套 short-term memory canonical state

semantic_memory.py
→ memory/recall.py + memory/index.py + memory/prompt_context.py

write_service.py
→ semantic fact 写入使用 memory/write.py
→ 结构化 Measurements 显式保存使用 service/user_context_write_service.py
```

迁移完成后执行：

```bash
rg "memory\.(manager|long_term|short_term|semantic_memory|write_service)" customer_service tests
```

必须不存在指向旧主实现的有效 import/call site，然后删除旧文件。禁止 `MemoryManager + 新 Service` 双写，也禁止 Redis short-term state 与 LangGraph checkpoint 形成两套会话真值。

---

# 23. Langfuse / Privacy

Memory trace 记录：

```text
memory.recall
memory.write
memory.vector_sync
```

默认只记录：

```text
hit_count
returned_count
NEW/DUPLICATE/SUPERSEDE/SKIP
sync status
latency
```

不默认上传完整 memory_text。

---

# 24. Slice 测试

## User Context

```text
按Intent懒加载
Product不会加载Measurements
Logistics不会加载Preferences
Size只加载必要结构化数据
```

## Memory

```text
NEW/DUPLICATE/SUPERSEDE/SKIP
candidate gate跳过无价值Turn
Qdrant user filter
MySQL hydrate二次隔离
stale superseded vector
vector sync failure
rebuild
```

## Measurements Boundary

```text
Exact measurements不写semantic memory真值
Profile/Preferences不自动写Commerce
```

## Cross-user

```text
USER_B不能读A session
不能读A memory
不能通过Qdrant拿A memory
不能通过Tool args伪造user_id
不能用A token查B order
```

---

# 25. Completion Gate

```text
AuthPrincipal是唯一身份来源
UserContextBundle和PromptUserContext分离
按Intent懒加载
Preferences/Memory默认soft personalization
Memory不每Turn调用LLM
Agent MySQL是semantic memory canonical truth
Qdrant只作候选索引
MySQL二次revalidate
精确Measurements不进入semantic size truth
四层用户隔离全部测试通过
cross-user leak = 0
```
