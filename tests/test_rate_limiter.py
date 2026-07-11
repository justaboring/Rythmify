"""Unit tests for command_rate_limiter.

Tests the token-bucket rate limiter used to throttle Discord commands.
"""

import importlib
import pytest

import command_rate_limiter

from command_rate_limiter import (
    TokenBucket,
    check_rate_limit,
    get_rate_limit_config,
)


class TestTokenBucket:
    """Tests for the TokenBucket class."""

    @pytest.mark.asyncio
    async def test_consume_allowed(self):
        """A fresh bucket should allow consumption."""
        bucket = TokenBucket(max_tokens=5, refill_rate=1.0, refill_period=5.0)
        assert await bucket.consume() is True

    @pytest.mark.asyncio
    async def test_consume_exhausted(self):
        """An empty bucket should deny consumption."""
        bucket = TokenBucket(max_tokens=1, refill_rate=1.0, refill_period=60.0)
        assert await bucket.consume() is True
        assert await bucket.consume() is False

    @pytest.mark.asyncio
    async def test_remaining_property(self):
        """Remaining tokens should reflect consumption."""
        bucket = TokenBucket(max_tokens=3, refill_rate=1.0, refill_period=60.0)
        rem = await bucket.remaining
        assert rem == 3.0
        await bucket.consume()
        rem = await bucket.remaining
        assert rem == 2.0


class TestCheckRateLimit:
    """Tests for the check_rate_limit top-level function.

    These tests use a dedicated module reload with the env var changes so they
    don't leak state between test runs.
    """

    @pytest.fixture(autouse=True)
    def _reset_module(self, monkeypatch):
        """Ensure each test starts with a clean rate-limiter state."""
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
        monkeypatch.setenv("RATE_LIMIT_TOKENS", "5")
        monkeypatch.setenv("RATE_LIMIT_REFILL_RATE", "1")
        monkeypatch.setenv("RATE_LIMIT_REFILL_SECONDS", "60")  # long window so no refill
        importlib.reload(command_rate_limiter)
        from command_rate_limiter import check_rate_limit
        self._check = check_rate_limit

    @pytest.mark.asyncio
    async def test_disabled_always_allows(self, monkeypatch):
        """When rate limiting is disabled, every call is allowed."""
        monkeypatch.setenv("RATE_LIMIT_ENABLED", "false")
        importlib.reload(command_rate_limiter)
        from command_rate_limiter import check_rate_limit as chk

        for _ in range(100):
            assert await chk(1, "test_cmd") is True

    @pytest.mark.asyncio
    async def test_burst_exhaustion(self):
        """A user can burst all tokens then gets blocked."""
        for _ in range(5):
            assert await self._check(99, "burst_cmd") is True
        assert await self._check(99, "burst_cmd") is False

    @pytest.mark.asyncio
    async def test_separate_users_independent(self):
        """Two different users should have independent rate-limit buckets."""
        for _ in range(5):
            assert await self._check(10, "cmd") is True
        # user 10 exhausted
        assert await self._check(10, "cmd") is False
        # user 20 still has tokens
        assert await self._check(20, "cmd") is True


class TestGetConfig:
    """Tests for the config inspection helper."""

    def test_returns_dict(self):
        """get_rate_limit_config should return a dict with expected keys."""
        cfg = get_rate_limit_config()
        assert isinstance(cfg, dict)
        assert "enabled" in cfg
        assert "tokens" in cfg
        assert "refill_rate" in cfg
        assert "refill_seconds" in cfg
