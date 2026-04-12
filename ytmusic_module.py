import asyncio
import concurrent.futures
from ytmusicapi import YTMusic

_ytmusic = None


def get_ytmusic() -> YTMusic:
    global _ytmusic
    if _ytmusic is None:
        _ytmusic = YTMusic()
    return _ytmusic


# ──────────────────────────────────────────────
# SEARCH
# ──────────────────────────────────────────────

def search_songs(query: str, limit: int = 5) -> list:
    """Search YT Music for songs. Returns list of track dicts."""
    ytm = get_ytmusic()
    try:
        results = ytm.search(query, filter="songs", limit=limit)
        tracks = []
        for r in results[:limit]:
            vid = r.get("videoId")
            if not vid:
                continue
            duration_text = r.get("duration", "0:00")
            duration_sec = _parse_duration(duration_text)
            artists = ", ".join(a["name"] for a in r.get("artists", []) if a.get("name"))
            album = r.get("album", {})
            album_name = album.get("name", "") if album else ""
            thumbnail = None
            thumbs = r.get("thumbnails", [])
            if thumbs:
                thumbnail = thumbs[-1].get("url")
            tracks.append({
                "videoId": vid,
                "title": r.get("title", "Unknown"),
                "artist": artists,
                "album": album_name,
                "duration": duration_sec,
                "thumbnail": thumbnail,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        return tracks
    except Exception as e:
        print(f"YTMusic search error: {e}")
        return []


def search_videos(query: str, limit: int = 5) -> list:
    """Search YT Music for videos."""
    ytm = get_ytmusic()
    try:
        results = ytm.search(query, filter="videos", limit=limit)
        tracks = []
        for r in results[:limit]:
            vid = r.get("videoId")
            if not vid:
                continue
            duration_text = r.get("duration", "0:00")
            duration_sec = _parse_duration(duration_text)
            artists = ", ".join(a["name"] for a in r.get("artists", []) if a.get("name"))
            thumbnail = None
            thumbs = r.get("thumbnails", [])
            if thumbs:
                thumbnail = thumbs[-1].get("url")
            tracks.append({
                "videoId": vid,
                "title": r.get("title", "Unknown"),
                "artist": artists,
                "album": "",
                "duration": duration_sec,
                "thumbnail": thumbnail,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        return tracks
    except Exception as e:
        print(f"YTMusic video search error: {e}")
        return []


# ──────────────────────────────────────────────
# ARTIST RADIO
# ──────────────────────────────────────────────

def get_artist_radio(artist_name: str, limit: int = 20) -> list:
    """Get radio/mix based on artist name."""
    ytm = get_ytmusic()
    try:
        # Search for artist
        results = ytm.search(artist_name, filter="artists", limit=1)
        if not results:
            # fallback: search songs by artist and build radio from first result
            songs = search_songs(artist_name, limit=1)
            if songs:
                return get_song_radio(songs[0]["videoId"], limit=limit)
            return []

        artist = results[0]
        artist_id = artist.get("browseId")
        if not artist_id:
            return []

        # Get artist info to find a popular song
        artist_info = ytm.get_artist(artist_id)
        songs_section = artist_info.get("songs", {})
        results_songs = songs_section.get("results", [])

        if not results_songs:
            return []

        # Use first song to build radio
        first_video_id = results_songs[0].get("videoId")
        if not first_video_id:
            return []

        return get_song_radio(first_video_id, limit=limit)

    except Exception as e:
        print(f"YTMusic artist radio error: {e}")
        return []


def get_song_radio(video_id: str, limit: int = 20) -> list:
    """Get radio playlist based on a video ID."""
    ytm = get_ytmusic()
    try:
        watch = ytm.get_watch_playlist(videoId=video_id, radio=True, limit=limit + 5)
        tracks = watch.get("tracks", [])
        results = []
        for t in tracks:
            vid = t.get("videoId")
            if not vid or vid == video_id:
                continue
            artists = ", ".join(a["name"] for a in t.get("artists", []) if a.get("name"))
            thumbnail = None
            thumbs = t.get("thumbnail", [])
            if thumbs:
                thumbnail = thumbs[-1].get("url")
            duration_text = t.get("duration", "0:00")
            duration_sec = _parse_duration(duration_text)
            results.append({
                "videoId": vid,
                "title": t.get("title", "Unknown"),
                "artist": artists,
                "album": "",
                "duration": duration_sec,
                "thumbnail": thumbnail,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
            if len(results) >= limit:
                break
        return results
    except Exception as e:
        print(f"YTMusic song radio error: {e}")
        return []


# ──────────────────────────────────────────────
# MOOD / GENRE
# ──────────────────────────────────────────────

def get_mood_playlists() -> dict:
    """Get available moods and genres from YT Music."""
    ytm = get_ytmusic()
    try:
        moods = ytm.get_mood_categories()
        return moods
    except Exception as e:
        print(f"YTMusic mood error: {e}")
        return {}


def get_mood_tracks(params: str, limit: int = 20) -> list:
    """Get tracks from a mood playlist by params string."""
    ytm = get_ytmusic()
    try:
        playlist = ytm.get_mood_content(params)
        tracks = []
        for section in playlist:
            for item in section.get("contents", []):
                vid = item.get("videoId")
                if not vid:
                    continue
                artists = ", ".join(a["name"] for a in item.get("artists", []) if a.get("name"))
                thumbnail = None
                thumbs = item.get("thumbnails", [])
                if thumbs:
                    thumbnail = thumbs[-1].get("url")
                duration_sec = item.get("duration_seconds", 0)
                tracks.append({
                    "videoId": vid,
                    "title": item.get("title", "Unknown"),
                    "artist": artists,
                    "album": "",
                    "duration": duration_sec,
                    "thumbnail": thumbnail,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                })
                if len(tracks) >= limit:
                    return tracks
        return tracks
    except Exception as e:
        print(f"YTMusic mood tracks error: {e}")
        return []


# ──────────────────────────────────────────────
# PLAYLIST (unauthenticated - public only)
# ──────────────────────────────────────────────

def get_playlist_tracks(playlist_id: str, limit: int = 50) -> list:
    """Get tracks from a public YT Music playlist."""
    ytm = get_ytmusic()
    try:
        playlist = ytm.get_playlist(playlist_id, limit=limit)
        tracks = []
        for t in playlist.get("tracks", []):
            vid = t.get("videoId")
            if not vid:
                continue
            artists = ", ".join(a["name"] for a in t.get("artists", []) if a.get("name"))
            thumbnail = None
            thumbs = t.get("thumbnails", [])
            if thumbs:
                thumbnail = thumbs[-1].get("url")
            duration_sec = t.get("duration_seconds", 0)
            tracks.append({
                "videoId": vid,
                "title": t.get("title", "Unknown"),
                "artist": artists,
                "album": "",
                "duration": duration_sec,
                "thumbnail": thumbnail,
                "url": f"https://www.youtube.com/watch?v={vid}",
            })
        return tracks
    except Exception as e:
        print(f"YTMusic playlist error: {e}")
        return []


# ──────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────

def _parse_duration(duration_text: str) -> int:
    """Convert MM:SS or HH:MM:SS string to seconds."""
    if not duration_text:
        return 0
    try:
        parts = duration_text.strip().split(":")
        parts = [int(p) for p in parts]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        elif len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
    except Exception:
        pass
    return 0


def track_to_source_data(track: dict) -> dict:
    """Convert YTMusic track dict to yt-dlp compatible data dict."""
    return {
        "title": track["title"],
        "url": track["url"],
        "webpage_url": track["url"],
        "duration": track["duration"],
        "thumbnail": track["thumbnail"],
        "uploader": track["artist"],
        "id": track["videoId"],
    }
