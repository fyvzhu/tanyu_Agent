"""create product_index_manifest table

Revision ID: b9f3c7d1e4a2
Revises: 8ebd5584f5e9
Create Date: 2026-09-22 21:58:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b9f3c7d1e4a2'
down_revision: Union[str, Sequence[str], None] = '8ebd5584f5e9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级数据库 schema - 创建商品索引清单表"""
    op.create_table(
        'product_index_manifest',
        sa.Column('product_id', sa.String(length=50), nullable=False, comment='商品 ID'),
        sa.Column('source_hash', sa.String(length=64), nullable=False, comment='商品原始数据的 SHA256 哈希'),
        sa.Column('index_signature', sa.String(length=128), nullable=False, comment='索引配置签名（包含 embedding model, chunker version 等）'),
        sa.Column('chunk_count', sa.Integer(), nullable=False, default=0, comment='该商品的 chunk 数量'),
        sa.Column('qdrant_sync_status', sa.String(length=20), nullable=False, default='pending', comment='Qdrant 同步状态: pending/synced/failed'),
        sa.Column('es_sync_status', sa.String(length=20), nullable=False, default='pending', comment='Elasticsearch 同步状态: pending/synced/failed'),
        sa.Column('indexed_at', sa.DateTime(), nullable=False, comment='索引时间'),
        sa.Column('last_error', sa.Text(), nullable=True, comment='最后一次同步错误信息'),
        sa.PrimaryKeyConstraint('product_id'),
        comment='商品索引清单 - 记录商品索引状态和同步信息'
    )
    
    # 创建索引以优化查询
    op.create_index('idx_qdrant_sync_status', 'product_index_manifest', ['qdrant_sync_status'])
    op.create_index('idx_es_sync_status', 'product_index_manifest', ['es_sync_status'])
    op.create_index('idx_indexed_at', 'product_index_manifest', ['indexed_at'])


def downgrade() -> None:
    """降级数据库 schema - 删除商品索引清单表"""
    op.drop_index('idx_indexed_at', table_name='product_index_manifest')
    op.drop_index('idx_es_sync_status', table_name='product_index_manifest')
    op.drop_index('idx_qdrant_sync_status', table_name='product_index_manifest')
    op.drop_table('product_index_manifest')
