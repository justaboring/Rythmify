import json
import os
import time
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


def record_play(guild_id: int, title: str, duration: int = None, uploader: str = None):
    """Call this every time a song starts playing."""
    data = _load()
    gid  = str(guild_id)
    if gid not in data:
        data[gid] = {"total_played": 0, "songs": {}, "play_history": [], "artists": {}}
    
    # Ensure all keys exist
    if "total_played" not in data[gid]:
        data[gid]["total_played"] = 0
    if "songs" not in data[gid]:
        data[gid]["songs"] = {}
    if "play_history" not in data[gid]:
        data[gid]["play_history"] = []
    if "artists" not in data[gid]:
        data[gid]["artists"] = {}
    
    data[gid]["total_played"] += 1
    data[gid]["songs"][title] = data[gid]["songs"].get(title, 0) + 1
    
    # Track play history with timestamp
    play_entry = {
        "title": title,
        "timestamp": int(time.time()),
        "duration": duration,
        "uploader": uploader
    }
    data[gid]["play_history"].append(play_entry)
    
    # Track artists
    if uploader:
        data[gid]["artists"][uploader] = data[gid]["artists"].get(uploader, 0) + 1
    
    # Keep only last 1000 plays to prevent file from getting too big
    if len(data[gid]["play_history"]) > 1000:
        data[gid]["play_history"] = data[gid]["play_history"][-1000:]
    
    _save(data)


def get_stats(guild_id: int) -> dict:
    """Return detailed stats for the guild."""
    data = _load()
    gid  = str(guild_id)
    if gid not in data:
        return {"total_played": 0, "top_songs": [], "top_artists": [], "play_history": [], "hourly_stats": [], "daily_stats": []}
    
    entry = data[gid]
    songs = entry.get("songs", {})
    artists = entry.get("artists", {})
    play_history = entry.get("play_history", [])
    
    top_songs = sorted(songs.items(), key=lambda x: x[1], reverse=True)[:10]
    top_artists = sorted(artists.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Calculate hourly and daily stats
    hourly_stats = defaultdict(int)
    daily_stats = defaultdict(int)
    
    for play in play_history:
        ts = play.get("timestamp", 0)
        hour_key = time.strftime("%H", time.localtime(ts))
        day_key = time.strftime("%Y-%m-%d", time.localtime(ts))
        hourly_stats[hour_key] += 1
        daily_stats[day_key] += 1
    
    # Convert to sorted lists for charts
    hourly_stats_list = [{"hour": h, "count": hourly_stats.get(str(h), 0)} for h in range(24)]
    daily_stats_list = sorted([{"day": d, "count": c} for d, c in daily_stats.items()], key=lambda x: x["day"])
    
    return {
        "total_played": entry.get("total_played", 0),
        "top_songs": top_songs,
        "top_artists": top_artists,
        "play_history": play_history,
        "hourly_stats": hourly_stats_list,
        "daily_stats": daily_stats_list
    }


def get_all_guild_stats() -> dict:
    """Get aggregated stats across all guilds."""
    data = _load()
    all_stats = {
        "total_guilds": len(data),
        "total_plays_all": sum(entry.get("total_played", 0) for entry in data.values()),
        "active_guilds": 0
    }
    
    # Count guilds with plays in last 24h
    now = int(time.time())
    day_ago = now - 86400
    for entry in data.values():
        for play in entry.get("play_history", []):
            if play.get("timestamp", 0) > day_ago:
                all_stats["active_guilds"] += 1
                break
    
    return all_stats
