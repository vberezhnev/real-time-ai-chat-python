from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.uow import UnitOfWork

_engine = None
_async_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.db_dsn,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
            connect_args={
                "timeout": 5,
                "command_timeout": 10,
            },
        )
    return _engine


def get_session_factory():
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)
    return _async_session_factory


async def get_session() -> AsyncSession:
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def get_uow() -> UnitOfWork:
    factory = get_session_factory()
    async with factory() as session:
        yield UnitOfWork(session)


async def dispose_engine():
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
