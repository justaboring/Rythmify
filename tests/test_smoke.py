"""Smoke tests — verify core modules import without errors."""

import os
import importlib
import pytest


# Set required env vars before any config-dependent imports
@pytest.fixture(autouse=True)
def _set_env(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "mock_token")
    monkeypatch.setenv("OWNER_ID", "12345")


def test_import_command_rate_limiter():
    """Rate limiter has no external deps beyond stdlib."""
    import command_rate_limiter
    assert hasattr(command_rate_limiter, "check_rate_limit")
    assert hasattr(command_rate_limiter, "TokenBucket")


def test_import_audit_log():
    """Audit log module has no external deps beyond stdlib."""
    import audit_log
    assert hasattr(audit_log, "record_command")
    assert hasattr(audit_log, "flush")
    assert hasattr(audit_log, "get_stats")
    assert hasattr(audit_log, "get_recent")


def test_import_config():
    """Config module requires env vars to be set."""
    import importlib
    import config
    importlib.reload(config)
    assert hasattr(config, "Config")
    assert not hasattr(config.Config, "SPOTIFY_CLIENT_ID")


def test_import_ytmusic_module():
    """ytmusic_module depends only on ytmusicapi."""
    import ytmusic_module
    assert hasattr(ytmusic_module, "search_songs")
    assert hasattr(ytmusic_module, "search_videos")
    assert hasattr(ytmusic_module, "get_artist_radio")
    assert hasattr(ytmusic_module, "get_mood_playlists")
    assert hasattr(ytmusic_module, "get_mood_tracks")
    assert hasattr(ytmusic_module, "get_playlist_tracks")
    assert hasattr(ytmusic_module, "track_to_source_data")


def test_import_utils():
    """Utils module has no external deps beyond stdlib."""
    import utils
    assert hasattr(utils, "format_duration")
    assert hasattr(utils, "is_url")


def test_import_ui_components():
    """UI components module depends on discord.py."""
    import ui_components
    assert hasattr(ui_components, "NowPlayingView")


def test_import_music_player():
    """YTDLSource and GuildMusicState are the core of the player.

    Reload config first with env vars so the import chain succeeds.
    """
    import importlib
    import config
    importlib.reload(config)

    import music_player
    assert hasattr(music_player, "YTDLSource")
    assert hasattr(music_player, "GuildMusicState")
    assert hasattr(music_player, "get_guild_state")
    assert hasattr(music_player, "play_next_song")


def test_import_panel_store():
    import panel_store
    assert hasattr(panel_store, "get_panel")


def test_import_playlist_store():
    import playlist_store
    assert hasattr(playlist_store, "create_playlist")


def test_import_quality_store():
    import quality_store
    assert hasattr(quality_store, "get_quality")
