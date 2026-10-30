from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException

from app.config import get_settings


class RateLimiter:
    def __init__(self) -> None:
        self.local: dict[str, deque[float]] = defaultdict(deque)
        self.redis = None
        if get_settings().app_env != "test":
            try:
                from redis import Redis

                self.redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
            except Exception:
                self.redis = None

    def check(self, key: str, limit: int | None = None) -> None:
        limit = limit or get_settings().rate_limit_per_minute
        window = int(time.time() // 60)
        if self.redis:
            try:
                redis_key = f"rate:{key}:{window}"
                value = self.redis.incr(redis_key)
                if value == 1:
                    self.redis.expire(redis_key, 65)
                if value > limit:
                    raise HTTPException(429, "Limite de requisições excedido")
                return
            except HTTPException:
                raise
            except Exception:
                pass
        now = time.time()
        bucket = self.local[key]
        while bucket and bucket[0] < now - 60:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(429, "Limite de requisições excedido")
        bucket.append(now)


limiter = RateLimiter()
