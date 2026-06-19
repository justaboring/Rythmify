# Discord Music Bot v2 - Design Specification

**Date:** 2026-03-28
**Approach:** Modular Monolith
**Interface:** Slash Commands (/)

---

## 1. Overview

Discord Music Bot v2 is a significant upgrade from the existing Discord music bot. This bot adds:
- Spotify integration (search & URL support)
- Interactive embeds with buttons
- Admin features (DJ role, skip vote, queue management)
- Security fixes & bug fixes
- Migration from prefix commands (!) to slash commands (/)

---

## 2. Architecture

### File Structure

```
discord-music-bot/
├── bot.py                 # Entry point, command registration
├── config.py              # Configuration & constants
├── music_player.py        # Core music functionality (YTDL, queue, playback)
├── spotify_module.py      # Spotify API integration
├── admin_module.py        # Permissions, DJ role, skip vote
├── ui_components.py       # Interactive embeds, buttons, views
├── utils.py               # Helper functions
├── requirements.txt       # Updated dependencies
├── .env.example           # Environment variables template
└── README.md              # Updated documentation
```

### Module Responsibilities

| Module | Purpose | Key Classes/Functions |
|--------|---------|----------------------|
| `config.py` | Centralized configuration | `Config` class, constants |
| `music_player.py` | Core music playback | `YTDLSource`, `GuildMusicState`, `play_song()`, `skip()`, `pause()`, `resume()` |
| `spotify_module.py` | Spotify API integration | `SpotifyClient`, `search_spotify()`, `get_spotify_track()`, `spotify_to_youtube()` |
| `admin_module.py` | Permission system | `is_dj()`, `can_skip()`, `SkipVoteManager`, `remove_from_queue()`, `move_in_queue()` |
| `ui_components.py` | Interactive Discord UI | `NowPlayingView`, `QueueView`, `SkipVoteView` |
| `utils.py` | Shared utilities | `format_duration()`, `get_thumbnail()` |

---

## 3. Data Flow

```
User Slash Command
       ↓
Command Handler (bot.py)
       ↓
Permission Check (admin_module.py)
       ↓
┌─────────────────┬─────────────────┐
↓                 ↓                 ↓
YouTube        Spotify           Admin
(yt-dlp)       API               Operations
↓                 ↓                 ↓
Audio Stream   Track Metadata    Queue Update
↓                 ↓                 ↓
└────────┬────────┴─────────────────┘
         ↓
   Voice Client Play
         ↓
   Update Embed with Buttons
```

### Shared State per Guild

```python
class GuildMusicState:
    def __init__(self):
        self.queue: List[YTDLSource] = []
        self.current_song: Optional[YTDLSource] = None
        self.skip_votes: Set[int] = set()  # User IDs
        self.is_paused: bool = False
        self.volume: float = 0.5
```

---

## 4. Spotify Integration

### Supported Operations

| Feature | Command | Description |
|---------|---------|-------------|
| Spotify Search | `/spotify <query>` | Search and play first result |
| Spotify Selection | `/spotify_search <query>` | Show 5 results for selection |
| URL Detection | `/play <url>` | Auto-detect Spotify URLs |
| Playlist Support | `/play <playlist_url>` | Add all tracks from playlist |

### Supported URLs

- Track: `https://open.spotify.com/track/{id}`
- Album: `https://open.spotify.com/album/{id}`
- Playlist: `https://open.spotify.com/playlist/{id}`

### Flow: Spotify → YouTube

1. Parse Spotify URL using regex → extract type & ID
2. Call Spotify Web API → get track metadata (title, artist, album, thumbnail)
3. Construct search query: `"{artist} - {title} official audio"`
4. Search via yt-dlp → get first result
5. Play via existing YTDL infrastructure

### Spotify API Auth

Using Client Credentials flow (no user login required):
```python
client_id = os.getenv('SPOTIFY_CLIENT_ID')
client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
```

---

## 5. Admin Features

### DJ Role System

- Configurable role name (default: "DJ")
- Commands restricted to DJ:
  - `/stop` - Stop playback & clear queue
  - `/remove <position>` - Remove song from queue
  - `/move <from> <to>` - Reorder queue
  - `/forceskip` - Skip without vote

### Skip Vote System

- Threshold: Configurable percentage (default: 50%)
- One vote per user
- Auto-calculate threshold based on users in voice channel
- Command: `/skip` - Cast vote or bypass if DJ

### Queue Management

| Command | Permission | Description |
|---------|------------|-------------|
| `/remove <index>` | DJ only | Remove specific song |
| `/move <from> <to>` | DJ only | Change song position |
| `/clear` | DJ only | Clear entire queue |
| `/shuffle` | DJ only | Shuffle queue order |

---

## 6. Interactive Embeds (UI)

### Now Playing View

**Visual Elements:**
- Large thumbnail (max size available, 1280x720 or fallback)
- Progress bar with time: `████████████████░░░░░ 3:45 / 5:20`
- Track info: Title, Artist, Album, Duration
- Source indicator: YouTube icon or Spotify icon

**Buttons:**
- ⏸️/▶️ - Play/Pause toggle
- ⏭️ - Skip (or show vote count)
- ⏹️ - Stop (DJ only)
- 🔊- - Volume down 10%
- 🔊+ - Volume up 10%

### Queue View

**Visual Elements:**
- Numbered list (1-10 per page)
- Small thumbnails per song
- Total queue count

**Buttons:**
- ⬆️ - Previous page
- ⬇️ - Next page
- 🗑️ - Remove song (DJ only, prompts confirmation)
- 🔀 - Shuffle (DJ only)

### Skip Vote View

**Visual Elements:**
- Current vote count: "3/5 votes to skip"
- Timeout indicator

**Buttons:**
- ⏭️ Skip - Click to vote
- Real-time update when threshold reached

---

## 7. Command Reference

### Music Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/play <query>` | Play from YouTube/Spotify (auto-detect) | Everyone |
| `/search <query>` | Search YouTube, show 5 results | Everyone |
| `/pause` | Pause playback | Everyone |
| `/resume` | Resume playback | Everyone |
| `/stop` | Stop and clear queue | DJ only |
| `/skip` | Vote to skip (or skip if DJ) | Everyone |
| `/forceskip` | Skip immediately | DJ only |
| `/nowplaying` | Show current song with controls | Everyone |
| `/volume <0-100>` | Set volume | Everyone |

### Queue Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/queue` | View queue with pagination | Everyone |
| `/remove <position>` | Remove song from queue | DJ only |
| `/move <from> <to>` | Move song position | DJ only |
| `/shuffle` | Shuffle queue | DJ only |
| `/clear` | Clear queue | DJ only |

### Spotify Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/spotify <query>` | Search Spotify, play first result | Everyone |
| `/spotify_search <query>` | Search Spotify, choose from 5 results | Everyone |

### Utility Commands

| Command | Description | Permission |
|---------|-------------|------------|
| `/join` | Join voice channel | Everyone |
| `/leave` | Leave voice channel | DJ only |
| `/help` | Show command list | Everyone |

---

## 8. Environment Variables

Required in `.env`:

```env
# Discord
DISCORD_TOKEN=your_discord_bot_token

# Spotify (required for Spotify features)
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Optional Configuration
FFMPEG_PATH=auto                      # auto or specific path
SKIP_VOTE_THRESHOLD=50                # percentage (0-100)
DJ_ROLE_NAME=DJ                        # role name for DJ permissions
MAX_QUEUE_SIZE=100                     # max songs in queue
DEFAULT_VOLUME=50                      # default volume (0-100)
SSL_VERIFY=true                        # true/false for SSL verification
```

---

## 9. Bug Fixes

### Security Fixes

1. **Hardcoded Token Removal**: Line 342 in current bot.py has hardcoded token → remove completely
2. **Token Logging**: Ensure token never logged or printed

### Stability Fixes

1. **Queue Memory Leak**: Add `on_voice_state_update` listener to detect unexpected disconnects
2. **Error Recovery**: Wrap Spotify API calls with retry logic
3. **FFmpeg Path**: Support auto-detection or fallback to PATH
4. **SSL Context**: Make unverified SSL optional via config (default: verified)

### Error Handling

- Network errors (Spotify API down)
- Invalid URLs (malformed Spotify/YouTube URLs)
- FFmpeg errors (corrupted audio)
- Rate limiting (Discord API)
- Voice connection failures

---

## 10. Dependencies

Updated `requirements.txt`:

```
discord.py==2.3.2
yt-dlp
python-dotenv==1.0.0
PyNaCl==1.5.0
ffmpeg-python==0.2.0
spotipy==2.23.0          # NEW: Spotify Web API wrapper
aiohttp==3.9.1           # NEW: Async HTTP client
```

---

## 11. Implementation Notes

### Slash Command Registration

Commands will be registered using `@app_commands.command()` decorator:

```python
@app_commands.command(name="play", description="Play music from YouTube or Spotify")
@app_commands.describe(query="Song name, URL, or Spotify link")
async def play(interaction: discord.Interaction, query: str):
    ...
```

### Button Interactions

Use `discord.ui.View` with `discord.ui.Button`:

```python
class NowPlayingView(discord.ui.View):
    def __init__(self, music_state):
        super().__init__(timeout=None)
        self.music_state = music_state

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ...
```

### Spotify Client

Initialize once, reuse for all requests:

```python
class SpotifyClient:
    def __init__(self):
        self.client = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET
            )
        )
```

---

## 12. Testing Checklist

- [ ] `/play` works with YouTube URL
- [ ] `/play` works with YouTube search query
- [ ] `/play` works with Spotify track URL
- [ ] `/play` works with Spotify playlist URL
- [ ] `/spotify` search returns correct results
- [ ] Interactive buttons (play/pause/skip/volume) work
- [ ] DJ-only commands restricted properly
- [ ] Skip vote system calculates threshold correctly
- [ ] Queue navigation (prev/next page) works
- [ ] Remove/Move queue items work
- [ ] Token not exposed in any output
- [ ] Bot handles disconnect gracefully
- [ ] Large thumbnails display correctly

---

## 13. Migration Notes

For existing users:
1. Update `.env` with Spotify credentials
2. Install new dependencies: `pip install -r requirements.txt`
3. Grant bot "Applications Commands" permission in Discord
4. Update role name if different from "DJ"

---

## Approval

Design approved by user on 2026-03-28.
