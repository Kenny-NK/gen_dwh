"""Redis connection module (T033)."""

import redis.asyncio as aioredis

from src.core.config import settings

redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> aioredis.Redis:
    return redis_client
