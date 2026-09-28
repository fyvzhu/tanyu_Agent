from sqlalchemy.ext.asyncio import create_async_engine, AsyncEngine, async_sessionmaker, AsyncSession
from customer_service.config.config import settings

engine: AsyncEngine | None = None
async_session: async_sessionmaker[AsyncSession] | None = None


def init_db_engine():
    global engine, async_session
    # 1. 创建异步引擎
    engine = create_async_engine(
        settings.agent_async_database_url,
        echo=False)  # 生产环境关闭 SQL 日志

    # 2. 创建异步session工厂
    async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_async_session():
    """
    获取异步数据库会话（用于依赖注入）
    """
    if async_session is None:
        init_db_engine()

    async with async_session() as session:
        yield session


async def close_db_engine():
    if engine is not None:
        await engine.dispose()
