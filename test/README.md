# 测试文件说明

本目录包含使用**真实完整数据**的端到端测试，所有测试均基于 Docker 部署的真实服务。

## 目录结构

```
test/
├── e2e/                          # 端到端集成测试
│   ├── test_slice02_e2e_full.py  # Slice02 完整功能测试（7个场景）
│   └── test_full_index_build.py  # 离线 RAG 索引构建测试（83个商品）
├── utils/                        # 测试工具
│   ├── check_services.py         # 检查 Docker 服务状态
│   └── check_bge_m3_dimension.py # 验证 BGE-M3 Embedding 模型
└── conftest.py                   # pytest 配置
```

## E2E 测试

### 1. Slice02 完整端到端测试 (`test_slice02_e2e_full.py`)

**测试场景：**
1. ✅ 商品咨询（Product Query with RAG）
2. ✅ Discovery 查询（模糊需求）
3. ✅ Exact 查询（精确商品ID）
4. ✅ 促销查询（Promotion Query）
5. ✅ 催拍催付（Urge Order Payment）
6. ✅ 基础闲聊（Chitchat）
7. ✅ 多轮对话上下文

**依赖服务：**
- MySQL (43306) - 用户认证、商品数据
- Redis (6379) - 会话管理
- Commerce Backend (8001) - 商品/促销 API
- Customer Service Backend (8000) - AI Agent API
- Qdrant (6333) - 向量检索
- Elasticsearch (9200) - 全文检索

**运行命令：**
```bash
python test/e2e/test_slice02_e2e_full.py
```

**测试用户：**
- 用户名：`li_ming88`
- 密码：`password123`

### 2. 离线索引构建测试 (`test_full_index_build.py`)

**功能：**
- 从 MySQL 获取全部 83 个商品
- 调用 Commerce API 获取 Knowledge Card
- 使用 BGE-M3 模型（1024维）生成 Embedding
- 写入 Qdrant 向量数据库
- 写入 Elasticsearch 全文索引

**依赖服务：**
- MySQL (43306)
- Commerce Backend (8001)
- Embedding Service (8100) - BGE-M3
- Qdrant (6333)
- Elasticsearch (9200)

**运行命令：**
```bash
python test/e2e/test_full_index_build.py
```

**预期输出：**
- ✅ 成功处理 83/83 商品
- ✅ 生成约 580 个 chunks
- ✅ Qdrant: 580 个向量点
- ✅ Elasticsearch: 580 个文档

## 测试工具

### 1. 服务状态检查 (`check_services.py`)

检查所有 Docker 服务是否正常运行：
- Qdrant (6333)
- Elasticsearch (9200)
- MySQL (43306)
- Embedding Service (8100)

**运行命令：**
```bash
python test/utils/check_services.py
```

### 2. Embedding 模型验证 (`check_bge_m3_dimension.py`)

验证 BGE-M3 模型配置：
- ✅ 向量维度：1024
- ✅ 模型名称：BAAI/bge-m3
- ✅ Embedding 服务连通性

**运行命令：**
```bash
python test/utils/check_bge_m3_dimension.py
```

## 设计原则

### ✅ 只保留真实完整数据测试

所有测试均使用：
- **真实 MySQL 数据库**：完整的 83 个商品数据
- **真实 Docker 服务**：Qdrant、Elasticsearch、Embedding
- **完整业务流程**：JWT 认证、RAG 检索、LLM 生成

### ❌ 已删除简化/Mock测试

以下测试已清理：
- 单元测试（Mock 数据）
- 简化集成测试（部分数据）
- 临时调试脚本
- 开发中的测试草稿

### 为什么这样设计？

**用户原话：**
> "我想只保留使用真实完整数据跑的测试代码，然后统一放到项目根目录的test文件夹底下，其他测试代码删除，这样项目更加简洁。"

> "我怀疑严重你之前所有测试都是简化，实则在实际环境中根本跑不通。一定要跑全链路实际完整数据才有说服力。"

**优势：**
1. **真实性**：发现真实环境中的问题（如配置错误、格式不匹配）
2. **可靠性**：测试通过即代表系统可交付
3. **简洁性**：避免维护大量Mock测试

## 运行所有测试

```bash
# 1. 确保 Docker 服务运行
docker-compose -f docker/docker-compose.yml up -d

# 2. 检查服务状态
python test/utils/check_services.py

# 3. 构建离线索引（仅需运行一次）
python test/e2e/test_full_index_build.py

# 4. 运行 E2E 测试
python test/e2e/test_slice02_e2e_full.py
```

## 测试结果示例

```
总计: 5/7 通过 (71.4%)
✅ 通过 - Exact查询
✅ 通过 - 促销查询
✅ 通过 - 催拍催付
✅ 通过 - 基础闲聊
✅ 通过 - 多轮对话
❌ 失败 - 商品咨询(RAG)
❌ 失败 - Discovery查询
```

## 注意事项

1. **首次运行**：需先运行 `test_full_index_build.py` 构建索引
2. **测试用户**：确保 MySQL 中存在 `li_ming88` 用户且密码正确
3. **服务依赖**：所有 Docker 服务必须正常运行
4. **数据完整性**：测试依赖 MySQL 中的完整商品数据（83个）
