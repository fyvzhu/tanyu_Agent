"""
结构化LLM分类器 - NLU_HYBRID_REFACTOR 重写

核心改造（根据 NLU_HYBRID_REFACTOR.md 第7节）：
- 替换 Mock _call_llm_with_timeout → 真实 get_llm() + ainvoke
- 优先使用 with_structured_output(StructuredNLUOutput, method="json_mode")
- 回退方案：ainvoke → 从响应文本提取 JSON → StructuredNLUOutput.model_validate_json()
- timeout + 完整 fail-soft（LLM 失败不让 API 500）
- Prompt 包含完整上下文（第8节要求）

禁止事项：
- 不新增第二套 LLM Client，复用 get_llm()
- LLM 自由文本不能直接进入 AgentState
- reasoning 只用于日志，不用于路由控制
- LLM 不能自己生成 product_id / order_id（只提取原文出现的）
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from loguru import logger
from pydantic import ValidationError

from customer_service.tasking.models import BusinessIntent
from customer_service.intents.models import (
    IntentClassificationResult,
    IntentGoal,
    StructuredNLUOutput,
)
from customer_service.infrastructure.llm import get_llm


# ---------------------------------------------------------------------------
# 业务意图描述（用于 Prompt 构造）
# ---------------------------------------------------------------------------
_INTENT_DESCRIPTIONS: dict[BusinessIntent, str] = {
    BusinessIntent.PRODUCT_QUERY: "商品查询与推荐，包括查找商品、询问商品信息、材质、价格等",
    BusinessIntent.SIZE_RECOMMEND: "尺码推荐，包括询问合适码数、根据身材推荐尺寸",
    BusinessIntent.URGE_ORDER_PAYMENT: "催拍催付，帮助客服催促客户下单或付款",
    BusinessIntent.PROMOTION_QUERY: "优惠活动查询，包括询问折扣、满减、特价、活动等",
    BusinessIntent.LOGISTICS_QUERY: "物流查询，包括查快递、问什么时候到、查运单号",
    BusinessIntent.RETURN: "退货退款，包括申请退货、询问退款流程",
    BusinessIntent.EXCHANGE: "换货，包括申请换码、换颜色、换款",
    BusinessIntent.CHITCHAT: "闲聊寒暄，包括打招呼、道谢、无明确业务意图的对话",
    BusinessIntent.URGE_SHIPPING: "催发货，用户催促商家/平台发货",
}


def _build_nlu_prompt(message: str, context: dict[str, Any] | None) -> str:
    """
    构造 LLM NLU 提示词

    阶段2-任务5：优化Prompt结构
    - 添加业务意图详细说明
    - 添加few-shot示例
    - 增强上下文信息传递

    根据 NLU_HYBRID_REFACTOR 第8节：至少包含：
    current_message / active_task info / rule_result / recent_messages（精简）
    不传整个 Redis State 或几十轮原始聊天。
    """
    intent_list = "\n".join(
        f"- {intent.value}: {desc}"
        for intent, desc in _INTENT_DESCRIPTIONS.items()
    )

    context_block = ""
    if context:
        parts = []
        if context.get("active_task_intent"):
            parts.append(f"当前任务意图: {context['active_task_intent']}")
        if context.get("active_task_status"):
            parts.append(f"当前任务状态: {context['active_task_status']}")
        if context.get("missing_slots"):
            parts.append(f"等待补充的槽位: {context['missing_slots']}")
        if context.get("conversation_focus"):
            parts.append(f"会话焦点: {context['conversation_focus']}")
        if context.get("last_business_intent"):
            parts.append(f"上一轮业务意图: {context['last_business_intent']}")
        if context.get("focused_object"):
            obj = context["focused_object"]
            parts.append(f"当前关注对象: {obj.get('entity_type')}={obj.get('entity_id')}")
        if context.get("paused_tasks"):
            parts.append(f"挂起的任务: {context['paused_tasks']}")
        if context.get("available_intents"):
            parts.append(f"系统支持的意图: {', '.join(context['available_intents'])}")
        if context.get("rule_intent"):
            parts.append(f"规则意图候选: {context['rule_intent']} (置信度={context.get('rule_confidence', '?')})")
        if context.get("rule_entities"):
            parts.append(f"规则实体: {context['rule_entities']}")
        if context.get("recent_messages"):
            history = context["recent_messages"]
            if isinstance(history, list):
                history = history[-10:]  # 最多10轮
            parts.append(f"最近对话:\n{history}")
        if parts:
            context_block = "\n\n## 对话上下文\n" + "\n".join(parts)

    # 阶段2-任务5：添加few-shot示例
    few_shot_examples = """
## 示例（Few-shot Examples）

### 示例1：商品查询
用户消息: "我想买Puma的运动鞋"
分析结果:
```json
{
  "goals": [{
    "intent": "product_query",
    "entities": {"brand": "Puma", "product_name": "运动鞋"},
    "confidence": 0.92,
    "reasoning": "用户明确表达购买意图，提到品牌和商品类别"
  }]
}
```

### 示例2：促销查询
用户消息: "商品15970有优惠吗？"
分析结果:
```json
{
  "goals": [{
    "intent": "promotion_query",
    "entities": {"product_id": "15970"},
    "confidence": 0.95,
    "reasoning": "用户询问优惠信息，明确提到商品ID"
  }]
}
```

### 示例3：省略式追问（需要结合上下文）
对话上下文: 上一轮业务意图=promotion_query
用户消息: "那29570呢？"
分析结果:
```json
{
  "goals": [{
    "intent": "promotion_query",
    "entities": {"product_id": "29570"},
    "confidence": 0.88,
    "reasoning": "继承上一轮的促销查询意图，用户只是更换了商品ID"
  }]
}
```

### 示例4：指代消解
对话上下文: 当前关注对象=product:15970
用户消息: "这个有货吗？"
分析结果:
```json
{
  "goals": [{
    "intent": "product_query",
    "entities": {"product_id": "15970"},
    "confidence": 0.85,
    "reasoning": "指代词'这个'指向当前关注的商品15970"
  }]
}
```

### 示例5：闲聊
用户消息: "谢谢你的帮助"
分析结果:
```json
{
  "goals": [{
    "intent": "chitchat",
    "entities": {},
    "confidence": 0.98,
    "reasoning": "礼貌用语，无明确业务需求"
  }]
}
```
"""

    return f"""你是电商客服意图分类助手，请根据用户消息和对话上下文，输出严格的 JSON 格式分析结果。

## 支持的业务意图
{intent_list}

## 当前用户消息
{message}{context_block}

{few_shot_examples}

## 重要规则
1. intent 必须是上述枚举值之一
2. confidence 为 0.0-1.0 浮点数
3. entities 只提取用户原文中明确出现的信息，严禁推测或编造 product_id / order_id
4. 如语义不明确设 needs_clarification=true，超出范围设 is_out_of_scope=true
5. reasoning 仅供调试，不影响路由

## 输出格式（必须是合法 JSON）
{{
  "goals": [
    {{
      "intent": "意图枚举值",
      "confidence": 0.85,
      "text_span": "原文片段",
      "entities": [
        {{"name": "实体名", "value": "实体值", "confidence": 0.9, "text_span": "原文"}}
      ]
    }}
  ],
  "is_out_of_scope": false,
  "needs_clarification": false,
  "reasoning": "简短推理"
}}"""


def _extract_json_from_text(text: str) -> str:
    """从 LLM 响应文本中提取 JSON 块（兼容 markdown 代码块）"""
    # 优先尝试 ```json ... ``` 格式
    md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if md_match:
        return md_match.group(1)

    # 查找第一个完整 JSON 对象
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return text


class StructuredLLMClassifier:
    """
    结构化LLM分类器（NLU_HYBRID_REFACTOR 重写版）

    职责：接受消息+上下文，返回 IntentClassificationResult（LLM 来源）
    不负责：Hybrid Policy 决策、Entity Fusion、Task 管理
    """

    def __init__(self, enabled: bool = False):
        self.enabled = enabled
        self._llm = None
        self._structured_llm = None
        self._use_structured_output = False

    def _init_llm(self) -> None:
        """延迟初始化 LLM（避免模块加载时连接）"""
        if self._llm is not None:
            return
        self._llm = get_llm()
        # 优先尝试 structured output（json_mode）
        try:
            self._structured_llm = self._llm.with_structured_output(
                StructuredNLUOutput,
                method="json_mode",
            )
            self._use_structured_output = True
            logger.info("[StructuredLLMClassifier] 使用 structured_output(json_mode) 模式")
        except Exception as e:
            self._structured_llm = None
            self._use_structured_output = False
            logger.warning(
                f"[StructuredLLMClassifier] structured_output 不支持 ({e})，"
                "回退到 ainvoke + JSON 解析模式"
            )

    async def _invoke_structured(self, prompt: str) -> StructuredNLUOutput:
        """使用 structured_output 调用（优先路径）"""
        result = await self._structured_llm.ainvoke(prompt)
        # with_structured_output 直接返回 Pydantic 对象
        if isinstance(result, StructuredNLUOutput):
            return result
        # 某些 provider 返回 dict
        return StructuredNLUOutput.model_validate(result)

    async def _invoke_with_json_parse(self, prompt: str) -> StructuredNLUOutput:
        """使用 ainvoke + 手动 JSON 解析（回退路径）"""
        response = await self._llm.ainvoke(prompt)
        raw_text = response.content if hasattr(response, "content") else str(response)

        json_text = _extract_json_from_text(raw_text)
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise ValidationError.from_exception_data(
                title="JSONDecodeError",
                input_type="python",
                input_value={"_error": str(e)},
                line_errors=[],
            ) from e

        return StructuredNLUOutput.model_validate(data)

    async def _invoke_llm(self, prompt: str) -> StructuredNLUOutput:
        """统一 LLM 调用入口（structured → json_parse 回退）"""
        if self._use_structured_output and self._structured_llm is not None:
            try:
                return await self._invoke_structured(prompt)
            except Exception as e:
                logger.warning(
                    f"[StructuredLLMClassifier] structured_output 失败({e})，"
                    "尝试 JSON 解析回退"
                )
        return await self._invoke_with_json_parse(prompt)

    async def classify(
        self,
        message: str,
        context: dict[str, Any] | None = None,
        timeout: float = 8.0,
    ) -> IntentClassificationResult:
        """
        使用 LLM 进行结构化意图分类（带 timeout + fail-soft）

        LLM 失败时返回 classifier_error，而不是让调用方 500。
        """
        if not self.enabled:
            return IntentClassificationResult(
                goals=[], is_confident=False, is_out_of_scope=False,
                classifier_error="LLM classifier not enabled",
            )

        try:
            self._init_llm()
            prompt = _build_nlu_prompt(message, context)
            logger.debug(f"[StructuredLLMClassifier] 发起 LLM 调用，消息长度={len(message)}")

            nlu_output = await asyncio.wait_for(
                self._invoke_llm(prompt),
                timeout=timeout,
            )

            logger.info(
                f"[StructuredLLMClassifier] LLM 完成，"
                f"goals={len(nlu_output.goals)}, "
                f"is_out_of_scope={nlu_output.is_out_of_scope}, "
                f"needs_clarification={nlu_output.needs_clarification}"
            )
            if nlu_output.reasoning:
                logger.debug(f"[StructuredLLMClassifier] reasoning: {nlu_output.reasoning[:100]}")

            return self._convert_to_result(nlu_output)

        except asyncio.TimeoutError:
            logger.warning(f"[StructuredLLMClassifier] LLM 超时 (>{timeout}s)")
            return IntentClassificationResult(
                goals=[], is_confident=False, is_out_of_scope=False,
                classifier_error="timeout",
            )
        except ValidationError as e:
            logger.warning(f"[StructuredLLMClassifier] Schema 校验失败: {e}")
            return IntentClassificationResult(
                goals=[], is_confident=False, is_out_of_scope=False,
                classifier_error="schema_validation_failed",
            )
        except Exception as e:
            logger.error(f"[StructuredLLMClassifier] 异常: {e}", exc_info=True)
            return IntentClassificationResult(
                goals=[], is_confident=False, is_out_of_scope=False,
                classifier_error=str(e)[:200],
            )

    def _convert_to_result(self, output: StructuredNLUOutput) -> IntentClassificationResult:
        """将 StructuredNLUOutput 转换为 IntentClassificationResult"""
        goals = []
        for g in output.goals:
            # 将 LLMEntity 列表转换为 dict（兼容 IntentGoal.entities）
            entities: dict[str, Any] = {e.name: e.value for e in g.entities}
            goals.append(IntentGoal(
                intent=g.intent,
                entities=entities,
                text_span=g.text_span,
                confidence=g.confidence,
            ))

        # 如果 needs_clarification=true，强制 is_confident=False
        if output.needs_clarification:
            return IntentClassificationResult(
                goals=goals,
                is_confident=False,
                is_out_of_scope=output.is_out_of_scope,
                classifier_error=None,
            )

        is_confident = (
            len(goals) > 0
            and not output.is_out_of_scope
            and all((g.confidence or 0.0) >= 0.70 for g in output.goals)
        )

        return IntentClassificationResult(
            goals=goals,
            is_confident=is_confident,
            is_out_of_scope=output.is_out_of_scope,
            classifier_error=None,
        )
