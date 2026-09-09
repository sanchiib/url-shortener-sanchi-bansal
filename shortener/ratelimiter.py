"""
A small, dependency-free sliding-window rate limiter.

Not distributed (state lives in process memory), which is fine for a
single-process dev/demo deployment. For multi-process/production use
this would need to move to something shared like Redis - noted in the
README.
"""

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str):
        """Return (allowed: bool, retry_after_seconds: float)."""
        now = time.monotonic()
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] > self.window_seconds:
                hits.popleft()

            if len(hits) >= self.max_requests:
                retry_after = self.window_seconds - (now - hits[0])
                return False, max(retry_after, 0.0)

            hits.append(now)
            return True, 0.0
