from __future__ import annotations

from customer_service.intents.entity_extractor import extract_entities, extract_entities_with_candidates
from customer_service.intents.models import (
    IntentResult,
    IntentDecision,
    IntentFallbackReason,
    IntentClassificationResult,
    IntentGoal,
    EntityCandidate,
    HybridIntentResult,
)
from customer_service.tasking.models import BusinessIntent

# NLU_HYBRID_REFACTOR：导入混合策略和实体融合模块
from customer_service.intents.hybrid_policy import (
    HybridNLUSettings,
    DEFAULT_SETTINGS,
    evaluate_confidence_level,
    should_call_llm,
    fuse_intent,
    ConfidenceLevel,
)
from customer_service.intents.entity_fusion import (
    EntityFusionService,
    llm_entities_to_candidates,
    rule_entities_to_candidates,
)

# P0-2修复：导入结构化LLM分类器（可选）
try:
    from customer_service.intents.structured_llm_classifier import StructuredLLMClassifier
    _llm_classifier_available = True
except ImportError:
    _llm_classifier_available = False
    StructuredLLMClassifier = None


# 关键词库 - 每个意图包含20-30个高频关键词，覆盖口语化表达
KEYWORDS: list[tuple[str, list[str]]] = [
    # 尺码推荐: 关于尺寸、码数、合身度的查询（但不含"换"、"退"等售后词）
    ("size_recommend", [
        "尺码", "码数", "穿什么码", "多大码", "推荐码", "适合穿", "合适吗", "合身",
        "身高", "体重", "腰围", "胸围", "臀围", "版型", "偏大", "偏小", "正常码",
        "码表", "尺寸", "size", "会不会大", "会不会小", "能穿吗", "穿得下",
        "选什么码", "选多大", "多大", "什么尺寸", "该选", "帮我推荐尺码"
    ]),

    # 催拍催付: 帮助客服催促客户下单或付款（Agent催用户）
    ("urge_order_payment", [
        "催拍", "催付", "下单话术", "付款话术", "劝他下单", "提醒付款",
        "还没付款", "没有付", "未付款", "待付款", "怎么催", "如何催", "话术", "说什么好",
        "什么时候付款", "何时付款", "付款时间", "犹豫", "观望", "考虑中"
    ]),

    # 催发货: 用户催促商家/平台发货（用户催平台）
    ("urge_shipping", [
        "催发货", "催一下", "催单", "催促", "快点发货", "赶紧发", "尽快发货",
        "还没发货", "什么时候发", "何时发货", "发货时间", "几天发货",
        "怎么还不发", "为什么不发", "能不能快点", "着急", "急用", "要得急",
        "帮我催", "催商家", "催卖家"
    ]),

    # 优惠查询: 关于价格优惠、促销活动（不包括单纯问价格）
    ("promotion_query", [
        "优惠", "促销", "活动", "折扣", "满减", "券", "便宜", "打折", "降价",
        "有活动吗", "有优惠吗", "能便宜", "特价", "秒杀",
        "拼团", "砍价", "红包", "津贴", "减免", "立减", "省钱", "实惠",
        "优惠券", "折扣码", "满多少", "减多少"
    ]),

    # 物流查询: 关于快递、配送、物流信息
    ("logistics_query", [
        "物流", "快递", "到哪", "运输", "配送", "单号", "发货", "收货",
        "什么时候到", "几天到", "到了吗", "在哪里", "查物流", "追踪",
        "运单号", "快递公司", "派送", "签收", "延迟", "没到"
    ]),

    # 退货: 关于退货、退款的请求
    ("return", [
        "退货", "退款", "退掉", "退回", "不想要", "退钱", "申请退",
        "可以退吗", "能退吗", "能不能退", "怎么退", "退货流程",
        "不满意", "不合适", "想退", "要退", "退了", "退单"
    ]),

    # 换货: 关于换货、换尺码、换颜色等（优先级高于size_recommend）
    ("exchange", [
        "换货", "换码", "换颜色", "换成", "换一件", "换个", "调换", "想换",
        "能换吗", "可以换吗", "能不能换", "怎么换", "换货流程",
        "换大", "换小", "换别的", "换款", "换尺寸", "重新发", "不合适想换"
    ]),

    # 商品查询: 关于商品信息、推荐、搜索（单纯问价格也算）
    ("product_query", [
        "商品", "推荐", "买", "想要", "适合", "怎么样", "卖点", "材质",
        "有没有", "有吗", "找", "搜", "查", "看看", "给我", "要",
        "什么款", "哪款", "品牌", "新品", "热销", "爆款", "款式",
        "运动鞋", "T恤", "裤子", "衣服", "鞋子", "包", "帽子",
        "多少钱", "价格", "价位", "衬衫", "外套", "连衣裙"
    ]),

    # 闲聊: 打招呼、寒暄、感谢等非业务对话
    ("chitchat", [
        "你好", "您好", "谢谢", "再见", "拜拜", "早上好", "晚上好",
        "你是谁", "什么名字", "干嘛", "在吗", "在不在", "hello",
        "哈喽", "hi", "hey", "thank", "thanks", "bye"
    ]),
]


class IntentClassifier:
    """
    意图分类器（混合模式）

    P0-2修复：支持关键词分类器和LLM结构化分类器
    - 优先使用确定性规则
    - 当关键词分类器不确定时，可选用LLM分类器

    P1-40修复：支持历史对话上下文
    - 关键词分类器：不需要历史对话（基于规则）
    - LLM分类器：可以传入历史对话增强上下文理解
    """

    def __init__(self, use_llm: bool = False):
        """
        Args:
            use_llm: 是否启用LLM分类器（默认False，使用关键词分类器）
        """
        self.use_llm = use_llm
        self.enabled = use_llm  # NLU_HYBRID_REFACTOR：classify_hybrid 使用此标志
        self.llm_classifier = None

        if use_llm and _llm_classifier_available:
            self.llm_classifier = StructuredLLMClassifier(enabled=True)

    def classify(self, message: str, history: str | None = None, active_intent: BusinessIntent | None = None) -> IntentResult:
        """
        识别用户意图

        Args:
            message: 当前用户消息
            history: 历史对话上下文（可选，用于LLM分类器）
            active_intent: 当前活跃的意图（用于意图继承）

        Returns:
            IntentResult: 意图识别结果
        """
        text = message.strip()
        # NLU_HYBRID_REFACTOR：使用新接口，entities 是 dict[str, EntityCandidate]
        entity_candidates = extract_entities_with_candidates(text)
        # 向后兼容：IntentResult.entities 仍使用 dict[str, Any]
        entities = {k: v.value for k, v in entity_candidates.items()}
        scores: dict[str, float] = {}

        # P2修复（参考修改建议2第十节）：检测省略式追问
        # "那29570呢？" / "15970呢？" / "这个呢？" 等应该继承上一轮意图
        if active_intent and _is_elliptical_followup(text):
            from loguru import logger
            logger.info(f"[IntentClassifier] 检测到省略式追问，继承意图: {active_intent.value}")

            # 继承上一轮意图，但降低置信度（因为可能用户想换话题）
            return IntentResult(
                recognized=True,
                intent=active_intent,
                decision=IntentDecision.ACCEPT,
                confidence=0.75,  # 继承意图的置信度略低
                entities=entities,
                inherited=True,  # 标记为继承的意图
            )

        # P1-40修复：如果启用了LLM分类器且提供了历史对话，优先使用LLM
        # 这可以更好地理解上下文，例如"那29570呢？"需要结合历史理解
        if self.use_llm and self.llm_classifier and history:
            from loguru import logger
            logger.info(f"[IntentClassifier] 使用LLM分类器（带历史上下文）")
            try:
                # TODO: 需要修改 StructuredLLMClassifier 支持历史对话参数
                # 暂时回退到关键词分类器
                pass
            except Exception as e:
                logger.warning(f"[IntentClassifier] LLM分类失败，回退到关键词: {e}")

        # P0-20 修复：特殊处理："售后"关键词出现时，无法明确识别是退货还是换货
        # 应返回 recognized=false + CLARIFY，而不是强行设为 "other"
        if "售后" in text:
            return IntentResult(
                recognized=False,
                intent=None,
                decision=IntentDecision.CLARIFY,
                fallback_reason=IntentFallbackReason.LOW_CONFIDENCE,
                confidence=0.6,
                candidate_intents=[BusinessIntent.RETURN, BusinessIntent.EXCHANGE],
                entities=entities,
            )

        # 关键词匹配计分
        for intent, words in KEYWORDS:
            hits = sum(1 for word in words if word in text)
            if hits:
                scores[intent] = min(0.55 + hits * 0.18, 0.97)

        # 优先级规则：售后意图 (退、换) 优先于尺码推荐
        if "换" in text and "exchange" in scores and "size_recommend" in scores:
            scores["exchange"] = min(scores["exchange"] + 0.15, 0.97)

        if "退" in text and "return" in scores and "size_recommend" in scores:
            scores["return"] = min(scores["return"] + 0.15, 0.97)

        # 优先级规则：物流特征词出现时，logistics_query 优先于 product_query
        # "查询订单 O20260811000004 的物流" 同时 hit "查"(product) + "物流/订单"(logistics)
        _logistics_boost_triggers = ["物流", "快递", "发货", "运单", "订单号", "收货", "签收"]
        if "logistics_query" in scores and "product_query" in scores:
            if any(w in text for w in _logistics_boost_triggers):
                scores["logistics_query"] = min(scores["logistics_query"] + 0.15, 0.97)

        # 实体推断：有颜色或价格但没有匹配到意图时，默认为商品查询
        if not scores and (entities.get("color") or entities.get("max_price")):
            scores["product_query"] = 0.72

        # P0-20 修复：没有任何匹配时，返回 recognized=false + CLARIFY
        # 而不是强行设为 "other"，这样可以触发低置信度澄清机制
        if not scores:
            return IntentResult(
                recognized=False,
                intent=None,
                decision=IntentDecision.CLARIFY,
                fallback_reason=IntentFallbackReason.LOW_CONFIDENCE,
                confidence=0.5,
                entities=entities,
            )

        # 排序并返回 - 成功识别到意图
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        top_intent, top_score = ranked[0]
        second_intent, second_score = ranked[1] if len(ranked) > 1 else (None, None)

        # 问题4调试：输出分类结果
        from loguru import logger
        logger.info(f"[IntentClassifier] 输入: '{text[:50]}...'")
        second_str = f"{second_intent}={second_score:.3f}" if second_score is not None else "None"
        logger.info(f"[IntentClassifier] Top意图: {top_intent}={top_score:.3f}, Second意图: {second_str}")

        # 映射 intent 字符串到 BusinessIntent 枚举
        intent_mapping = {
            "product_query": BusinessIntent.PRODUCT_QUERY,
            "size_recommend": BusinessIntent.SIZE_RECOMMEND,
            "urge_order_payment": BusinessIntent.URGE_ORDER_PAYMENT,
            "urge_shipping": BusinessIntent.URGE_SHIPPING,
            "promotion_query": BusinessIntent.PROMOTION_QUERY,
            "logistics_query": BusinessIntent.LOGISTICS_QUERY,
            "return": BusinessIntent.RETURN,
            "exchange": BusinessIntent.EXCHANGE,
            "chitchat": BusinessIntent.CHITCHAT,
        }

        business_intent = intent_mapping.get(top_intent)
        if not business_intent:
            # 无法映射，返回 CLARIFY
            return IntentResult(
                recognized=False,
                intent=None,
                decision=IntentDecision.CLARIFY,
                fallback_reason=IntentFallbackReason.LOW_CONFIDENCE,
                confidence=top_score,
                entities=entities,
            )

        # 计算 margin（置信度差值）
        margin = (top_score - second_score) if second_score else 1.0

        # 问题4修复：改进多意图判断逻辑
        # 按照文档要求：区分"一个目标提到多个关键词"和"两个独立目标"
        # 例如："这件鞋有优惠吗" vs "推荐鞋并查订单物流"

        # 步骤1：检测是否有明确的连接词表示两个独立目标
        has_independent_goals = _detect_independent_goals(text, top_intent, second_intent)
        logger.info(f"[IntentClassifier] 独立目标检测: {has_independent_goals}, margin={margin:.3f}")

        # 步骤2：如果检测到独立目标连接词，且第二个意图分数达到基本阈值（0.15），
        # 就认为是多意图，而不要求 margin 必须很小
        # 这是因为用户明确说了"并且"等连接词，表明确实是两个目标
        if has_independent_goals and second_score and second_score >= 0.15:
            logger.info(f"[IntentClassifier] 检测到多意图候选")
            # 映射第二个意图
            second_business_intent = intent_mapping.get(second_intent)
            candidate_intents = [business_intent]
            if second_business_intent and second_business_intent != business_intent:
                candidate_intents.append(second_business_intent)

            # 只有在真的有两个不同意图时才返回多意图
            if len(candidate_intents) >= 2:
                return IntentResult(
                    recognized=False,
                    intent=None,
                    decision=IntentDecision.CLARIFY,
                    fallback_reason=IntentFallbackReason.MULTIPLE_INTENTS,
                    confidence=top_score,
                    second_confidence=second_score,
                    margin=margin,
                    candidate_intents=candidate_intents,
                    entities=entities,
                )

        # 步骤3：即使没有明确连接词，如果分数很接近且都达到一定阈值，也可能是歧义
        # 这种情况更保守：要求 top_score >= 0.55, second_score >= 0.40, margin < 0.15
        elif (not has_independent_goals and second_score and
              top_score >= 0.55 and second_score >= 0.40 and margin < 0.15):
            second_business_intent = intent_mapping.get(second_intent)
            candidate_intents = [business_intent]
            if second_business_intent and second_business_intent != business_intent:
                candidate_intents.append(second_business_intent)

            if len(candidate_intents) >= 2:
                return IntentResult(
                    recognized=False,
                    intent=None,
                    decision=IntentDecision.CLARIFY,
                    fallback_reason=IntentFallbackReason.MULTIPLE_INTENTS,
                    confidence=top_score,
                    second_confidence=second_score,
                    margin=margin,
                    candidate_intents=candidate_intents,
                    entities=entities,
                )

        # 问题6修复：调整阈值逻辑
        # >= 0.55 → ACCEPT（包括 0.73 这样的中等置信度）
        # < 0.55 → CLARIFY (低置信度)
        #
        # 原因：实际测试发现 0.73 的分数对于"我想买鞋"、"谢谢"等明确意图已经足够高
        # 不应该被拒绝
        if top_score >= 0.55:
            decision = IntentDecision.ACCEPT
            fallback_reason = None
        else:
            # <0.55 → CLARIFY with LOW_CONFIDENCE
            return IntentResult(
                recognized=False,
                intent=None,
                decision=IntentDecision.CLARIFY,
                fallback_reason=IntentFallbackReason.LOW_CONFIDENCE,
                confidence=top_score,
                second_confidence=second_score,
                margin=margin,
                candidate_intents=[business_intent] if business_intent else [],
                entities=entities,
            )

        return IntentResult(
            recognized=(decision == IntentDecision.ACCEPT),
            intent=business_intent if decision == IntentDecision.ACCEPT else None,
            decision=decision,
            fallback_reason=fallback_reason,
            confidence=top_score,
            second_confidence=second_score,
            margin=margin,
            candidate_intents=[business_intent] if decision == IntentDecision.CLARIFY else [],
            entities=entities,
        )

    async def classify_hybrid(
        self,
        message: str,
        *,
        history: str | None = None,
        context: dict | None = None,
        active_intent: BusinessIntent | None = None,
        nlu_settings: HybridNLUSettings | None = None,
    ) -> HybridIntentResult:
        """
        NLU_HYBRID_REFACTOR：混合意图识别主入口（异步）

        流程：
        1. rule_classifier.classify() → 规则意图 + 置信度 + margin
        2. extract_entities_with_candidates() → 规则实体（EntityCandidate）
        3. hybrid_policy.should_call_llm() → 决策是否需要 LLM
        4. 必要时 StructuredLLMClassifier.classify() → LLM 意图 + LLM 实体
        5. fuse_intent() → 最终意图
        6. EntityFusionService.merge() → 融合实体
        7. 返回 HybridIntentResult（含可观测信息）

        Args:
            message: 当前用户消息
            history: 历史对话摘要（LLM prompt 上下文用）
            context: NLU 上下文（active_task / conversation_focus 等）
            active_intent: 当前活跃意图（意图继承）
            nlu_settings: Hybrid NLU 阈值配置
        """
        from loguru import logger

        cfg = nlu_settings or DEFAULT_SETTINGS
        fusion_svc = EntityFusionService()

        # ---- Step 1: 规则分类 ----
        rule_result = self.classify(message, history=history, active_intent=active_intent)
        rule_intent_val = rule_result.intent.value if rule_result.intent else None
        rule_conf = rule_result.confidence or 0.0
        rule_margin = rule_result.margin

        # ---- Step 2: 规则实体（带 EntityCandidate）----
        rule_entity_candidates = extract_entities_with_candidates(message)
        # 同步到 rule_result.entities（兼容旧逻辑）
        rule_result.entities.update({k: v.value for k, v in rule_entity_candidates.items()})

        rule_candidate_list = list(rule_entity_candidates.values())

        _margin_str = f"{rule_margin:.3f}" if rule_margin is not None else "0.000"
        logger.info(
            f"[NLU] rule_intent={rule_intent_val} "
            f"rule_confidence={rule_conf:.3f} "
            f"margin={_margin_str} "
            f"rule_entities={list(rule_entity_candidates.keys())}"
        )

        # ---- Step 3: Hybrid Policy 决策 ----
        ambiguous = (
            rule_result.decision == IntentDecision.CLARIFY
            and rule_result.fallback_reason == IntentFallbackReason.MULTIPLE_INTENTS
        )

        # 为了决策实体完整性，先拿本意图要求的核心实体
        required_core_entities = _get_core_entities_for_intent(rule_result.intent)
        call_decision = should_call_llm(
            confidence=rule_conf,
            margin=rule_margin,
            ambiguous=ambiguous,
            required_entities=required_core_entities,
            extracted_entities=rule_entity_candidates,
            settings=cfg,
        )

        # ---- Step 4: LLM 分类（必要时）----
        llm_called = False
        llm_intent_val: str | None = None
        llm_conf: float | None = None
        llm_candidate_list: list[EntityCandidate] = []

        if call_decision.should_call and self.llm_classifier and self.enabled:
            llm_context = _build_llm_context(message, context, rule_result, history)
            try:
                llm_result = await self.llm_classifier.classify(
                    message=message,
                    context=llm_context,
                    timeout=8.0,
                )
                llm_called = True

                if not llm_result.classifier_error and llm_result.goals:
                    top_goal = llm_result.goals[0]
                    llm_intent_val = top_goal.intent.value
                    llm_conf = top_goal.confidence

                    # 提取 LLM 实体候选（来自 goal.entities dict）
                    llm_raw = [
                        {"name": k, "value": v, "confidence": top_goal.confidence or 0.8}
                        for k, v in top_goal.entities.items()
                        if v
                    ]
                    llm_candidate_list = llm_entities_to_candidates(llm_raw)

                    logger.info(
                        f"[NLU] llm_called=true "
                        f"llm_intent={llm_intent_val} "
                        f"llm_confidence={llm_conf:.3f} "
                        f"llm_entities={[e.name for e in llm_candidate_list]}"
                    )
                else:
                    logger.warning(
                        f"[NLU] llm_called=true 但失败: {llm_result.classifier_error}"
                    )

            except Exception as e:
                logger.error(f"[NLU] LLM 调用异常: {e}", exc_info=True)
                llm_called = True  # 标记尝试过

        else:
            logger.info(
                f"[NLU] llm_called=false reason='{call_decision.reason}'"
            )

        # ---- Step 5: 意图融合 ----
        level = call_decision.level
        final_intent_val, final_conf, source = fuse_intent(
            rule_intent=rule_intent_val,
            rule_confidence=rule_conf,
            llm_intent=llm_intent_val if llm_called else None,
            llm_confidence=llm_conf or 0.0,
            level=level,
            settings=cfg,
        )

        # 映射 intent 字符串到枚举
        intent_map = {i.value: i for i in BusinessIntent}
        final_intent = intent_map.get(final_intent_val) if final_intent_val else None
        rule_intent_enum = intent_map.get(rule_intent_val) if rule_intent_val else None
        llm_intent_enum = intent_map.get(llm_intent_val) if llm_intent_val else None

        ambiguous_final = (final_intent is None and not rule_result.is_out_of_scope
                           if hasattr(rule_result, 'is_out_of_scope') else final_intent is None)

        # ---- Step 6: 实体融合 ----
        context_entities: list[EntityCandidate] = []
        if context and context.get("context_entity_candidates"):
            context_entities = context["context_entity_candidates"]

        fused_entities = fusion_svc.merge(
            rule_entities=rule_candidate_list,
            llm_entities=llm_candidate_list,
            context_entities=context_entities,
        )

        logger.info(
            f"[NLU] fusion_result intent={final_intent_val} "
            f"confidence={final_conf:.3f} source={source} "
            f"entity_sources={{{', '.join(f'{k}:{v.source}' for k, v in fused_entities.items())}}}"
        )

        return HybridIntentResult(
            intent=final_intent,
            confidence=final_conf,
            source=source,
            margin=rule_margin,
            ambiguous=ambiguous_final,
            entities=fused_entities,
            llm_called=llm_called,
            llm_intent=llm_intent_enum,
            llm_confidence=llm_conf,
            rule_intent=rule_intent_enum,
            rule_confidence=rule_conf,
            fallback_used=(llm_called and llm_intent_val is None),
            is_out_of_scope=rule_result.decision == IntentDecision.OUT_OF_SCOPE,
        )


# ==================== NLU_HYBRID_REFACTOR：辅助函数 ====================

def _get_core_entities_for_intent(intent: BusinessIntent | None) -> list[str]:
    """
    返回该意图的核心实体列表（用于决策是否需要 LLM 补全实体）。

    NLU_HYBRID_REFACTOR 第9节：should_call_llm 要考虑 entity completeness。
    这里只列 LLM 可能额外识别的核心实体（brand/product_name），
    不包括 product_id/order_id（这些只能靠规则/业务验证，LLM 不允许生成）。
    """
    if intent is None:
        return []
    _core_map: dict[BusinessIntent, list[str]] = {
        BusinessIntent.PRODUCT_QUERY: ["brand", "product_name"],
        BusinessIntent.PROMOTION_QUERY: ["brand", "product_name"],
        BusinessIntent.SIZE_RECOMMEND: ["brand", "product_name"],
    }
    return _core_map.get(intent, [])


def _build_llm_context(
    message: str,
    context: dict | None,
    rule_result,
    history: str | None,
) -> dict:
    """
    构建传给 StructuredLLMClassifier 的上下文。

    NLU_HYBRID_REFACTOR 第8节：包含 active_task / rule_result / recent_messages 等，
    不传整个 Redis State 或几十轮原始聊天。
    """
    nlu_ctx: dict = {}

    if context:
        if context.get("active_task_intent"):
            nlu_ctx["active_task_intent"] = context["active_task_intent"]
        if context.get("active_task_status"):
            nlu_ctx["active_task_status"] = context["active_task_status"]
        if context.get("missing_slots"):
            nlu_ctx["missing_slots"] = context["missing_slots"]
        if context.get("conversation_focus"):
            nlu_ctx["conversation_focus"] = context["conversation_focus"]
        if context.get("last_business_intent"):
            nlu_ctx["last_business_intent"] = context["last_business_intent"]

    # 传入规则分类器的结果（辅助 LLM 做判断）
    if rule_result.intent:
        nlu_ctx["rule_intent"] = rule_result.intent.value
    if rule_result.confidence:
        nlu_ctx["rule_confidence"] = f"{rule_result.confidence:.2f}"
    if rule_result.entities:
        nlu_ctx["rule_entities"] = rule_result.entities

    # 阶段2-任务4：增加历史对话到10轮（参考TurnPlanner传10轮）
    if history:
        lines = history.strip().split("\n")
        nlu_ctx["recent_messages"] = "\n".join(lines[-20:])  # 约10轮（每轮2行：USER+ASSISTANT）

    return nlu_ctx


def _detect_independent_goals(text: str, intent1: str, intent2: str | None) -> bool:
    """
    问题4修复：检测是否包含两个独立的用户目标

    区分两种情况：
    1. "这件鞋有优惠吗" - 一个目标（促销查询），只是提到了商品作为参数
    2. "推荐鞋并查订单物流" - 两个独立目标（商品推荐 + 物流查询）

    简化版实现：检查明确的连接词
    """
    if not intent2:
        return False

    # 明确表示两个独立动作的连接词
    independent_connectors = [
        "并且", "并", "同时", "还要", "另外", "再", "也要", "以及",
        "，然后", "，再", "，还", "，同时", "，另外"
    ]

    for connector in independent_connectors:
        if connector in text:
            return True

    return False


# ==================== 阶段1重构：适配器函数 ====================

def adapt_intent_result_to_classification(
    intent_result: IntentResult,
    user_message: str,
) -> IntentClassificationResult:
    """
    适配器：将旧的 IntentResult 转换为新的 IntentClassificationResult

    这是阶段1的过渡方案，保留现有关键词分类器，但输出新格式
    后续阶段可以替换为结构化 LLM 分类器

    Args:
        intent_result: 旧分类器的输出
        user_message: 用户原始消息

    Returns:
        IntentClassificationResult: 新格式的分类结果
    """
    goals: list[IntentGoal] = []

    # 情况1：成功识别到单个意图（ACCEPT）
    if intent_result.decision == IntentDecision.ACCEPT and intent_result.intent:
        goals.append(IntentGoal(
            intent=intent_result.intent,
            entities=intent_result.entities,
            text_span=user_message,  # 简化版：整句都算
            confidence=intent_result.confidence,
        ))
        return IntentClassificationResult(
            goals=goals,
            is_confident=True,
            is_out_of_scope=False,
            raw_response=None,
        )

    # 情况2：多意图（MULTIPLE_INTENTS）
    if (intent_result.decision == IntentDecision.CLARIFY and
        intent_result.fallback_reason == IntentFallbackReason.MULTIPLE_INTENTS):
        # 将 candidate_intents 转换为多个 IntentGoal
        for candidate_intent in intent_result.candidate_intents:
            goals.append(IntentGoal(
                intent=candidate_intent,
                entities=intent_result.entities,  # 简化：所有候选共享实体
                text_span=user_message,
                confidence=intent_result.confidence,
            ))
        return IntentClassificationResult(
            goals=goals,
            is_confident=True,  # 分类器确信有多个目标
            is_out_of_scope=False,
            raw_response=None,
        )

    # 情况3：低置信度
    if (intent_result.decision == IntentDecision.CLARIFY and
        intent_result.fallback_reason == IntentFallbackReason.LOW_CONFIDENCE):
        # 可能有候选，也可能没有
        for candidate_intent in intent_result.candidate_intents:
            goals.append(IntentGoal(
                intent=candidate_intent,
                entities=intent_result.entities,
                text_span=user_message,
                confidence=intent_result.confidence,
            ))
        return IntentClassificationResult(
            goals=goals,
            is_confident=False,  # 关键：标记为低置信度
            is_out_of_scope=False,
            raw_response=None,
        )

    # 情况4：超出范围
    if intent_result.decision == IntentDecision.OUT_OF_SCOPE:
        return IntentClassificationResult(
            goals=[],
            is_confident=True,
            is_out_of_scope=True,
            raw_response=None,
        )

    # 情况5：分类器失败
    if intent_result.decision == IntentDecision.CLASSIFIER_FAILURE:
        return IntentClassificationResult(
            goals=[],
            is_confident=False,
            is_out_of_scope=False,
            classifier_error="分类器内部错误",
            raw_response=None,
        )

    # 兜底：未知情况
    return IntentClassificationResult(
        goals=[],
        is_confident=False,
        is_out_of_scope=False,
        classifier_error=f"未知的决策类型: {intent_result.decision}",
        raw_response=None,
    )


async def classify_with_llm(
    classifier: IntentClassifier,
    message: str,
    context: dict | None = None
) -> IntentClassificationResult:
    """
    P0-2修复：使用LLM进行结构化分类（异步）

    根据文档第19行：
    - 先用关键词分类器（确定性规则）
    - 如果不确定（LOW_CONFIDENCE），尝试LLM分类器
    - LLM失败回退到关键词结果

    Args:
        classifier: IntentClassifier实例
        message: 用户消息
        context: 上下文（会话焦点、等待槽位等）

    Returns:
        IntentClassificationResult
    """
    # 先用关键词分类器
    keyword_result = classifier.classify(message)
    keyword_classification = adapt_intent_result_to_classification(keyword_result, message)

    # 如果关键词分类器有信心，直接返回
    if keyword_classification.is_confident:
        return keyword_classification

    # 如果启用了LLM分类器，尝试使用
    if classifier.llm_classifier:
        try:
            llm_result = await classifier.llm_classifier.classify(
                message=message,
                context=context,
                timeout=5.0
            )

            # 如果LLM分类成功，使用LLM结果
            if llm_result.is_confident and not llm_result.classifier_error:
                return llm_result

            # LLM失败，回退到关键词结果
            from loguru import logger
            logger.warning(
                f"LLM分类器不确定或失败，回退到关键词分类器: "
                f"error={llm_result.classifier_error}"
            )

        except Exception as e:
            from loguru import logger
            logger.error(f"LLM分类器异常，回退到关键词分类器: {e}")

    # 返回关键词分类结果（作为fallback）
    return keyword_classification


def _is_elliptical_followup(text: str) -> bool:
    """
    检测是否是省略式追问

    P2修复（参考修改建议2第十节）：
    省略式追问特征：
    1. 消息很短（通常<15字符）
    2. 包含"那"、"这"等指示词或纯数字
    3. 包含"呢"、"吗"、"怎么样"等疑问表达
    4. 不包含完整问句标志（"怎么选"、"如何"、"什么时候"等）

    Examples:
        - "那29570呢？"
        - "15970呢？"
        - "这个呢？"
        - "那个有促销吗？"
        - "那个怎么样？"

    反例：
        - "这款商品的尺码怎么选？" -> 完整问句，不是省略式
        - "29570有促销吗" -> 没有指示词，是完整表达

    Args:
        text: 用户消息

    Returns:
        是否是省略式追问
    """
    text = text.strip()

    # 特征1：消息很短（省略式追问通常简短）
    if len(text) > 15:
        return False

    # 排除完整问句标志（如果包含这些动词，说明是完整表达）
    # "怎么样"是例外，它是省略式的典型表达
    complete_question_markers = ["怎么选", "怎么买", "怎么用", "如何", "为什么", "什么时候", "哪里", "哪个", "多少钱"]
    if any(marker in text for marker in complete_question_markers):
        return False

    # 疑问词（包含"怎么样"这种省略式表达）
    question_markers = ["呢", "吗", "么", "怎么样"]
    has_question = any(q in text for q in question_markers)
    if not has_question:
        return False

    # 特征2：包含指示词
    elliptical_markers = ["那", "这", "这个", "那个", "它", "他"]
    has_marker = any(marker in text for marker in elliptical_markers)

    # 特征3：包含数字（商品ID）
    has_number = any(char.isdigit() for char in text)

    # 规则1：指示词 + 疑问词
    if has_marker and has_question:
        # 排除"这款"、"那款"等完整表达
        if "款" in text or "种" in text or "类" in text:
            return False
        return True

    # 规则2：纯数字 + 疑问词（如"15970呢？"）
    if has_number and has_question and not has_marker:
        # 检查是否主要是数字组成
        text_alphanumeric = ''.join(c for c in text if c.isalnum())
        if text_alphanumeric:
            digit_ratio = sum(1 for c in text_alphanumeric if c.isdigit()) / len(text_alphanumeric)
            if digit_ratio >= 0.5:
                return True

    return False
