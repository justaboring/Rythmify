import json
import os
from collections import defaultdict

STATS_FILE = "stats_store.json"


def _load() -> dict:
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict):
    with open(STATS_FILE, "w") as f:
        json.dump(data, f)


def record_play(guild_id: int, title: str):
    """Call this every time a song starts playing."""
    data = _load()
    gid  = str(guild_id)
    if gid not in data:
        data[gid] = {"total_played": 0, "songs": {}}
    data[gid]["total_played"] += 1
    data[gid]["songs"][title]  = data[gid]["songs"].get(title, 0) + 1
    _save(data)


def get_stats(guild_id: int) -> dict:
    """Return {'total_played': int, 'top_songs': [(title, count), ...]}"""
    data = _load()
    gid  = str(guild_id)
    if gid not in data:
        return {"total_played": 0, "top_songs": []}
    entry     = data[gid]
    songs     = entry.get("songs", {})
    top_songs = sorted(songs.items(), key=lambda x: x[1], reverse=True)[:5]
    return {"total_played": entry.get("total_played", 0), "top_songs": top_songs}
