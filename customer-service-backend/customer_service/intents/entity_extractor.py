from __future__ import annotations

import re
from decimal import Decimal
from typing import Any


ORDER_RE = re.compile(r"\bO\d{8,}\b", re.IGNORECASE)
PRODUCT_RE = re.compile(r"(?:商品|product)[_ -]?(\d{3,})", re.IGNORECASE)
SKU_RE = re.compile(r"\bSKU[\w-]+\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:预算|价格|价位)?\s*(\d+(?:\.\d+)?)\s*(?:元|块|以内|左右)?")
# 问题5修复：裸数字正则，用于在促销等场景识别商品ID
BARE_NUMBER_RE = re.compile(r"\b(\d{4,6})\b")  # 4-6位数字

COLORS = ["黑色", "白色", "藏青色", "蓝色", "红色", "灰色", "米色", "绿色", "粉色"]
SIZES = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]


def extract_entities(message: str) -> dict[str, Any]:
    entities: dict[str, Any] = {}
    text = message.strip()

    if match := ORDER_RE.search(text):
        entities["order_id"] = match.group(0).upper()
    if match := PRODUCT_RE.search(text):
        entities["product_id"] = match.group(1)
    if match := SKU_RE.search(text):
        entities["sku_id"] = match.group(0).upper()

    # P2修复（参考修改建议2）：增强商品ID提取，支持省略式追问
    # "那29570呢？"、"15970呢？" 等应该提取商品ID
    if "product_id" not in entities:
        # 策略1：省略式追问模式（指示词 + 数字）
        # "那29570呢？"、"这个15970吗？"、"那29570有什么促销吗？"
        elliptical_product_pattern = r"(?:那|这|这个|那个)\s*(\d{4,6})"
        if match := re.search(elliptical_product_pattern, text):
            entities["product_id"] = match.group(1)
        # 策略2：纯数字 + 疑问词（"15970呢？"）
        elif re.match(r"^\s*(\d{4,6})\s*(?:呢|吗|么)\s*[？?]*\s*$", text):
            match = re.search(r"(\d{4,6})", text)
            if match:
                entities["product_id"] = match.group(1)
        # 策略3：数字 + "有" + 商品相关词（"29570有优惠吗"）
        elif re.search(r"(\d{4,6})\s*有\s*(?:优惠|促销|活动|折扣)", text):
            match = re.search(r"(\d{4,6})", text)
            if match:
                entities["product_id"] = match.group(1)
        # 策略4：商品相关词 + 数字（"推荐29570"）
        elif re.search(r"(?:推荐|查询|搜索|找)\s*(\d{4,6})", text):
            match = re.search(r"(?:推荐|查询|搜索|找)\s*(\d{4,6})", text)
            if match:
                entities["product_id"] = match.group(1)
        # 策略5：有商品相关关键词时，提取裸数字
        else:
            has_product_context = any(word in text for word in ["优惠", "促销", "活动", "折扣", "推荐", "尺码"])
            if has_product_context:
                # 查找裸数字
                if match := BARE_NUMBER_RE.search(text):
                    number = match.group(1)
                    # 确保数字后面不是价格单位
                    end_pos = match.end()
                    next_chars = text[end_pos:end_pos+2] if end_pos < len(text) else ""
                    if not any(unit in next_chars for unit in ["元", "块"]):
                        entities["product_id"] = number

    for color in COLORS:
        if color in text:
            entities["color"] = color
            break

    for size in SIZES:
        if re.search(rf"(?<![A-Za-z]){re.escape(size)}(?![A-Za-z])", text, re.IGNORECASE):
            entities["size"] = size.upper()
            break

    # P2修复：价格提取时，避免误捕获已识别为商品ID的数字
    if match := PRICE_RE.search(text):
        try:
            value = Decimal(match.group(1))
            # 如果这个数字已经被识别为product_id，跳过价格提取
            if entities.get("product_id") == match.group(1):
                pass  # 已经是商品ID，不作为价格
            elif any(word in text for word in ["预算", "以内", "不超过", "最高"]):
                entities["max_price"] = str(value)
            else:
                entities["price"] = str(value)
        except Exception:
            pass

    for key, pattern in {
        "height_cm": r"(\d{2,3})\s*(?:cm|厘米|身高)",
        "weight_kg": r"(\d{2,3})\s*(?:kg|公斤|斤|体重)",
        "waist_cm": r"(?:腰围|腰)\s*(\d{2,3})",
        "bust_cm": r"(?:胸围|胸)\s*(\d{2,3})",
        "hip_cm": r"(?:臀围|臀)\s*(\d{2,3})",
    }.items():
        if match := re.search(pattern, text, re.IGNORECASE):
            entities[key] = int(match.group(1))

    if "宽松" in text:
        entities["fit_preference"] = "loose"
    elif "修身" in text:
        entities["fit_preference"] = "slim"
    elif "合身" in text:
        entities["fit_preference"] = "regular"

    return entities
