CLARIFY_QUESTIONS = {
    "intent": "我还不太确定您的具体需求。您是想找商品、查优惠、推荐尺码、查物流，还是办理退换货？",
    "product_id": "你想咨询哪件商品？可以先选择商品卡片，或告诉我商品名称。",
    "order_id": "请告诉我订单号，我再帮你查询。",
    "sku_id": "请告诉我需要处理的颜色和尺码，或选择对应商品卡片。",
    "original_sku_id": "请告诉我原来的颜色和尺码。",
    "exchange_sku_id": "请告诉我想换成哪个颜色或尺码。",
    "reason": "请简单说一下原因。",
}


def clarify_for(missing: list[str]) -> str:
    if not missing:
        return "你可以再具体说一下想处理什么电商问题吗？"
    return CLARIFY_QUESTIONS.get(missing[0], "请补充一下必要信息。")
