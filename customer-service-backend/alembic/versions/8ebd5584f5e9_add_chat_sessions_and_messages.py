"""add_chat_sessions_and_messages

Revision ID: 8ebd5584f5e9
Revises:
Create Date: 2026-09-22 17:23:41.633271

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8ebd5584f5e9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 创建 chat_sessions 表
    op.create_table('chat_sessions',
    sa.Column('id', sa.String(length=64), nullable=False, comment='Session ID (UUID)'),
    sa.Column('user_id', sa.String(length=64), nullable=False, comment='用户 ID'),
    sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
    sa.Column('updated_at', sa.DateTime(), nullable=False, comment='最后更新时间'),
    sa.Column('metadata_json', sa.Text(), nullable=True, comment='Session 元数据 (JSON)'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_user_created', 'chat_sessions', ['user_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_chat_sessions_user_id'), 'chat_sessions', ['user_id'], unique=False)

    # 创建 chat_messages 表
    op.create_table('chat_messages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='消息 ID'),
    sa.Column('session_id', sa.String(length=64), nullable=False, comment='所属 Session ID'),
    sa.Column('role', sa.Enum('USER', 'ASSISTANT', 'SYSTEM', name='messagerole'), nullable=False, comment='消息角色'),
    sa.Column('content', sa.Text(), nullable=False, comment='消息内容'),
    sa.Column('created_at', sa.DateTime(), nullable=False, comment='创建时间'),
    sa.Column('metadata_json', sa.Text(), nullable=True, comment='消息元数据 (JSON)'),
    sa.ForeignKeyConstraint(['session_id'], ['chat_sessions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_session_created', 'chat_messages', ['session_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_chat_messages_session_id'), 'chat_messages', ['session_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # 删除 chat_messages 表
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index('idx_session_created', table_name='chat_messages')
    op.drop_table('chat_messages')

    # 删除 chat_sessions 表
    op.drop_index(op.f('ix_chat_sessions_user_id'), table_name='chat_sessions')
    op.drop_index('idx_user_created', table_name='chat_sessions')
    op.drop_table('chat_sessions')
    op.create_table('logistics_records',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('order_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='关联orders.order_id'),
    sa.Column('logistics_company', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=False, comment='物流公司'),
    sa.Column('tracking_number', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=False, comment='运单号'),
    sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='物流状态'),
    sa.Column('status_desc', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=True, comment='状态描述'),
    sa.Column('updated_at', mysql.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.order_id'], name=op.f('logistics_records_ibfk_1'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_logistics_records_order_id'), 'logistics_records', ['order_id'], unique=False)
    op.create_table('promotions',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('promotion_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='PROMO20260001'),
    sa.Column('product_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='关联商品'),
    sa.Column('promotion_name', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=False, comment='促销名称'),
    sa.Column('promotion_type', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=50), nullable=False, comment='PERCENT_OFF/FIXED_OFF/FULL_REDUCTION/MEMBER_PRICE'),
    sa.Column('threshold_amount', mysql.DECIMAL(precision=10, scale=2), nullable=True, comment='满减门槛'),
    sa.Column('discount_amount', mysql.DECIMAL(precision=10, scale=2), nullable=True, comment='减免金额'),
    sa.Column('discount_rate', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='折扣率'),
    sa.Column('promo_price', mysql.DECIMAL(precision=10, scale=2), nullable=True, comment='会员专享价'),
    sa.Column('member_level', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=True, comment='会员等级限制: ALL/PLUS'),
    sa.Column('start_at', mysql.DATETIME(), nullable=False, comment='开始时间'),
    sa.Column('end_at', mysql.DATETIME(), nullable=False, comment='结束时间'),
    sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='active/scheduled/expired'),
    sa.Column('description', mysql.TEXT(collation='utf8mb4_unicode_ci'), nullable=True, comment='促销描述'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.Column('updated_at', mysql.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], name=op.f('promotions_ibfk_1'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_promotions_status'), 'promotions', ['status'], unique=False)
    op.create_index(op.f('ix_promotions_start_at'), 'promotions', ['start_at'], unique=False)
    op.create_index(op.f('ix_promotions_promotion_id'), 'promotions', ['promotion_id'], unique=True)
    op.create_index(op.f('ix_promotions_product_id'), 'promotions', ['product_id'], unique=False)
    op.create_index(op.f('ix_promotions_end_at'), 'promotions', ['end_at'], unique=False)
    op.create_table('dialogue_states',
    sa.Column('sender_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=False, comment='用户唯一标识'),
    sa.Column('state_json', mysql.TEXT(collation='utf8mb4_unicode_ci'), nullable=False, comment='完整对话状态 JSON'),
    sa.PrimaryKeyConstraint('sender_id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_table('order_items',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('order_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='关联orders.order_id'),
    sa.Column('product_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='商品ID'),
    sa.Column('sku_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='SKU ID'),
    sa.Column('quantity', mysql.INTEGER(), autoincrement=False, nullable=False, comment='数量'),
    sa.Column('price', mysql.DECIMAL(precision=10, scale=2), nullable=False, comment='单价（下单时快照）'),
    sa.ForeignKeyConstraint(['order_id'], ['orders.order_id'], name=op.f('order_items_ibfk_1'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_table('products',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('product_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='商品ID: 15970'),
    sa.Column('brand', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='品牌'),
    sa.Column('product_display_name', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=False, comment='商品展示名称'),
    sa.Column('gender', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=True, comment='性别: 男士/女士/男童/女童'),
    sa.Column('master_category', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='主分类: 服装/鞋靴'),
    sa.Column('sub_category', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='子分类: 上装/下装'),
    sa.Column('type', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='类型: 衬衫/牛仔裤'),
    sa.Column('season', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=True, comment='季节'),
    sa.Column('year', mysql.INTEGER(), autoincrement=False, nullable=True, comment='年份'),
    sa.Column('usage', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='用途: 休闲/正式/运动'),
    sa.Column('material', mysql.TEXT(collation='utf8mb4_unicode_ci'), nullable=True, comment='材质描述'),
    sa.Column('selling_points', mysql.JSON(), nullable=True, comment='卖点JSON数组'),
    sa.Column('size_data', mysql.JSON(), nullable=True, comment='尺码表JSON'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_products_sub_category'), 'products', ['sub_category'], unique=False)
    op.create_index(op.f('ix_products_product_id'), 'products', ['product_id'], unique=True)
    op.create_index(op.f('ix_products_master_category'), 'products', ['master_category'], unique=False)
    op.create_index(op.f('ix_products_brand'), 'products', ['brand'], unique=False)
    op.create_table('exchange_requests',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('request_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='EXG-yyyymmdd-xxxxx'),
    sa.Column('user_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='用户ID'),
    sa.Column('order_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='订单ID'),
    sa.Column('product_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='商品ID'),
    sa.Column('original_sku_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='原SKU ID'),
    sa.Column('exchange_sku_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='目标SKU ID'),
    sa.Column('reason', mysql.TEXT(collation='utf8mb4_unicode_ci'), nullable=False, comment='换货原因'),
    sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='REQUESTED/APPROVED/REJECTED/COMPLETED'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.Column('updated_at', mysql.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.order_id'], name=op.f('exchange_requests_ibfk_1')),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_exchange_requests_user_id'), 'exchange_requests', ['user_id'], unique=False)
    op.create_index(op.f('ix_exchange_requests_status'), 'exchange_requests', ['status'], unique=False)
    op.create_index(op.f('ix_exchange_requests_request_id'), 'exchange_requests', ['request_id'], unique=True)
    op.create_index(op.f('ix_exchange_requests_order_id'), 'exchange_requests', ['order_id'], unique=False)
    op.create_table('product_skus',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('sku_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='SKU15970_01'),
    sa.Column('product_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='关联products.product_id'),
    sa.Column('color', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='颜色'),
    sa.Column('size_code', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=50), nullable=True, comment='尺码代码: S/M/L/40/41'),
    sa.Column('price', mysql.DECIMAL(precision=10, scale=2), nullable=False, comment='价格'),
    sa.Column('stock_status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='有货/缺货'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['product_id'], ['products.product_id'], name=op.f('product_skus_ibfk_1'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_product_skus_sku_id'), 'product_skus', ['sku_id'], unique=True)
    op.create_index(op.f('ix_product_skus_product_id'), 'product_skus', ['product_id'], unique=False)
    op.create_table('orders',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('order_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='O20260913000016'),
    sa.Column('user_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='关联users.user_id'),
    sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='待付款/待发货/运输中/待收货/已完成'),
    sa.Column('status_desc', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=True, comment='状态描述'),
    sa.Column('amount', mysql.DECIMAL(precision=10, scale=2), nullable=False, comment='订单总金额'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.Column('receiver_name', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='收货人姓名'),
    sa.Column('receiver_phone', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=True, comment='收货人电话'),
    sa.Column('receiver_address', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=500), nullable=True, comment='收货地址'),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], name=op.f('orders_ibfk_1')),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_orders_user_id'), 'orders', ['user_id'], unique=False)
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)
    op.create_index(op.f('ix_orders_order_id'), 'orders', ['order_id'], unique=True)
    op.create_table('user_measurements',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('user_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='关联users.user_id'),
    sa.Column('height_cm', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='身高(cm)'),
    sa.Column('weight_kg', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='体重(kg)'),
    sa.Column('bust_cm', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='胸围(cm)'),
    sa.Column('waist_cm', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='腰围(cm)'),
    sa.Column('hip_cm', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='臀围(cm)'),
    sa.Column('shoulder_cm', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='肩宽(cm)'),
    sa.Column('foot_length_cm', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='脚长(cm)'),
    sa.Column('foot_width_cm', mysql.DECIMAL(precision=5, scale=2), nullable=True, comment='脚宽(cm)'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.Column('updated_at', mysql.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], name=op.f('user_measurements_ibfk_1'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('user_id'), 'user_measurements', ['user_id'], unique=True)
    op.create_table('users',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('user_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='业务ID: U0001'),
    sa.Column('username', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=False, comment='用户名'),
    sa.Column('nickname', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=False, comment='昵称'),
    sa.Column('phone_number', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=True, comment='手机号'),
    sa.Column('email', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=True, comment='邮箱'),
    sa.Column('level', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='会员等级: PLUS/普通会员'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_index(op.f('ix_users_user_id'), 'users', ['user_id'], unique=True)
    op.create_table('logistics_traces',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('logistics_record_id', mysql.INTEGER(), autoincrement=False, nullable=False, comment='关联logistics_records.id'),
    sa.Column('trace_time', mysql.DATETIME(), nullable=False, comment='轨迹时间'),
    sa.Column('trace_desc', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=500), nullable=False, comment='轨迹描述'),
    sa.ForeignKeyConstraint(['logistics_record_id'], ['logistics_records.id'], name=op.f('logistics_traces_ibfk_1'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_logistics_traces_logistics_record_id'), 'logistics_traces', ['logistics_record_id'], unique=False)
    op.create_table('shipping_urge_requests',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('request_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='URG-yyyymmdd-xxxxx'),
    sa.Column('user_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='用户ID'),
    sa.Column('order_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='订单ID'),
    sa.Column('reason_code', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='NORMAL_URGE/URGENT'),
    sa.Column('reason_detail', mysql.TEXT(collation='utf8mb4_unicode_ci'), nullable=True, comment='详细原因'),
    sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='SUBMITTED/HANDLED'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['order_id'], ['orders.order_id'], name=op.f('shipping_urge_requests_ibfk_1')),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('ix_shipping_urge_requests_user_id'), 'shipping_urge_requests', ['user_id'], unique=False)
    op.create_index(op.f('ix_shipping_urge_requests_status'), 'shipping_urge_requests', ['status'], unique=False)
    op.create_index(op.f('ix_shipping_urge_requests_request_id'), 'shipping_urge_requests', ['request_id'], unique=True)
    op.create_index(op.f('ix_shipping_urge_requests_order_id'), 'shipping_urge_requests', ['order_id'], unique=False)
    op.create_table('user_auth',
    sa.Column('id', mysql.INTEGER(), autoincrement=True, nullable=False),
    sa.Column('user_id', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=64), nullable=False, comment='关联users.user_id'),
    sa.Column('username', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=100), nullable=False, comment='登录用户名'),
    sa.Column('password_hash', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=255), nullable=False, comment='Argon2id加密密码'),
    sa.Column('status', mysql.VARCHAR(collation='utf8mb4_unicode_ci', length=32), nullable=False, comment='active/locked'),
    sa.Column('failed_login_count', mysql.INTEGER(), autoincrement=False, nullable=False, comment='失败登录次数'),
    sa.Column('locked_until', mysql.DATETIME(), nullable=True, comment='锁定截止时间'),
    sa.Column('last_login_at', mysql.DATETIME(), nullable=True, comment='最后登录时间'),
    sa.Column('created_at', mysql.DATETIME(), nullable=False),
    sa.Column('updated_at', mysql.DATETIME(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], name=op.f('user_auth_ibfk_1'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    mysql_collate='utf8mb4_unicode_ci',
    mysql_default_charset='utf8mb4',
    mysql_engine='InnoDB'
    )
    op.create_index(op.f('user_id'), 'user_auth', ['user_id'], unique=True)
    op.create_index(op.f('ix_user_auth_username'), 'user_auth', ['username'], unique=True)
    op.drop_index(op.f('ix_chat_messages_session_id'), table_name='chat_messages')
    op.drop_index('idx_session_created', table_name='chat_messages')
    op.drop_table('chat_messages')
    op.drop_index(op.f('ix_chat_sessions_user_id'), table_name='chat_sessions')
    op.drop_index('idx_user_created', table_name='chat_sessions')
    op.drop_table('chat_sessions')
    # ### end Alembic commands ###
