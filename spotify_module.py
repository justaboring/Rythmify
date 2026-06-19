import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import List, Optional

class SpotifyClient:
    def __init__(self, client_id: str, client_secret: str):
        self.enabled = bool(client_id and client_secret)
        self.client = None
        if self.enabled:
            auth_manager = SpotifyClientCredentials(
                client_id=client_id,
                client_secret=client_secret
            )
            self.client = spotipy.Spotify(auth_manager=auth_manager)
    
    def get_track_query(self, track_id: str) -> Optional[str]:
        if not self.enabled or not self.client:
            return None
        try:
            track = self.client.track(track_id)
            artist = track['artists'][0]['name']
            name = track['name']
            return f"{artist} - {name}"
        except Exception as e:
            print(f"Spotify get_track_query error: {e}")
            return None

    def search_track(self, query: str) -> Optional[str]:
        if not self.enabled or not self.client:
            return None
        try:
            results = self.client.search(q=query, type='track', limit=1)
            tracks = results.get('tracks', {}).get('items', [])
            if tracks:
                track = tracks[0]
                artist = track['artists'][0]['name']
                name = track['name']
                return f"{artist} - {name}"
            return None
        except Exception as e:
            print(f"Spotify search_track error: {e}")
            return None

    def search_playlist_queries(self, query: str) -> List[str]:
        """Mencari playlist secara global berdasarkan nama dan mengambil track-nya."""
        if not self.enabled or not self.client:
            return []
        try:
            # Cari playlist yang paling relevan
            results = self.client.search(q=query, type='playlist', limit=1)
            items = results.get('playlists', {}).get('items', [])
            if items:
                playlist_id = items[0]['id']
                return self.get_playlist_queries(playlist_id)
            return []
        except Exception as e:
            print(f"Spotify search_playlist error: {e}")
            return []

    def get_playlist_queries(self, playlist_id: str) -> List[str]:
        if not self.enabled or not self.client:
            return []
        queries = []
        try:
            # Fetch tracks with pagination support
            results = self.client.playlist_items(playlist_id, limit=100, additional_types=('track',))
            while results:
                for item in results.get('items', []):
                    track = item.get('track')
                    if track and track.get('name'):
                        artist = track['artists'][0]['name']
                        name = track['name']
                        queries.append(f"{artist} - {name}")
                
                # Limit to 200 tracks to avoid extreme wait times during YouTube resolution
                if results['next'] and len(queries) < 200:
                    results = self.client.next(results)
                else:
                    results = None
            return queries
        except Exception as e:
            print(f"Spotify get_playlist_queries error: {e}")
            return []

    def get_album_queries(self, album_id: str) -> List[str]:
        if not self.enabled or not self.client:
            return []
        queries = []
        try:
            results = self.client.album_tracks(album_id, limit=50)
            while results:
                for track in results.get('items', []):
                    artist = track['artists'][0]['name']
                    name = track['name']
                    queries.append(f"{artist} - {name}")
                if results['next'] and len(queries) < 100:
                    results = self.client.next(results)
                else:
                    results = None
            return queries
        except Exception as e:
            print(f"Spotify get_album_queries error: {e}")
            return []
