"""
数据导入脚本 - 完整版
从CSV文件批量导入数据到MySQL数据库
"""
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core import logger, hash_password
from app.core.config import settings
from app.database import Base
from app.models import (
    User, UserAuth, Product, ProductSKU, Promotion,
    Order, OrderItem, LogisticsRecord, LogisticsTrace
)

DATA_DIR = Path(__file__).parent.parent.parent / "data"

# 枚举值映射（CSV -> 数据库）
STOCK_STATUS_MAP = {
    "有货": "in_stock",
    "缺货": "out_of_stock"
}

PROMOTION_TYPE_MAP = {
    "PERCENT_OFF": "percentage_discount",
    "FIXED_OFF": "fixed_discount",
    "FULL_REDUCTION": "threshold_discount",
    "MEMBER_PRICE": "member_price"
}


def get_sync_database_url() -> str:
    """Return a sync SQLAlchemy URL for the import script."""
    return settings.database_url.replace("mysql+aiomysql://", "mysql+pymysql://")


def safe_value(value):
    """将 pandas 的 nan 转换为 None（数据库 NULL）"""
    if pd.isna(value):
        return None
    return value


def init_database():
    """初始化数据库"""
    logger.info("初始化数据库...")
    engine = create_engine(get_sync_database_url(), echo=False)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    logger.success("数据库表创建成功")
    return engine


def import_all_data(session):
    """导入所有数据"""
    # 1. 用户
    logger.info("导入用户...")
    df = pd.read_csv(DATA_DIR / "users.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        user = User(
            user_id=row["user_id"], username=row["username"], nickname=row["nickname"],
            phone_number=row.get("phone_number"), email=row.get("email"),
            level=row["level"], created_at=pd.to_datetime(row["created_at"])
        )
        session.add(user)
        if "password" in row and pd.notna(row["password"]):
            auth = UserAuth(
                user_id=row["user_id"], username=row["username"],
                password_hash=hash_password(str(row["password"])),
                status="active", created_at=datetime.now(), updated_at=datetime.now()
            )
            session.add(auth)
    session.commit()
    logger.success("用户导入完成")
    
    # 2. 商品
    logger.info("导入商品...")
    df = pd.read_csv(DATA_DIR / "products.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        product = Product(
            product_id=str(row["product_id"]), brand=row.get("brand"),
            product_display_name=row["product_display_name"],
            gender=row.get("gender"), master_category=row.get("master_category"),
            sub_category=row.get("sub_category"), type=row.get("type"),
            season=row.get("season"), year=row.get("year"), usage=row.get("usage"),
            material=row.get("material"),
            selling_points=json.loads(row["selling_points"]) if pd.notna(row.get("selling_points")) else None,
            size_data=json.loads(row["size"]) if pd.notna(row.get("size")) else None,
            created_at=datetime.now()
        )
        session.add(product)
    session.commit()
    logger.success("商品导入完成")
    
    # 3. SKU
    logger.info("导入SKU...")
    df = pd.read_csv(DATA_DIR / "product_skus.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        # 转换库存状态枚举值
        stock_status = row["stock_status"]
        if stock_status in STOCK_STATUS_MAP:
            stock_status = STOCK_STATUS_MAP[stock_status]
        elif stock_status not in ["in_stock", "out_of_stock"]:
            logger.warning(f"未知的库存状态值: {stock_status}，跳过该SKU")
            continue

        sku = ProductSKU(
            sku_id=row["sku_id"], product_id=str(row["product_id"]),
            color=row.get("color"), size_code=row.get("size_code"),
            price=float(row["price"]), stock_status=stock_status,
            created_at=datetime.now()
        )
        session.add(sku)
    session.commit()
    logger.success("SKU导入完成")
    
    # 4. 促销
    logger.info("导入促销...")
    df = pd.read_csv(DATA_DIR / "promotions.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        # 转换促销类型枚举值
        promotion_type = row["promotion_type"]
        if promotion_type in PROMOTION_TYPE_MAP:
            promotion_type = PROMOTION_TYPE_MAP[promotion_type]
        elif promotion_type not in ["percentage_discount", "fixed_discount", "threshold_discount", "member_price"]:
            logger.warning(f"未知的促销类型值: {promotion_type}，跳过该促销")
            continue

        promo = Promotion(
            promotion_id=row["promotion_id"], product_id=str(row["product_id"]),
            promotion_name=row["promotion_name"], promotion_type=promotion_type,
            threshold_amount=safe_value(row.get("threshold_amount")),
            discount_amount=safe_value(row.get("discount_amount")),
            discount_rate=safe_value(row.get("discount_rate")),
            promo_price=safe_value(row.get("promo_price")),
            member_level=row.get("member_level"),
            start_at=pd.to_datetime(row["start_at"]), end_at=pd.to_datetime(row["end_at"]),
            status=row["status"], description=row.get("description"),
            created_at=pd.to_datetime(row["created_at"]), updated_at=pd.to_datetime(row["updated_at"])
        )
        session.add(promo)
    session.commit()
    logger.success("促销导入完成")
    
    # 5. 订单
    logger.info("导入订单...")
    df = pd.read_csv(DATA_DIR / "orders.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        order = Order(
            order_id=row["order_id"], user_id=row["user_id"],
            status=row["status"], status_desc=row.get("status_desc"),
            amount=float(row["amount"]), created_at=pd.to_datetime(row["created_at"]),
            receiver_name=row.get("receiver_name"), receiver_phone=row.get("receiver_phone"),
            receiver_address=row.get("receiver_address")
        )
        session.add(order)
    session.commit()
    
    # 6. 订单明细
    df = pd.read_csv(DATA_DIR / "order_item.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        item = OrderItem(
            order_id=row["order_id"], product_id=str(row["product_id"]),
            sku_id=row["sku_id"], quantity=int(row["quantity"]), price=float(row["price"])
        )
        session.add(item)
    session.commit()
    logger.success("订单导入完成")
    
    # 7. 物流
    logger.info("导入物流...")
    df = pd.read_csv(DATA_DIR / "logistics_records.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        record = LogisticsRecord(
            order_id=row["order_id"], logistics_company=row["logistics_company"],
            tracking_number=row["tracking_number"], status=row["status"],
            status_desc=row.get("status_desc"), updated_at=pd.to_datetime(row["updated_at"])
        )
        session.add(record)
    session.commit()
    
    # 8. 物流轨迹
    records = session.query(LogisticsRecord).all()
    record_map = {r.order_id: r.id for r in records}
    df = pd.read_csv(DATA_DIR / "logistics_traces.csv", encoding="utf-8-sig")
    for _, row in df.iterrows():
        if row["order_id"] in record_map:
            trace = LogisticsTrace(
                logistics_record_id=record_map[row["order_id"]],
                trace_time=pd.to_datetime(row["trace_time"]),
                trace_desc=row["trace_desc"]
            )
            session.add(trace)
    session.commit()
    logger.success("物流导入完成")


def main():
    logger.info("=" * 60)
    logger.info("开始导入电商数据")
    logger.info("=" * 60)
    try:
        engine = init_database()
        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()
        import_all_data(session)
        logger.success("所有数据导入完成")
    except Exception as e:
        logger.error(f"数据导入失败: {e}")
        logger.exception(e)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
