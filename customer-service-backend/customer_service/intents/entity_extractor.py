from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from loguru import logger

# NLU_HYBRID_REFACTOR：导入 EntityCandidate，实体输出需带 source/confidence
# entity_extractor 同时保留向后兼容的 extract_entities(dict) 接口
from customer_service.intents.models import EntityCandidate


ORDER_RE = re.compile(r"\bO\d{8,}\b", re.IGNORECASE)
PRODUCT_RE = re.compile(r"(?:商品|product)[_ -]?(\d{3,})", re.IGNORECASE)
SKU_RE = re.compile(r"\bSKU[\w-]+\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:预算|价格|价位)?\s*(\d+(?:\.\d+)?)\s*(?:元|块|以内|左右)?")
# 问题5修复：裸数字正则，用于在促销等场景识别商品ID
BARE_NUMBER_RE = re.compile(r"\b(\d{4,6})\b")  # 4-6位数字

COLORS = ["黑色", "白色", "藏青色", "蓝色", "红色", "灰色", "米色", "绿色", "粉色"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]

# P0-3修复：动态加载品牌列表（从products.csv）
# 启动时加载，避免硬编码
_BRAND_SET: set[str] = set()
_BRAND_PATTERNS: list[tuple[str, re.Pattern]] = []

def _load_brands_from_csv():
    """
    P0-3修复：从products.csv动态加载品牌列表

    优点：
    1. 避免硬编码
    2. 自动覆盖所有数据中的品牌
    3. 易于维护
    """
    global _BRAND_SET, _BRAND_PATTERNS

    try:
        import pandas as pd
        from pathlib import Path

        # 查找products.csv路径
        csv_path = Path(__file__).parent.parent.parent.parent / "data" / "products.csv"

        if csv_path.exists():
            df = pd.read_csv(csv_path)
            _BRAND_SET = set(df["brand"].dropna().unique())

            # P0-3修复：编译品牌正则（支持中文+英文混合场景）
            # 关键：品牌前后可以是任意非字母数字字符（包括中文、空格、标点）
            if _BRAND_SET:
                _BRAND_PATTERNS = []
                for brand in sorted(_BRAND_SET, key=len, reverse=True):
                    # 使用简单匹配：品牌名直接出现即可，不强制边界
                    # 这样"我想买Turtle的"可以匹配到Turtle
                    pattern = re.compile(re.escape(brand), re.IGNORECASE)
                    _BRAND_PATTERNS.append((brand, pattern))

                logger.info(f"[EntityExtractor] 成功加载 {len(_BRAND_SET)} 个品牌: {sorted(_BRAND_SET)}")
            else:
                logger.warning("[EntityExtractor] products.csv中未找到品牌数据")
        else:
            logger.warning(f"[EntityExtractor] 未找到products.csv: {csv_path}")
            # 回退到最小品牌集
            _BRAND_SET = {"Puma", "ADIDAS", "Nike"}
            _BRAND_PATTERNS = [
                (brand, re.compile(re.escape(brand), re.IGNORECASE))
                for brand in sorted(_BRAND_SET, key=len, reverse=True)
            ]

    except Exception as e:
        logger.error(f"[EntityExtractor] 加载品牌列表失败: {e}", exc_info=True)
        # 回退到最小品牌集
        _BRAND_SET = {"Puma", "ADIDAS", "Nike"}
        _BRAND_PATTERNS = [
            (brand, re.compile(re.escape(brand), re.IGNORECASE))
            for brand in sorted(_BRAND_SET, key=len, reverse=True)
        ]

# 模块加载时自动初始化
_load_brands_from_csv()

# NLU_HYBRID_REFACTOR Step 4：商品品类词典（用于 product_name 粗提取）
_PRODUCT_CATEGORY_RE = re.compile(
    r"(?:"
    r"外套|夹克|衬衫|T恤|t恤|连衣裙|裙子|裤子|牛仔裤|运动鞋|鞋子|球鞋|"
    r"卫衣|毛衣|羽绒服|风衣|大衣|西装|polo衫|内衣|睡衣|"
    r"背包|手包|腰包|帽子|围巾|手套|腰带|"
    r"jacket|shirt|jeans|sneakers|shoes|dress|coat|hoodie|pants"
    r")"
    r"[\u4e00-\u9fa5A-Za-z]*",  # 允许后缀（如"运动外套"）
    re.IGNORECASE,
)

# 不同实体的规则置信度
_RULE_CONFIDENCE = {
    "product_id": 0.95,
    "order_id": 0.97,
    "sku_id": 0.95,
    "price": 0.92,
    "max_price": 0.92,
    "size": 0.90,
    "color": 0.88,
    "brand": 0.88,
    "product_name": 0.75,
    "height_cm": 0.90,
    "weight_kg": 0.90,
    "waist_cm": 0.90,
    "bust_cm": 0.90,
    "hip_cm": 0.90,
    "fit_preference": 0.85,
}


def extract_entities(message: str) -> dict[str, Any]:
    """
    规则实体抽取（向后兼容接口）

    NLU_HYBRID_REFACTOR：这个函数继续返回 dict[str, Any]，
    供旧代码直接使用（entities["color"] 等）。
    新代码应使用 extract_entities_with_candidates() 获取带 source/confidence 的格式。
    """
    candidates = extract_entities_with_candidates(message)
    return {name: cand.value for name, cand in candidates.items()}


def extract_entities_with_candidates(message: str) -> dict[str, EntityCandidate]:
    """
    规则实体抽取（NLU_HYBRID_REFACTOR 新接口）

    返回 dict[str, EntityCandidate]，每个实体带：
    - source = "rule"
    - confidence（由 _RULE_CONFIDENCE 决定）
    - text_span（原文片段）
    - validated = False（需业务验证后设为 True）

    所有规则实体优先级高于 LLM 实体（见 entity_fusion.py）。
    """
    entities: dict[str, EntityCandidate] = {}
    text = message.strip()

    def _add(name: str, value: Any, text_span: str | None = None, validated: bool = False):
        conf = _RULE_CONFIDENCE.get(name, 0.85)
        entities[name] = EntityCandidate(
            name=name,
            value=value,
            source="rule",
            confidence=conf,
            text_span=text_span or str(value),
            validated=validated,
        )

    # ---- order_id ----
    if match := ORDER_RE.search(text):
        _add("order_id", match.group(0).upper(), match.group(0))

    # ---- product_id（先精确匹配，再策略补充）----
    if match := PRODUCT_RE.search(text):
        _add("product_id", match.group(1), match.group(0))
    else:
        pid_span = None
        pid_val = None

        # 策略1：指示词 + 数字（"那29570呢？"）
        if m := re.search(r"(?:那|这|这个|那个)\s*(\d{4,6})", text):
            pid_val, pid_span = m.group(1), m.group(0)
        # 策略2：纯数字 + 疑问词
        elif re.match(r"^\s*(\d{4,6})\s*(?:呢|吗|么)\s*[？?]*\s*$", text):
            if m := re.search(r"(\d{4,6})", text):
                pid_val, pid_span = m.group(1), m.group(0)
        # 策略3：数字 + "有" + 商品相关词
        elif re.search(r"(\d{4,6})\s*有\s*(?:优惠|促销|活动|折扣)", text):
            if m := re.search(r"(\d{4,6})", text):
                pid_val, pid_span = m.group(1), m.group(0)
        # 策略4：商品相关词 + 数字
        elif m := re.search(r"(?:推荐|查询|搜索|找)\s*(\d{4,6})", text):
            pid_val, pid_span = m.group(1), m.group(0)
        # 策略5：有商品上下文时的裸数字
        else:
            has_ctx = any(w in text for w in ["优惠", "促销", "活动", "折扣", "推荐", "尺码"])
            if has_ctx and (m := BARE_NUMBER_RE.search(text)):
                end_pos = m.end()
                next_chars = text[end_pos:end_pos + 2] if end_pos < len(text) else ""
                if not any(u in next_chars for u in ["元", "块"]):
                    pid_val, pid_span = m.group(1), m.group(0)

        if pid_val:
            _add("product_id", pid_val, pid_span)

    # ---- sku_id ----
    if match := SKU_RE.search(text):
        _add("sku_id", match.group(0).upper(), match.group(0))

    # ---- color ----
    for color in COLORS:
        if color in text:
            _add("color", color, color)
            break

    # ---- size ----
    for size in SIZES:
        if re.search(rf"(?<![A-Za-z]){re.escape(size)}(?![A-Za-z])", text, re.IGNORECASE):
            _add("size", size.upper(), size)
            break

    # ---- price / max_price ----
    if match := PRICE_RE.search(text):
        try:
            value = Decimal(match.group(1))
            matched_num = match.group(1)
            # 已识别为 product_id 或 order_id（订单号包含该数字序列）的不作为价格
            is_already_entity = (
                (entities.get("product_id") and entities["product_id"].value == matched_num)
                or (entities.get("order_id") and matched_num in entities["order_id"].value)
            )
            if is_already_entity:
                pass  # 跳过，已作为业务实体
            elif any(word in text for word in ["预算", "以内", "不超过", "最高"]):
                _add("max_price", str(value), match.group(0))
            else:
                _add("price", str(value), match.group(0))
        except Exception:
            pass

    # ---- 身体参数 ----
    for name, pattern in {
        "height_cm": r"(\d{2,3})\s*(?:cm|厘米|身高)",
        "weight_kg": r"(\d{2,3})\s*(?:kg|公斤|斤|体重)",
        "waist_cm": r"(?:腰围|腰)\s*(\d{2,3})",
        "bust_cm":  r"(?:胸围|胸)\s*(\d{2,3})",
        "hip_cm":   r"(?:臀围|臀)\s*(\d{2,3})",
    }.items():
        if match := re.search(pattern, text, re.IGNORECASE):
            _add(name, int(match.group(1)), match.group(0))

    # ---- fit_preference ----
    if "宽松" in text:
        _add("fit_preference", "loose", "宽松")
    elif "修身" in text:
        _add("fit_preference", "slim", "修身")
    elif "合身" in text:
        _add("fit_preference", "regular", "合身")

    # ---- NLU_HYBRID_REFACTOR Step 4：brand 提取 ----
    for brand_name, pattern in _BRAND_PATTERNS:
        if m := pattern.search(text):
            _add("brand", brand_name, m.group(0), validated=True)
            break  # 匹配到第一个品牌即停止

    # ---- NLU_HYBRID_REFACTOR Step 4：product_name 粗提取 ----
    # 规则只能提取品类词，精确商品名需 LLM + ProductReferenceResolver
    if not entities.get("product_id"):  # 有精确 ID 就不再推断商品名
        if m := _PRODUCT_CATEGORY_RE.search(text):
            product_name_val = m.group(0).strip()
            if len(product_name_val) >= 2:
                _add("product_name", product_name_val, product_name_val)

    return entities
