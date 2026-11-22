"""Token-Bucket Rate Limiter and Daily Draft Quota Engine for TallyGuard MCP.

Implements FR-052 and FR-044.
Provides tenant and user rate limiting with token-bucket algorithm,
burst handling, and daily draft submission quotas.
"""

from datetime import datetime, timezone, date
import threading
import time
from typing import Dict, Optional, Tuple


class RateLimitedError(Exception):
    """Raised when a tenant or user exceeds their allowed rate limit or daily quota."""

    def __init__(self, message: str, retry_after_seconds: float):
        super().__init__(message)
        self.code = "RATE_LIMITED"
        self.retry_after_seconds = retry_after_seconds


class TokenBucket:
    """Thread-safe token bucket rate limiter."""

    def __init__(self, capacity: int = 60, refill_rate_per_sec: float = 1.0):
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate_per_sec)
        self.tokens = float(capacity)
        self.last_updated = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens_needed: float = 1.0) -> Tuple[bool, float]:
        """Attempt to consume tokens.

        Returns:
            (allowed: bool, retry_after_seconds: float)
        """
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_updated
            self.last_updated = now

            # Refill bucket
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

            if self.tokens >= tokens_needed:
                self.tokens -= tokens_needed
                return True, 0.0

            # Calculate wait time
            deficit = tokens_needed - self.tokens
            retry_after = deficit / self.refill_rate
            return False, round(retry_after, 2)


class RateLimiter:
    """Manager for tenant and user-level rate limits and quotas."""

    def __init__(
        self,
        default_rate_limit: int = 60,
        default_refill_per_sec: float = 1.0,
        max_daily_drafts: int = 50,
    ):
        self.default_capacity = default_rate_limit
        self.default_refill = default_refill_per_sec
        self.max_daily_drafts = max_daily_drafts

        self._buckets: Dict[str, TokenBucket] = {}
        self._daily_draft_counts: Dict[str, Dict[str, int]] = {}  # {user_id: {YYYY-MM-DD: count}}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> TokenBucket:
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(
                    capacity=self.default_capacity,
                    refill_rate_per_sec=self.default_refill,
                )
            return self._buckets[key]

    def check_rate_limit(self, identifier: str, cost: float = 1.0) -> None:
        """Check if request passes rate limit. Raises RateLimitedError if throttled."""
        bucket = self._get_bucket(identifier)
        allowed, retry_after = bucket.consume(cost)
        if not allowed:
            raise RateLimitedError(
                f"RATE_LIMITED: Request rate limit exceeded for '{identifier}'. "
                f"Back off and retry in {retry_after} seconds.",
                retry_after_seconds=retry_after,
            )

    def check_and_increment_daily_drafts(self, user_id: str) -> int:
        """Track daily draft creation quota. Raises RateLimitedError if quota breached."""
        today_str = date.today().isoformat()
        with self._lock:
            if user_id not in self._daily_draft_counts:
                self._daily_draft_counts[user_id] = {}

            current_count = self._daily_draft_counts[user_id].get(today_str, 0)
            if current_count >= self.max_daily_drafts:
                raise RateLimitedError(
                    f"RATE_LIMITED: User '{user_id}' has reached the daily write-draft quota "
                    f"of {self.max_daily_drafts} drafts. Resets tomorrow at midnight.",
                    retry_after_seconds=3600.0,
                )

            self._daily_draft_counts[user_id][today_str] = current_count + 1
            return self._daily_draft_counts[user_id][today_str]
