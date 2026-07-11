"""
command_rate_limiter.py — Token bucket rate limiter per user per command.

Thread-safe (asyncio). Configuration via environment variables:
    RATE_LIMIT_TOKENS=5        # max burst per window
    RATE_LIMIT_REFILL_RATE=1   # tokens added per refill period
    RATE_LIMIT_REFILL_SECONDS=5  # refill period in seconds
    RATE_LIMIT_ENABLED=true    # toggle the entire system
"""

import os
import time
import asyncio
from collections import defaultdict


# ── Configuration from environment ──────────────────────────────────────────
_CONFIG = {
    "enabled": os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true",
    "tokens": int(os.getenv("RATE_LIMIT_TOKENS", "5")),
    "refill_rate": float(os.getenv("RATE_LIMIT_REFILL_RATE", "1")),
    "refill_seconds": float(os.getenv("RATE_LIMIT_REFILL_SECONDS", "5")),
}


class TokenBucket:
    """Token bucket for a single user × command combination."""

    __slots__ = ("max_tokens", "refill_rate", "refill_period", "_tokens", "_last_refill", "_lock")

    def __init__(self, max_tokens: int, refill_rate: float, refill_period: float):
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self.refill_period = refill_period
        self._tokens = float(max_tokens)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        """Add tokens based on elapsed time (must hold lock)."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed >= self.refill_period:
            added = (elapsed / self.refill_period) * self.refill_rate
            self._tokens = min(self.max_tokens, self._tokens + added)
            self._last_refill = now

    async def consume(self) -> bool:
        """Try to consume one token. Returns True if allowed, False if rate-limited."""
        if not _CONFIG["enabled"]:
            return True
        async with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return True
            return False

    @property
    async def remaining(self) -> float:
        """How many tokens remain (approximate, no state change)."""
        async with self._lock:
            self._refill()
            return self._tokens


# ── Global registry ─────────────────────────────────────────────────────────
# Key: (user_id: int, command_name: str) → TokenBucket
_buckets: dict[tuple[int, str], TokenBucket] = {}
_registry_lock = asyncio.Lock()


async def check_rate_limit(user_id: int, command_name: str) -> bool:
    """Return True if the command is allowed, False if rate-limited."""
    if not _CONFIG["enabled"]:
        return True

    key = (user_id, command_name)
    async with _registry_lock:
        if key not in _buckets:
            _buckets[key] = TokenBucket(
                max_tokens=_CONFIG["tokens"],
                refill_rate=_CONFIG["refill_rate"],
                refill_period=_CONFIG["refill_seconds"],
            )
        bucket = _buckets[key]

    return await bucket.consume()


async def rate_limit_remaining(user_id: int, command_name: str) -> float:
    """Check remaining tokens without consuming one."""
    key = (user_id, command_name)
    async with _registry_lock:
        bucket = _buckets.get(key)
    if bucket is None:
        return float(_CONFIG["tokens"])
    return await bucket.remaining


def get_rate_limit_config() -> dict:
    """Return current configuration for display / debugging."""
    return dict(_CONFIG)
