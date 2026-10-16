from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from secondbrain.config.settings import settings

# database_url example: postgresql+asyncpg://user:password@localhost:5432/secondbrain
engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
    # timestamptz values are returned in Nepal time (asyncpg syntax)
    connect_args={"server_settings": {"timezone": "Asia/Kathmandu"}},
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session