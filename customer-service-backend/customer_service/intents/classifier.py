from __future__ import annotations

from customer_service.intents.entity_extractor import extract_entities
from customer_service.intents.models import IntentResult, IntentDecision, IntentFallbackReason
from customer_service.tasking.models import BusinessIntent


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
    """Rule-first classifier. LLM structured classification can be added behind this interface."""

    def classify(self, message: str) -> IntentResult:
        text = message.strip()
        entities = extract_entities(text)
        scores: dict[str, float] = {}

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
            # 如果包含"换"字，exchange意图加权
            scores["exchange"] = min(scores["exchange"] + 0.15, 0.97)

        if "退" in text and "return" in scores and "size_recommend" in scores:
            # 如果包含"退"字，return意图加权
            scores["return"] = min(scores["return"] + 0.15, 0.97)

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
