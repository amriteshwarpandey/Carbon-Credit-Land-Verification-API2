"""Small in-memory sliding-window rate limiter, usable as a FastAPI dependency.

Per process and keyed by client IP, so it blunts password guessing but is not a distributed limiter:
with several API replicas, enforce limits at the reverse proxy / API gateway too (and make sure the
proxy forwards the real client IP, e.g. uvicorn --proxy-headers).
"""
import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import HTTPException, Request


class RateLimiter:
    def __init__(self, limit: Callable[[], int], window_seconds: int = 60):
        self.limit, self.window = limit, window_seconds
        self.hits: dict[str, deque] = defaultdict(deque)

    def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.monotonic()
        q = self.hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        limit = self.limit()
        if limit <= 0:  # 0 disables limiting
            return
        if len(q) >= limit:
            retry = max(1, int(self.window - (now - q[0])))
            raise HTTPException(429, "Too many attempts, slow down", headers={"Retry-After": str(retry)})
        q.append(now)

    def reset(self) -> None:
        self.hits.clear()
