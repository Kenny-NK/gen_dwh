"""API rate limiting (T121)."""

import re
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings
from src.core.redis import redis_client

# Fallback in-memory rate limiter when Redis is unavailable.
_requests: dict[str, list[float]] = defaultdict(list)
_UUID_RE = re.compile(
    r"/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?=/|$)"
)
_INT_RE = re.compile(r"/\d+(?=/|$)")

_RATE_LIMIT_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call("ZREMRANGEBYSCORE", key, 0, now - window)
local count = redis.call("ZCARD", key)
if count >= limit then
  local oldest = redis.call("ZRANGE", key, 0, 0, "WITHSCORES")
  local retry_after = 1
  if oldest[2] ~= nil then
    retry_after = math.ceil((window - (now - tonumber(oldest[2]))) / 1000)
    if retry_after < 1 then
      retry_after = 1
    end
  end
  return {0, retry_after}
end

redis.call("ZADD", key, now, member)
redis.call("EXPIRE", key, math.ceil(window / 1000))
return {1, 0}
"""


def _normalize_path(path: str) -> str:
    value = _UUID_RE.sub("/:id", path)
    return _INT_RE.sub("/:id", value)


def _too_many_requests_response(retry_after: int) -> Response:
    return Response(
        content=(
            '{"detail":"Слишком много запросов. Подождите и повторите позже.",'
            f'"retry_after_seconds":{retry_after}'
            "}"
        ),
        status_code=429,
        media_type="application/json",
        headers={"Retry-After": str(retry_after)},
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if settings.rate_limit_per_minute <= 0:
            return await call_next(request)

        if request.method == "OPTIONS":
            return await call_next(request)

        path = _normalize_path(request.url.path)
        if path.startswith("/health") or path.startswith("/metrics"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        bucket = f"rate_limit:{client_ip}:{request.method}:{path}"
        now = time.time()
        window = settings.rate_limit_window_seconds

        # Primary limiter in Redis to work across workers/instances.
        try:
            now_ms = int(now * 1000)
            result = await redis_client.eval(
                _RATE_LIMIT_LUA,
                1,
                bucket,
                now_ms,
                window * 1000,
                settings.rate_limit_per_minute,
                f"{now_ms}:{uuid4().hex}",
            )
            allowed = int(result[0])
            retry_after = int(result[1])
            if not allowed:
                return _too_many_requests_response(retry_after)
            return await call_next(request)
        except Exception:
            # Fallback to in-process limiter if Redis is temporarily unavailable.
            _requests[bucket] = [t for t in _requests[bucket] if now - t < window]

            if len(_requests[bucket]) >= settings.rate_limit_per_minute:
                oldest_request = _requests[bucket][0]
                retry_after = max(1, int(window - (now - oldest_request)))
                return _too_many_requests_response(retry_after)

            _requests[bucket].append(now)
            return await call_next(request)
