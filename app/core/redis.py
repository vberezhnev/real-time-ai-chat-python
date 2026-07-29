
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio import from_url

from app.config import settings

redis_client: AsyncRedis | None = None


async def get_redis() -> AsyncRedis:
    global redis_client
    if redis_client is None:
        redis_client = await from_url(
            settings.redis_dsn,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=10,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return redis_client


async def close_redis() -> None:
    global redis_client
    if redis_client is not None:
        await redis_client.close()
        redis_client = None
