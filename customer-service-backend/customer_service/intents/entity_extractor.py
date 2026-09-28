from __future__ import annotations

import re
from decimal import Decimal
from typing import Any


ORDER_RE = re.compile(r"\bO\d{8,}\b", re.IGNORECASE)
PRODUCT_RE = re.compile(r"(?:商品|product)[_ -]?(\d{3,})", re.IGNORECASE)
SKU_RE = re.compile(r"\bSKU[\w-]+\b", re.IGNORECASE)
PRICE_RE = re.compile(r"(?:预算|价格|价位)?\s*(\d+(?:\.\d+)?)\s*(?:元|块|以内|左右)?")

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

    for color in COLORS:
        if color in text:
            entities["color"] = color
            break

    for size in SIZES:
        if re.search(rf"(?<![A-Za-z]){re.escape(size)}(?![A-Za-z])", text, re.IGNORECASE):
            entities["size"] = size.upper()
            break

    if match := PRICE_RE.search(text):
        try:
            value = Decimal(match.group(1))
            if any(word in text for word in ["预算", "以内", "不超过", "最高"]):
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
