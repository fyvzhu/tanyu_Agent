"""
数据迁移脚本：统一库存状态和促销类型枚举值

将数据库中的旧枚举值迁移到新的标准值：
- 库存状态: "有货" -> "in_stock", "缺货" -> "out_of_stock"
- 促销类型: "PERCENT_OFF" -> "percentage_discount", 等等
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 枚举映射
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


def migrate_stock_status(session):
    """迁移库存状态"""
    print("开始迁移库存状态...")
    
    # 检查当前的不同取值
    result = session.execute(text("SELECT DISTINCT stock_status FROM product_skus"))
    current_values = [row[0] for row in result]
    print(f"当前库存状态值: {current_values}")
    
    # 统计每种状态的数量
    for old_value, new_value in STOCK_STATUS_MAP.items():
        result = session.execute(
            text("SELECT COUNT(*) FROM product_skus WHERE stock_status = :old_value"),
            {"old_value": old_value}
        )
        count = result.scalar()
        if count > 0:
            print(f"  将 {count} 条 '{old_value}' 更新为 '{new_value}'")
            session.execute(
                text("UPDATE product_skus SET stock_status = :new_value WHERE stock_status = :old_value"),
                {"old_value": old_value, "new_value": new_value}
            )
    
    session.commit()
    
    # 验证迁移结果
    result = session.execute(text("SELECT DISTINCT stock_status FROM product_skus"))
    new_values = [row[0] for row in result]
    print(f"迁移后库存状态值: {new_values}")
    
    # 检查是否有未知值
    expected_values = set(STOCK_STATUS_MAP.values())
    unknown_values = set(new_values) - expected_values
    if unknown_values:
        print(f"⚠️  警告：发现未知的库存状态值: {unknown_values}")
        return False
    
    print("✅ 库存状态迁移完成")
    return True


def migrate_promotion_type(session):
    """迁移促销类型"""
    print("\n开始迁移促销类型...")
    
    # 检查当前的不同取值
    result = session.execute(text("SELECT DISTINCT promotion_type FROM promotions"))
    current_values = [row[0] for row in result]
    print(f"当前促销类型值: {current_values}")
    
    # 统计每种类型的数量
    for old_value, new_value in PROMOTION_TYPE_MAP.items():
        result = session.execute(
            text("SELECT COUNT(*) FROM promotions WHERE promotion_type = :old_value"),
            {"old_value": old_value}
        )
        count = result.scalar()
        if count > 0:
            print(f"  将 {count} 条 '{old_value}' 更新为 '{new_value}'")
            session.execute(
                text("UPDATE promotions SET promotion_type = :new_value WHERE promotion_type = :old_value"),
                {"old_value": old_value, "new_value": new_value}
            )
    
    session.commit()
    
    # 验证迁移结果
    result = session.execute(text("SELECT DISTINCT promotion_type FROM promotions"))
    new_values = [row[0] for row in result]
    print(f"迁移后促销类型值: {new_values}")
    
    # 检查是否有未知值
    expected_values = set(PROMOTION_TYPE_MAP.values())
    unknown_values = set(new_values) - expected_values
    if unknown_values:
        print(f"⚠️  警告：发现未知的促销类型值: {unknown_values}")
        return False
    
    print("✅ 促销类型迁移完成")
    return True


def main():
    """执行迁移"""
    print("=" * 60)
    print("数据库枚举值迁移脚本")
    print("=" * 60)

    # 创建同步数据库连接
    database_url = settings.database_url.replace("mysql+aiomysql://", "mysql+pymysql://")
    engine = create_engine(database_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # 迁移库存状态
        stock_success = migrate_stock_status(db)

        # 迁移促销类型
        promotion_success = migrate_promotion_type(db)

        if stock_success and promotion_success:
            print("\n" + "=" * 60)
            print("✅ 所有迁移成功完成！")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("⚠️  迁移完成，但存在警告，请检查上述输出")
            print("=" * 60)
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
