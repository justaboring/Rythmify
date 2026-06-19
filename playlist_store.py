import json
import os
from typing import Dict, List, Optional

PLAYLIST_FILE = "playlists.json"

def _load() -> Dict:
    if not os.path.exists(PLAYLIST_FILE):
        return {}
    try:
        with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def _save(data: Dict):
    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def create_playlist(guild_id: int, user_id: int, name: str, songs: List[Dict] = None) -> bool:
    """Create a new playlist"""
    data = _load()
    gid = str(guild_id)
    uid = str(user_id)
    
    if gid not in data:
        data[gid] = {}
    if uid not in data[gid]:
        data[gid][uid] = {}
    
    if name in data[gid][uid]:
        return False  # Playlist already exists
    
    data[gid][uid][name] = {
        "name": name,
        "created_at": None,  # Can add timestamp if needed
        "songs": songs or []
    }
    _save(data)
    return True

def save_queue_as_playlist(guild_id: int, user_id: int, name: str, queue: List) -> bool:
    """Save current queue as a playlist"""
    songs = []
    for song in queue:
        song_data = {
            "title": getattr(song, "title", "Unknown"),
            "url": getattr(song, "url", None),
            "webpage_url": getattr(song, "webpage_url", None),
            "thumbnail": getattr(song, "thumbnail", None),
            "duration": getattr(song, "duration", None),
            "uploader": getattr(song, "uploader", None)
        }
        songs.append(song_data)
    return create_playlist(guild_id, user_id, name, songs)

def get_playlist(guild_id: int, user_id: int, name: str) -> Optional[Dict]:
    """Get a specific playlist"""
    data = _load()
    gid = str(guild_id)
    uid = str(user_id)
    
    if gid not in data or uid not in data[gid] or name not in data[gid][uid]:
        return None
    return data[gid][uid][name]

def get_user_playlists(guild_id: int, user_id: int) -> List[Dict]:
    """Get all playlists for a user"""
    data = _load()
    gid = str(guild_id)
    uid = str(user_id)
    
    if gid not in data or uid not in data[gid]:
        return []
    return list(data[gid][uid].values())

def get_all_playlists(guild_id: int) -> Dict[int, List[Dict]]:
    """Get all playlists in a guild"""
    data = _load()
    gid = str(guild_id)
    
    if gid not in data:
        return {}
    return {int(uid): list(playlists.values()) for uid, playlists in data[gid].items()}

def delete_playlist(guild_id: int, user_id: int, name: str) -> bool:
    """Delete a playlist"""
    data = _load()
    gid = str(guild_id)
    uid = str(user_id)
    
    if gid not in data or uid not in data[gid] or name not in data[gid][uid]:
        return False
    
    del data[gid][uid][name]
    _save(data)
    return True

def add_to_playlist(guild_id: int, user_id: int, name: str, song: Dict) -> bool:
    """Add a song to an existing playlist"""
    data = _load()
    gid = str(guild_id)
    uid = str(user_id)
    
    if gid not in data or uid not in data[gid] or name not in data[gid][uid]:
        return False
    
    data[gid][uid][name]["songs"].append(song)
    _save(data)
    return True

def remove_from_playlist(guild_id: int, user_id: int, name: str, index: int) -> bool:
    """Remove a song from a playlist"""
    data = _load()
    gid = str(guild_id)
    uid = str(user_id)
    
    if gid not in data or uid not in data[gid] or name not in data[gid][uid]:
        return False
    
    if index < 0 or index >= len(data[gid][uid][name]["songs"]):
        return False
    
    del data[gid][uid][name]["songs"][index]
    _save(data)
    return True
