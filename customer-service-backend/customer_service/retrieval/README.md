# RAG 基础模块

商品检索的核心 RAG 模块实现（不包括 Flow 层）。

## 架构概览

```
Query → ContextResolver → QueryPlanner → [RAG Pipeline] → RetrievalResult
         ↓                  ↓                ↓
    QueryContext      direct/rag/clarify   Fusion
                                            ↓
                                        RetrievalGuard
```

## 核心组件

### 1. 数据模型 (`models.py`)

#### `QueryContext`
查询上下文，包含：
- `original_query`: 原始用户查询
- `semantic_query`: 语义查询部分（移除硬约束后）
- `hard_filters`: 硬约束（brand, color, size, price）
- `soft_signals`: 软信号（用户偏好等）
- `focused_product_id`: 当前聚焦的商品
- `conversation_products`: 对话中提到的商品列表

#### `ProductChunk`
商品文本块：
- `chunk_id`: 格式 `{product_id}:{chunk_type}:{ordinal}`
- `chunk_type`: overview, selling_points, material, size

#### `RetrievalResult`
检索结果：
- `product_ids`: 商品 ID 列表（按分数排序）
- `scores`: 融合后的分数
- `matched_reasons`: 匹配原因
- `mode`: 检索模式（qdrant+es, qdrant_only, es_only, commerce_only_degraded）
- `evidence`: 证据链（可观测性）

### 2. 上下文解析 (`context_resolver.py`)

`ContextResolver` 负责解析用户查询的上下文：

**优先级**：
1. 消息中明确的 product_id（#12345, SKU12345）
2. `focused_object` 中的商品
3. `short_memory.candidate_products` 中的唯一商品

**关键方法**：
- `resolve()`: 解析查询上下文
- `extract_product_id_from_text()`: 提取明确的 product_id
- `extract_hard_filters()`: 提取硬约束（价格、尺码等）
- `build_semantic_query()`: 构造语义查询（移除硬约束词汇）
- `get_focused_product()`: 从 state 获取聚焦商品

### 3. 查询规划 (`query_planner.py`)

`QueryPlanner` 决定检索策略：

**路径类型**：
- `direct`: 有明确 product_id，直接走 Commerce API
- `rag`: Discovery query，需要走 RAG 检索
- `clarify`: 指代不明确，需要澄清

**辅助方法**：
- `should_use_semantic_search()`: 判断是否需要向量检索
- `should_use_lexical_search()`: 判断是否需要词法检索（ES）
- `get_retrieval_limit()`: 获取检索数量限制

### 4. 融合算法 (`fusion.py`)

#### RRF (Reciprocal Rank Fusion)
```python
score(d) = sum(1 / (k + rank(d))) for all occurrences
```

**函数**：
- `reciprocal_rank_fusion()`: 融合多个检索结果
- `aggregate_chunks_to_products()`: 将 chunk 级别结果聚合到 product
- `merge_scores_with_reasons()`: 合并匹配原因
- `apply_boost_factors()`: 应用加权因子

### 5. 安全防护 (`guard.py`)

`RetrievalGuard` 防止注入攻击：

**检测模式**：
- 注入模式：忽略规则、执行命令、系统提示等
- 敏感信息：银行卡号、身份证号、邮箱

**方法**：
- `sanitize_chunk_text()`: 清理检索内容中的注入
- `sanitize_query()`: 清理用户查询
- `validate_retrieval_results()`: 验证检索结果安全性

### 6. Embedding 客户端 (`infrastructure/embedding.py`)

`EmbeddingClient` 连接 TEI 服务：

**API 格式**：
- POST `/embed`: `{"inputs": str}` → `[[float, ...]]`
- POST `/embed`: `{"inputs": [str, ...]}` → `[[float, ...], ...]`

**方法**：
- `embed()`: 单条文本 embedding
- `embed_batch()`: 批量文本 embedding
- `health_check()`: 健康检查

## 使用示例

```python
from customer_service.retrieval import (
    ContextResolver,
    QueryPlanner,
    QueryContext,
    reciprocal_rank_fusion,
)

# 1. 解析上下文
resolver = ContextResolver()
context = await resolver.resolve("推荐一件红色T恤", state)

# 2. 规划查询路径
planner = QueryPlanner()
plan = planner.plan(context)  # "rag"

# 3. 融合检索结果
qdrant_results = [("p1", 0.9), ("p2", 0.8)]
es_results = [("p2", 0.95), ("p3", 0.7)]
fused = reciprocal_rank_fusion([qdrant_results, es_results])
```

## 依赖的外部服务

1. **TEI (Text Embeddings Inference)**
   - 地址: `http://localhost:8080`
   - 用途: 文本向量化

2. **Qdrant**
   - 用途: 向量检索（由 `service.py` 中的 `QdrantProductRetriever` 调用）

3. **Elasticsearch**
   - 用途: 词法检索（由 `service.py` 中的 `ElasticsearchProductRetriever` 调用）

## 未实现部分

- Flow 层（另一个任务）
- Qdrant/ES 具体检索器已在 `service.py` 中实现
- Redis 速率限制（`guard.py` 中预留接口）
