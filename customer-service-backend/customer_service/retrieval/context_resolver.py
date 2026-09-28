"""
上下文解析器 - 解析用户查询中的商品指代和约束条件
"""
from __future__ import annotations

import logging
import re
from typing import Any

from customer_service.graph.state import AgentState, get_conversation_products, get_focused_product_id
from customer_service.retrieval.models import QueryContext

logger = logging.getLogger(__name__)


class ContextResolver:
    """解析用户查询的上下文，提取商品指代和约束条件"""
    
    # 硬约束关键词（这些会从语义查询中移除）
    HARD_FILTER_KEYWORDS = {
        "brand": ["品牌", "牌子", "厂家", "出品"],
        "color": ["颜色", "色", "黑色", "白色", "红色", "蓝色", "灰色", "粉色", "黄色", "绿色", "紫色"],
        "size": ["尺码", "码数", "S", "M", "L", "XL", "XXL", "均码"],
        "price": ["价格", "多少钱", "元", "便宜", "贵", "实惠"],
    }
    
    async def resolve(self, user_query: str, state: AgentState) -> QueryContext:
        """
        解析查询上下文

        关键决策顺序（P0-01 修复）：
        1. 本条消息明确给出 product_id → explicit
        2. 本条消息是发现型需求（推荐/找/还有其他）→ discovery（优先于历史 focus）
        3. 序数指代（第一/第二/第三款）→ ordinal 映射到 explicit_product_id
        4. 本条消息有明确指代词且能唯一映射 → anaphora
        5. 指代有歧义 → ambiguous
        6. 无明确对象 → none
        """
        # 1. 提取本条消息中明确的 product_id
        explicit_product_id = self.extract_product_id_from_text(user_query)

        # 2. 获取历史焦点商品（仅作为上下文，不优先）
        # 问题二修复：使用新的辅助函数从 conversation_focus 提取
        focused_product_id = get_focused_product_id(state)

        # 3. 获取对话中的商品列表（用于序数映射和歧义检测）
        # 问题二修复：使用新的辅助函数从 active_task.slots["candidates"] 提取
        conversation_products = get_conversation_products(state)

        # 4. 判断查询目标和指代类型
        query_goal, reference_kind = self._classify_query_intent(
            user_query, explicit_product_id, focused_product_id, conversation_products
        )

        # 5. P0-01 核心修复：处理序数指代，映射到 explicit_product_id
        if reference_kind == "ordinal":
            ordinal_index = self._extract_ordinal_reference(user_query)
            if ordinal_index is not None and 0 <= ordinal_index < len(conversation_products):
                # 将序数映射的 product_id 提升为 explicit_product_id
                explicit_product_id = conversation_products[ordinal_index]
                logger.info(
                    f"🔗 Ordinal mapping: '第{ordinal_index+1}款' → product_id={explicit_product_id}"
                )
                # 将 reference_kind 改为 anaphora（因为已经完成映射）
                reference_kind = "anaphora"

        # 6. 处理简单指代词的唯一映射
        elif reference_kind == "anaphora" and not explicit_product_id:
            # 如果是 anaphora 但还没有 explicit_product_id，尝试从上下文推断
            if len(conversation_products) == 1:
                explicit_product_id = conversation_products[0]
                logger.info(f"🔗 Anaphora mapping: unique candidate → product_id={explicit_product_id}")
            elif focused_product_id:
                explicit_product_id = focused_product_id
                logger.info(f"🔗 Anaphora mapping: focused product → product_id={explicit_product_id}")

        # 7. 提取硬约束
        hard_filters = self.extract_hard_filters(user_query)

        # 8. 构造语义查询（移除硬约束关键词）
        semantic_query = self.build_semantic_query(user_query, hard_filters)

        # 9. 提取软信号（用户偏好等）
        soft_signals = self.extract_soft_signals(state)

        logger.info(
            f"📋 Context resolved - explicit: {explicit_product_id}, "
            f"focused: {focused_product_id}, goal: {query_goal}, "
            f"reference: {reference_kind}, semantic: '{semantic_query}'"
        )

        return QueryContext(
            original_query=user_query,
            semantic_query=semantic_query,
            hard_filters=hard_filters,
            soft_signals=soft_signals,
            explicit_product_id=explicit_product_id,
            focused_product_id=focused_product_id,
            reference_kind=reference_kind,
            query_goal=query_goal,
            conversation_products=conversation_products,
        )
    
    def extract_product_id_from_text(self, text: str) -> str | None:
        """从文本中提取明确的 product_id"""
        # 匹配 #12345 或 SKU12345 或 商品12345 或 裸数字5位 等格式
        patterns = [
            r"#(\d+)",
            r"SKU\s*[:\-]?\s*(\d+)",
            r"商品\s*[:\-]?\s*(\d+)",
            r"ID\s*[:\-]?\s*(\d+)",
            r"(\d{4,6})(?:\s|$|[，。？！])",  # 匹配4-6位独立数字
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                product_id = match.group(1)
                logger.debug(f"✓ Extracted product_id from text: {product_id}")
                return product_id

        return None

    def extract_hard_filters(self, text: str) -> dict[str, Any]:
        """
        提取硬约束条件（品牌、颜色、尺码、价格、品类等）

        P1-05 修复：完整提取所有结构化硬约束
        User Query → ContextResolver → QueryContext.hard_filters → ProductQueryFlow → ProductSearchInput
        整条链都必须保持用户硬约束
        """
        filters: dict[str, Any] = {}

        # 1. 提取价格范围
        # "400元以下" 或 "400元以内"
        price_match = re.search(r"(\d+)\s*[元块]\s*(?:以下|以内)", text)
        if price_match:
            filters["max_price"] = int(price_match.group(1))

        # "300元以上"
        price_match = re.search(r"(\d+)\s*[元块]\s*以上", text)
        if price_match:
            filters["min_price"] = int(price_match.group(1))

        # "200到500元" 或 "200-500元"
        price_match = re.search(r"(\d+)\s*[-到~]\s*(\d+)\s*[元块]", text)
        if price_match:
            filters["min_price"] = int(price_match.group(1))
            filters["max_price"] = int(price_match.group(2))

        # 2. 提取颜色（"只要黑色"、"黑色的"、"要白色"）
        color_patterns = [
            r"(?:只要|要|想要|需要)?([黑白红蓝绿黄紫粉灰棕橙][色])",
            r"([黑白红蓝绿黄紫粉灰棕橙][色])(?:的|系)",
        ]
        for pattern in color_patterns:
            match = re.search(pattern, text)
            if match:
                filters["color"] = match.group(1)
                break

        # 3. 提取尺码（"M码"、"大码"、"均码"）
        size_patterns = [
            r"([SMLXL]{1,3})[码号]?",
            r"(均码|大码|小码|加大码)",
            r"(\d{2,3})码",
        ]
        for pattern in size_patterns:
            match = re.search(pattern, text)
            if match:
                filters["size"] = match.group(1)
                break

        # 4. 提取品类/类目（"通勤裙"、"T恤"、"运动鞋"）
        # 常见品类关键词
        category_keywords = [
            r"(连衣裙|半身裙|长裙|短裙|通勤裙|A字裙)",
            r"(T恤|衬衫|卫衣|毛衣|外套|风衣|羽绒服)",
            r"(运动鞋|板鞋|帆布鞋|皮鞋|高跟鞋|凉鞋)",
            r"(牛仔裤|休闲裤|运动裤|短裤)",
            r"(包包|手提包|双肩包|单肩包)",
        ]
        for pattern in category_keywords:
            match = re.search(pattern, text)
            if match:
                filters["category"] = match.group(1)
                break

        # 5. 提取品牌（需要品牌词库，这里先提取明确的品牌表达）
        # 改进：避免贪婪匹配，只提取品牌名称本身
        brand_match = re.search(r"(?:品牌|牌子)[是:]?\s*([A-Za-z\u4e00-\u9fa5]+?)(?:的|[，、])", text)
        if brand_match:
            filters["brand"] = brand_match.group(1)

        return filters
    
    def build_semantic_query(self, original_query: str, hard_filters: dict[str, Any]) -> str:
        """
        构造语义查询（移除硬约束关键词）

        P1-05 修复：移除所有结构化硬约束，避免干扰语义搜索
        保留软性的使用场景、风格偏好等语义信息
        """
        semantic = original_query

        # 1. 移除价格表达
        semantic = re.sub(r"\d+\s*[元块]\s*(?:以[下上内])", "", semantic)
        semantic = re.sub(r"\d+\s*[-到~]\s*\d+\s*[元块]", "", semantic)

        # 2. 移除已提取的颜色（如果存在）
        if hard_filters.get("color"):
            color = hard_filters["color"]
            semantic = re.sub(rf"(?:只要|要|想要|需要)?{color}(?:的|系)?", "", semantic)

        # 3. 移除已提取的尺码
        if hard_filters.get("size"):
            size = hard_filters["size"]
            semantic = re.sub(rf"{size}[码号]?", "", semantic)

        # 4. 移除已提取的品类（保留在语义查询中可能有帮助，暂不移除）
        # 品类如"通勤裙"对语义理解有价值，暂时保留

        # 5. 移除已提取的品牌
        if hard_filters.get("brand"):
            brand = hard_filters["brand"]
            semantic = re.sub(rf"(?:品牌|牌子)[是:]?\s*{brand}", "", semantic)

        # 6. 移除"只要"、"必须"等硬约束修饰词
        semantic = re.sub(r"(?:只要|必须|一定要|只能是)", "", semantic)

        # 去除多余空格和标点
        semantic = re.sub(r"[,，、]+", " ", semantic)
        semantic = " ".join(semantic.split())

        return semantic if semantic else original_query
    
    def _extract_ordinal_reference(self, text: str) -> int | None:
        """
        提取序数指代，返回对应的索引（0-based）

        示例：
        - "第一款" → 0
        - "第二个" → 1
        - "第三件" → 2

        Returns:
            int | None: 索引（0-based），未找到返回 None
        """
        ordinal_patterns = {
            "第一": 0, "第1": 0, "1": 0, "一": 0,
            "第二": 1, "第2": 1, "2": 1, "二": 1,
            "第三": 2, "第3": 2, "3": 2, "三": 2,
            "第四": 3, "第4": 3, "4": 3, "四": 3,
            "第五": 4, "第5": 4, "5": 4, "五": 4,
        }

        for pattern, index in ordinal_patterns.items():
            # 检查是否有 "第X款/个/件"
            if re.search(rf"{pattern}[款个件]", text):
                logger.debug(f"✓ Ordinal detected: '{pattern}' → index {index}")
                return index

        return None

    def extract_soft_signals(self, state: AgentState) -> dict[str, Any]:
        """提取软信号（用户偏好等）"""
        # 未来可以从长期记忆中提取用户偏好
        return {}

    def _classify_query_intent(
        self,
        user_query: str,
        explicit_product_id: str | None,
        focused_product_id: str | None,
        conversation_products: list[str],
    ) -> tuple[str, str]:
        """
        分类查询意图和指代类型

        返回: (query_goal, reference_kind)

        决策顺序（P0-01 修复）：
        1. 消息明确给出 product_id → ("exact_detail", "explicit")
        2. 消息是发现型需求（推荐/找/还有/其他）→ ("discovery", "none") - 永远优先于历史 focus
        3. 序数指代（第一/第二/第三款）且能映射 → ("exact_detail", "anaphora") - 从 candidate_list 映射
        4. 普通指代词（这个/这款）且能唯一映射 → ("exact_detail", "anaphora")
        5. 指代有歧义（多个商品未明确） → ("unclear", "ambiguous")
        6. 无明确对象 → ("unclear", "none")
        """
        query_lower = user_query.lower()

        # 1. 消息明确给出 product_id（最高优先级）
        if explicit_product_id:
            logger.debug(f"✓ Explicit product_id detected: {explicit_product_id}")
            return ("exact_detail", "explicit")

        # 2. 发现型需求关键词（优先级第二，永远压过历史 focus）
        discovery_keywords = [
            "推荐", "找", "有没有", "还有", "其他", "别的", "更多",
            "类似", "同类", "换", "看看", "哪些", "什么样",
        ]
        if any(keyword in query_lower for keyword in discovery_keywords):
            logger.debug(f"✓ Discovery intent detected - overrides historical focus")
            return ("discovery", "none")

        # 3. 序数指代（第一/第二/第三款）- P0-01 核心修复
        ordinal_match = self._extract_ordinal_reference(user_query)
        if ordinal_match is not None:
            # 序数从 0 开始：第一款 = index 0
            if 0 <= ordinal_match < len(conversation_products):
                # 可以映射到具体商品
                resolved_product_id = conversation_products[ordinal_match]
                logger.debug(
                    f"✓ Ordinal reference '第{ordinal_match+1}款' resolved to product: {resolved_product_id}"
                )
                # 注意：这里返回 anaphora，但实际映射的 product_id 需要在 resolve() 中更新到 explicit_product_id
                return ("exact_detail", "ordinal")  # 新增类型：ordinal
            else:
                # 序数超出范围
                logger.debug(
                    f"⚠ Ordinal reference '第{ordinal_match+1}款' out of range: "
                    f"only {len(conversation_products)} products available"
                )
                return ("unclear", "ambiguous")

        # 4. 普通指代词（这件/那件/这个/那个/这款/那款）
        simple_anaphora_patterns = [
            "这件", "那件", "这个", "那个", "这款", "那款",
            "刚才", "刚说", "刚提", "上面", "前面",
        ]
        has_simple_anaphora = any(pattern in user_query for pattern in simple_anaphora_patterns)

        if has_simple_anaphora:
            # 检查是否能唯一映射
            if len(conversation_products) == 1:
                # 只有一个候选，明确映射
                logger.debug(f"✓ Simple anaphora resolved to unique product: {conversation_products[0]}")
                return ("exact_detail", "anaphora")
            elif len(conversation_products) > 1:
                # 多个候选，需要用户明确
                logger.debug(f"⚠ Simple anaphora ambiguous: {len(conversation_products)} products in conversation")
                return ("unclear", "ambiguous")
            elif focused_product_id:
                # 没有 conversation_products，但有历史 focus
                logger.debug(f"✓ Simple anaphora resolved to focused product: {focused_product_id}")
                return ("exact_detail", "anaphora")

        # 5. 无指代词，但有历史 focus，且查询像是继续询问详情
        detail_keywords = [
            "多少钱", "价格", "什么材质", "材料", "颜色", "尺码",
            "码数", "有货", "库存", "怎么样", "好不好",
        ]
        is_detail_query = any(keyword in query_lower for keyword in detail_keywords)

        if is_detail_query and focused_product_id:
            logger.debug(f"✓ Detail query about focused product: {focused_product_id}")
            return ("exact_detail", "anaphora")

        # 6. 其他情况：不明确
        logger.debug(f"? Unclear query intent")
        return ("unclear", "none")