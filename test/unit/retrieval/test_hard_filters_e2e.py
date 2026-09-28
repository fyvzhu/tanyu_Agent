"""
P1-05 端到端硬约束链测试

User Query → ContextResolver → QueryContext.hard_filters → ProductQueryFlow → ProductSearchInput
整条链都必须保持用户硬约束
"""
import pytest
from customer_service.retrieval.context_resolver import ContextResolver


class TestHardFiltersEndToEnd:
    """测试硬约束的端到端提取和传递"""

    def test_extract_price_only(self):
        """测试：只有价格约束"""
        resolver = ContextResolver()
        filters = resolver.extract_hard_filters("400元以内的裙子")
        
        assert filters.get("max_price") == 400
        assert "color" not in filters
        assert "category" not in filters

    def test_extract_color_and_price(self):
        """测试：颜色 + 价格（P1-05 核心案例）"""
        resolver = ContextResolver()
        filters = resolver.extract_hard_filters("只要黑色、400元以内的通勤裙")
        
        assert filters.get("max_price") == 400, "价格约束应该提取"
        assert filters.get("color") == "黑色", "颜色约束应该提取"
        assert filters.get("category") == "通勤裙", "品类约束应该提取"

    def test_extract_color_variants(self):
        """测试：不同颜色表达方式"""
        resolver = ContextResolver()
        
        # "要黑色"
        filters1 = resolver.extract_hard_filters("要黑色的T恤")
        assert filters1.get("color") == "黑色"
        
        # "白色的"
        filters2 = resolver.extract_hard_filters("白色的衬衫")
        assert filters2.get("color") == "白色"
        
        # "红色系"
        filters3 = resolver.extract_hard_filters("红色系连衣裙")
        assert filters3.get("color") == "红色"

    def test_extract_size(self):
        """测试：尺码提取"""
        resolver = ContextResolver()
        
        # "M码"
        filters1 = resolver.extract_hard_filters("M码的T恤")
        assert filters1.get("size") == "M"
        
        # "均码"
        filters2 = resolver.extract_hard_filters("均码连衣裙")
        assert filters2.get("size") == "均码"
        
        # "XL"
        filters3 = resolver.extract_hard_filters("XL号卫衣")
        assert filters3.get("size") == "XL"

    def test_extract_category(self):
        """测试：品类提取"""
        resolver = ContextResolver()
        
        filters1 = resolver.extract_hard_filters("通勤裙")
        assert filters1.get("category") == "通勤裙"
        
        filters2 = resolver.extract_hard_filters("T恤")
        assert filters2.get("category") == "T恤"
        
        filters3 = resolver.extract_hard_filters("运动鞋")
        assert filters3.get("category") == "运动鞋"

    def test_extract_brand(self):
        """测试：品牌提取"""
        resolver = ContextResolver()
        
        filters = resolver.extract_hard_filters("品牌是Nike的运动鞋")
        assert filters.get("brand") == "Nike"

    def test_extract_price_range(self):
        """测试：价格区间"""
        resolver = ContextResolver()
        
        # "200-500元"
        filters1 = resolver.extract_hard_filters("200到500元的连衣裙")
        assert filters1.get("min_price") == 200
        assert filters1.get("max_price") == 500
        
        # "300元以上"
        filters2 = resolver.extract_hard_filters("300元以上的外套")
        assert filters2.get("min_price") == 300

    def test_build_semantic_query_removes_constraints(self):
        """测试：语义查询应移除硬约束关键词"""
        resolver = ContextResolver()
        
        # 原始查询
        original = "只要黑色、400元以内的通勤裙"
        
        # 提取硬约束
        filters = resolver.extract_hard_filters(original)
        
        # 构建语义查询
        semantic = resolver.build_semantic_query(original, filters)
        
        # 语义查询应移除价格、颜色、"只要"等硬约束
        assert "400" not in semantic, "价格应被移除"
        assert "元" not in semantic, "价格单位应被移除"
        assert "黑色" not in semantic, "颜色应被移除"
        assert "只要" not in semantic, "硬约束修饰词应被移除"
        
        # 品类可以保留（对语义理解有帮助）
        assert "通勤裙" in semantic or semantic == original

    def test_complex_query_all_filters(self):
        """测试：复杂查询，包含多个硬约束"""
        resolver = ContextResolver()
        
        filters = resolver.extract_hard_filters("要黑色M码、200到400元的通勤连衣裙")
        
        assert filters.get("color") == "黑色"
        assert filters.get("size") == "M"
        assert filters.get("min_price") == 200
        assert filters.get("max_price") == 400
        assert filters.get("category") in ["通勤连衣裙", "连衣裙"]

    def test_no_constraints(self):
        """测试：无硬约束的模糊查询"""
        resolver = ContextResolver()
        
        filters = resolver.extract_hard_filters("有什么好看的裙子推荐吗")
        
        # 应该没有提取到任何硬约束
        assert not filters or len(filters) == 0

    def test_semantic_query_preserves_soft_context(self):
        """测试：语义查询保留软性上下文"""
        resolver = ContextResolver()
        
        original = "适合上班穿的黑色通勤裙，400元以内"
        filters = resolver.extract_hard_filters(original)
        semantic = resolver.build_semantic_query(original, filters)
        
        # "适合上班穿"是软性使用场景，应该保留
        assert "上班" in semantic or "通勤" in semantic
