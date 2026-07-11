"""Unit tests for the audit_log module.

Tests command-usage tracking, flush behaviour, and stats.
"""

import json
import os
import tempfile
import pytest

from audit_log import record_command, flush, get_stats, get_recent


class TestRecordAndFlush:
    """Tests for recording commands and flushing to disk."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch, tmp_path):
        """Point audit_log to a temp file for each test."""
        self.log_path = tmp_path / "audit_log.json"
        monkeypatch.setenv("AUDIT_LOG_PATH", str(self.log_path))
        # Reload module to pick up path change
        import importlib
        import audit_log
        importlib.reload(audit_log)
        from audit_log import record_command as rc, flush as fl
        self.record_command = rc
        self.flush = fl

    def test_record_adds_to_queue(self):
        """record_command should add an entry to the in-memory queue without
        writing to disk immediately."""
        self.record_command(
            user_id=1, user_name="Alice",
            guild_id=100, guild_name="G1",
            command="play", options={"q": "test"}
        )
        # Should not have written to disk yet
        assert not self.log_path.exists()

    def test_flush_writes_to_disk(self):
        """flush should write queued entries to the JSON file."""
        self.record_command(
            user_id=1, user_name="Alice",
            guild_id=100, guild_name="G1",
            command="play",
        )
        n = self.flush()
        assert n == 1
        assert self.log_path.exists()
        with open(self.log_path) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["command"] == "play"

    def test_flush_idempotent(self):
        """Calling flush on an empty queue returns 0."""
        n = self.flush()
        assert n == 0


class TestStats:
    """Tests for the get_stats helper."""

    def test_stats_no_file(self, monkeypatch, tmp_path):
        """When no audit file exists, stats should be all zeros."""
        path = tmp_path / "nonexistent.json"
        monkeypatch.setenv("AUDIT_LOG_PATH", str(path))
        import importlib
        import audit_log
        importlib.reload(audit_log)
        from audit_log import get_stats
        stats = get_stats()
        assert stats["total_commands"] == 0
        assert stats["unique_users"] == 0

    def test_stats_with_data(self, monkeypatch, tmp_path):
        """Stats should count entries correctly."""
        path = tmp_path / "audit_log.json"
        data = [
            {"user_id": 1, "command": "play"},
            {"user_id": 1, "command": "skip"},
            {"user_id": 2, "command": "play"},
        ]
        with open(path, "w") as f:
            json.dump(data, f)
        monkeypatch.setenv("AUDIT_LOG_PATH", str(path))
        import importlib
        import audit_log
        importlib.reload(audit_log)
        from audit_log import get_stats
        stats = get_stats()
        assert stats["total_commands"] == 3
        assert stats["unique_users"] == 2


class TestGetRecent:
    """Tests for get_recent which returns the latest entries."""

    def test_recent_returns_latest_first(self, monkeypatch, tmp_path):
        """get_recent should return newest entries first (reversed)."""
        path = tmp_path / "audit_log.json"
        data = [{"user_id": i, "command": "cmd"} for i in range(10)]
        with open(path, "w") as f:
            json.dump(data, f)
        monkeypatch.setenv("AUDIT_LOG_PATH", str(path))
        import importlib
        import audit_log
        importlib.reload(audit_log)
        from audit_log import get_recent
        recent = get_recent(limit=3)
        assert len(recent) == 3
        # Most recent first
        assert recent[0]["user_id"] == 9
