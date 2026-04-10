import asyncio
import yt_dlp


class SoundCloudClient:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def search_track(self, query, limit=5):
        opts = {'quiet': True, 'no_warnings': True}
        search_query = f"scsearch{limit}:{query}"
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                data = ydl.extract_info(search_query, download=False)
            if not data or 'entries' not in data:
                return []
            tracks = []
            for entry in data['entries']:
                if not entry:
                    continue
                tracks.append({
                    'id': entry.get('id', ''),
                    'name': entry.get('title', 'Unknown'),
                    'artist': entry.get('uploader', 'Unknown'),
                    'thumbnail': entry.get('thumbnail'),
                    'duration_sec': entry.get('duration', 0),
                    'url': entry.get('webpage_url', ''),
                })
            return tracks
        except Exception as e:
            print(f"SoundCloud search error: {e}")
            return []

    def is_available(self):
        return True


def soundcloud_to_youtube_query(track):
    artist = track.get('artist', '')
    name = track.get('name', '')
    return f"{artist} - {name}"
