# 🎵 Gratify — Discord Music Bot (yt-dlp)

A simple, educational Discord music bot that plays from YouTube via **yt-dlp**. Built for learning — clean code, minimal dependencies, no Java/Lavalink required.

## Features

- 🎵 **Play music** from YouTube (URL/search) via yt-dlp
- 🎧 **YouTube Music** — search, playlists, artist radio
- 🔊 **SoundCloud** support
- 🎤 **Lyrics** lookup via lyrics.ovh
- 📋 **Queue** — loop, shuffle, move, remove
- ⏭️ **Skip vote** + DJ force skip
- 🎛️ **Volume control**
- 📢 **Song request channel** — auto-play from text channel
- 🛡️ **Rate limiter** — prevents spam
- 📝 **Audit log** — tracks command usage
- 🔁 **Autoplay / radio mode**
- 🎚️ **Persistent control panel** (`/controlpanel`)
- 🎚️ **Audio quality presets** — low/medium/high/lossless
- 💾 **Backup/restore** — save and restore bot data

## Why yt-dlp (not Lavalink)?

No Java. No Lavalink server. Just Python + yt-dlp. Perfect for learning how Discord music bots work at the foundation level. If you want a more advanced version with Lavalink, check out the private fork ([RHYTHMIFY](https://github.com/justaboring/RHYTHMIFY)).

## Quick Start

```bash
# 1. Install FFmpeg
sudo pacman -S ffmpeg       # Arch
sudo apt install ffmpeg      # Debian/Ubuntu

# 2. Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Config
cp .env.example .env
nano .env    # paste your DISCORD_TOKEN

# 4. Run
python bot.py
```

## Commands

### Playback
| Command | Description |
|---------|-------------|
| `/play <query>` | Play from YouTube (URL/search) |
| `/ytmusic <query>` | Play via YouTube Music |
| `/soundcloud <query>` | Play from SoundCloud |
| `/search <query>` | Search & choose |
| `/lyrics [query]` | Get lyrics for current song |
| `/pause` / `/resume` | Pause / Resume |
| `/skip` / `/forceskip` | Vote / Force skip |
| `/stop` | Stop & clear queue |
| `/nowplaying` | Current song info |
| `/volume <0-100>` | Set volume |
| `/loop <off/one/all>` | Loop modes |
| `/crossfade <seconds>` | Enable/disable crossfade |
| `/filter <mode>` | Apply audio filter (bassboost/nightcore/etc.) |
| `/quality [preset]` | Set/check audio quality (DJ) |

### Queue Management
| Command | Description |
|---------|-------------|
| `/queue` | View queue |
| `/shuffle` | Shuffle queue |
| `/remove <pos>` | Remove from queue |
| `/move <from> <to>` | Move queue position |
| `/clear` | Clear queue |

### Utility
| Command | Description |
|---------|-------------|
| `/controlpanel` | Toggle persistent control panel |
| `/setrequestchannel` | Set auto-play channel |
| `/join` / `/leave` | Join/Leave voice channel |
| `/help` | Show all commands |

### Admin/DJ
| Command | Description |
|---------|-------------|
| `/backup` / `/restore` | Backup/restore bot data |
| `/restart` / `/shutdown` | Owner restart/shutdown |

## Architecture

```
├── bot.py                      # Main bot (~1800 lines)
├── config.py                   # Env-based configuration
├── music_player.py             # yt-dlp audio playback engine
├── ytmusic_module.py           # YouTube Music integration
├── soundcloud_module.py        # SoundCloud integration
├── admin_module.py             # DJ permissions, skip votes
├── command_rate_limiter.py     # Per-user rate limiting
├── audit_log.py                # Command usage tracking
├── backup_restore.py           # Backup/restore management
├── ui_components.py            # Discord UI views
├── quality_store.py            # Per-guild audio quality settings
├── playlist_store.py           # User playlist storage
├── panel_store.py              # Control panel state
├── request_channel_store.py    # Auto-play channel config
├── recommendation_engine.py    # Dashboard recommendations
├── stats_store.py              # Usage statistics
└── requirements.txt
```

## Requirements

- Python 3.10+
- FFmpeg 4.0+
- Discord Bot Token ([create here](https://discord.com/developers/applications))

## License

MIT — free to use, modify, and learn from.
