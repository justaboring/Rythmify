"""pytest fixtures for Gratify tests."""

import pytest


@pytest.fixture
def rate_limit_config():
    """Provide a clean rate limit config dict for testing."""
    return {
        "enabled": True,
        "tokens": 5,
        "refill_rate": 1.0,
        "refill_seconds": 5.0,
    }


@pytest.fixture
def audit_entry():
    """Provide a sample audit log entry."""
    return {
        "timestamp": "2025-01-01T00:00:00Z",
        "user_id": 12345,
        "user_name": "TestUser#1234",
        "guild_id": 67890,
        "guild_name": "Test Guild",
        "command": "play",
        "options": {"query": "test song"},
    }
