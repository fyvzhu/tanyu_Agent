"""
测试查询路由逻辑 - S02-F01
验证 Context Resolver 和 Query Planner 的路由优先级
"""
import pytest
from customer_service.retrieval.context_resolver import ContextResolver
from customer_service.retrieval.query_planner import QueryPlanner
from customer_service.graph.state import AgentState


class TestQueryRouting:
    """测试查询路由 - P0-01 问题修复验证"""

    @pytest.fixture
    def resolver(self):
        return ContextResolver()

    @pytest.fixture
    def planner(self):
        return QueryPlanner()

    @pytest.mark.asyncio
    async def test_p01_discovery_overrides_old_focus(self, resolver, planner):
        """
        P-01: 商品15970多少钱？→ Exact
        """
        state: AgentState = {
            "focused_object": None,
            "short_memory": {}
        }
        
        context = await resolver.resolve("商品15970多少钱？", state)
        plan = planner.plan(context)
        
        # 应该识别为 explicit product_id
        assert context.query_goal == "exact_detail"
        assert context.reference_kind == "explicit"
        assert plan == "direct"

    @pytest.mark.asyncio
    async def test_p05_discovery_with_old_focus(self, resolver, planner):
        """
        P-05: 前一轮看15970，本轮"还有什么好看的运动鞋？" → Discovery（不是 Exact）
        关键测试：发现型需求优先级 > 历史 focus
        """
        state: AgentState = {
            "focused_object": {"type": "product", "product_id": "15970"},
            "short_memory": {
                "candidate_products": [{"product_id": "15970"}]
            }
        }
        
        context = await resolver.resolve("还有什么好看的运动鞋？", state)
        plan = planner.plan(context)
        
        # 关键断言：即使有 focused_product_id=15970，仍应该走 discovery
        assert context.focused_product_id == "15970"  # 历史 focus 存在
        assert context.query_goal == "discovery"  # 但 goal 是 discovery
        assert context.reference_kind == "none"  # 不是指代
        assert plan == "rag"  # 走 RAG 路径

    @pytest.mark.asyncio
    async def test_p02_exact_with_anaphora(self, resolver, planner):
        """
        P-02: 已唯一确认15970："这件是什么材质？" → Exact
        """
        state: AgentState = {
            "focused_object": {"type": "product", "product_id": "15970"},
            "short_memory": {
                "candidate_products": [{"product_id": "15970"}]
            }
        }
        
        context = await resolver.resolve("这件是什么材质？", state)
        plan = planner.plan(context)
        
        assert context.query_goal == "exact_detail"
        assert context.reference_kind == "anaphora"
        assert context.focused_product_id == "15970"
        assert plan == "direct"

    @pytest.mark.asyncio
    async def test_p07_ambiguous_reference(self, resolver, planner):
        """
        P-07: 前一轮推荐了三款："这个材质怎么样？" → Clarify
        """
        state: AgentState = {
            "focused_object": None,
            "short_memory": {
                "candidate_products": [
                    {"product_id": "101"},
                    {"product_id": "102"},
                    {"product_id": "103"}
                ]
            }
        }
        
        context = await resolver.resolve("这个材质怎么样？", state)
        plan = planner.plan(context)
        
        assert context.query_goal == "unclear"
        assert context.reference_kind == "ambiguous"
        assert len(context.conversation_products) == 3
        assert plan == "clarify"

    @pytest.mark.asyncio
    async def test_p04_pure_discovery(self, resolver, planner):
        """
        P-04: 新会话："想找舒适透气的 T 恤，有什么推荐？" → Discovery
        """
        state: AgentState = {
            "focused_object": None,
            "short_memory": {}
        }
        
        context = await resolver.resolve("想找舒适透气的 T 恤，有什么推荐？", state)
        plan = planner.plan(context)
        
        assert context.query_goal == "discovery"
        assert context.reference_kind == "none"
        assert plan == "rag"
        assert "舒适透气" in context.semantic_query or "T恤" in context.semantic_query
