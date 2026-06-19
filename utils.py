import re
from typing import Optional, Tuple

# Pre-compiled regex patterns for Spotify URLs
SPOTIFY_PATTERNS = [
    (re.compile(r'open\.spotify\.com/track/([a-zA-Z0-9]+)(?:\?.*)?'), 'track'),
    (re.compile(r'open\.spotify\.com/album/([a-zA-Z0-9]+)(?:\?.*)?'), 'album'),
    (re.compile(r'open\.spotify\.com/playlist/([a-zA-Z0-9]+)(?:\?.*)?'), 'playlist'),
]


def format_duration(seconds: Optional[int]) -> str:
    """Format seconds to MM:SS or HH:MM:SS."""
    if seconds is None:
        return "?:??"
    if seconds < 0:
        seconds = 0

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def create_progress_bar(current: int, total: int, length: int = 20) -> str:
    """Create a text progress bar."""
    if total <= 0:
        return "█" * length
    if current < 0:
        current = 0
    if current > total:
        current = total

    filled = int(length * current / total)
    bar = "█" * filled + "░" * (length - filled)
    return bar


def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
    """Parse Spotify URL and return (type, id) or None."""
    for pattern, url_type in SPOTIFY_PATTERNS:
        match = pattern.search(url)
        if match:
            return (url_type, match.group(1))
    return None


def is_url(text: str) -> bool:
    """Check if string is a URL."""
    return text.startswith(('http://', 'https://', 'www.'))


def truncate_string(text: str, max_length: int = 100) -> str:
    """Truncate string with ellipsis."""
    if max_length < 3:
        max_length = 3
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."
