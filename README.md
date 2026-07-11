# 🤖 Discord Music Bot (Rythmify)

Discord bot that plays music from YouTube directly in voice channels.
Supports: **Arch Linux** (primary), other Linux distributions, and **Windows**.

---

## ✨ Features

- 🎵 Play from YouTube (URL / search query)
- 🎧 YouTube Music search (`/ytmusic`, `/ytmusic_search`)
- 📋 Queue system with loop, shuffle, move
- ⏭️ Skip vote + force skip (DJ)
- ⏸️ Pause / Resume / Stop
- 🔊 Volume control
- 📻 Artist radio & mood playlists
- 🎚️ Persistent control panel (`/controlpanel`)
- 📢 Song request channel
- 🔁 Autoplay (radio mode)
- 🎧 **Spotify Connect** — Link your Spotify account (`/spotify_connect`, `/spotify_token`, `/spotify_disconnect`, `/spotify_status`)
- ⏳ **Command Rate Limiter** — Token-bucket per-user per-command, configurable via env
- 📝 **Audit Log** — Track command usage to `audit_log.json` (auto-rotating)
- 🎮 **Game Save Guardian** — `gamesave.sh` snapshots runtime state into dated archives
- 🖥️ **Upgraded Dashboard** — Dark theme with gold accents, toast notifications, keyboard shortcuts

---

## 🛠️ Prerequisites

| Requirement | Minimum Version |
|-------------|-----------------|
| Python      | 3.10+           |
| FFmpeg      | 4.0+            |
| Discord Bot Token | —       |

---

## 📦 Install FFmpeg

### 🐧 Arch Linux / Manjaro / EndeavourOS / Garuda

```bash
sudo pacman -S ffmpeg
```

FFmpeg will automatically be in PATH, the bot will detect it immediately.

### 🐧 Debian / Ubuntu / Linux Mint

```bash
sudo apt update && sudo apt install ffmpeg
```

### 🐧 Fedora / RHEL

```bash
sudo dnf install ffmpeg
```

### 🪟 Windows — via winget (Windows 10/11 built-in)

```powershell
winget install Gyan.FFmpeg
```

### 🪟 Windows — via Chocolatey

```powershell
choco install ffmpeg
```

### 🪟 Windows — Manual

1. Download from https://www.gyan.dev/ffmpeg/builds/ (choose `ffmpeg-release-full`)
2. Extract to `C:\ffmpeg\`
3. Add `C:\ffmpeg\bin\` to Environment Variable PATH  
   *Or* set `FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe` in the `.env` file

---

## 🚀 Setup & Installation

### Quick Start — Use Automatic Script

**Arch Linux / Manjaro / EndeavourOS:**
```bash
chmod +x install_arch.sh
./install_arch.sh
```

**Windows:**
```
install_windows.bat  (double-click or run in CMD)
```

---

### Manual Setup

#### 1. Clone / download repo

```bash
git clone <repo-url>
cd discord-music-bot
```

#### 2. Create Python virtual environment

**Linux:**
```bash
python -m venv .venv
source .venv/bin/activate
```

**Windows:**
```bat
python -m venv .venv
.venv\Scripts\activate
```

> ⚠️ **Arch Linux**: venv is **required** because PEP 668 prohibits `pip install` directly to system Python.

#### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

#### 4. Setup .env

```bash
cp .env.example .env
```

Edit `.env` and fill in the bot token:

```env
DISCORD_TOKEN=your_discord_bot_token
```

#### 5. Get Discord Bot Token

1. Open [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** → give it a name
3. Go to **Bot** tab → click **Reset Token** → copy the token
4. Enable:
   - ✅ **MESSAGE CONTENT INTENT**
   - ✅ **SERVER MEMBERS INTENT**

#### 6. Invite Bot to Server

1. Go to **OAuth2** tab → **URL Generator**
2. Scopes: `bot`, `applications.commands`
3. Permissions: `Send Messages`, `Connect`, `Speak`, `Embed Links`, `Read Message History`, `Use Voice Activity`
4. Open the URL in your browser → select your server

---

## ▶️ Run the Bot

**Linux:**
```bash
./run_bot.sh
```

**Windows:**
```
run_bot.bat  (double-click)
```

**Manual (after activating venv):**
```bash
python bot.py
```

---

## 🔍 Diagnostics

Check if all dependencies are correct:

**Linux:**
```bash
source .venv/bin/activate
python diagnose.py
```

**Windows:**
```bat
.venv\Scripts\python diagnose.py
```

---

## 📝 Slash Commands

| Command | Description |
|---------|-------------|
| `/play <query>` | Play from YouTube (URL / search) |
| `/ytmusic <query>` | Play via YouTube Music (more accurate) |
| `/ytmusic_search` | Search YT Music, choose from results |
| `/artist <name>` | Artist radio from YT Music |
| `/mood <mood>` | Play by mood (chill, party, sad...) |
| `/ytplaylist <id>` | Load public YT Music playlist |
| `/search <query>` | Search YouTube, choose from results |
| `/soundcloud <query>` | SoundCloud — play first result |
| `/soundcloud_search` | SoundCloud — choose from results |
| `/loop <mode>` | Loop: off / one / all |
| `/pause` | Pause |
| `/resume` | Resume |
| `/skip` | Vote to skip |
| `/forceskip` | Skip immediately (DJ only) |
| `/stop` | Stop & clear queue (DJ only) |
| `/queue` | View queue |
| `/nowplaying` | Current song info |
| `/volume <0-100>` | Set volume |
| `/remove <pos>` | Remove song from queue (DJ only) |
| `/move <from> <to>` | Move song position (DJ only) |
| `/shuffle` | Shuffle queue (DJ only) |
| `/clear` | Clear queue (DJ only) |
| `/join` | Join voice channel |
| `/leave` | Leave voice channel (DJ only) |
| `/setrequestchannel` | Set song request channel (DJ/Admin) |
| `/controlpanel` | Toggle persistent music panel (DJ/Admin) |
| `/help` | Show all commands |
| **New — Spotify Connect** ||
| `/spotify_connect` | Link your Spotify account (OAuth) |
| `/spotify_token` | Complete OAuth verification |
| `/spotify_disconnect` | Unlink Spotify account |
| `/spotify_status` | Check connection status |

---

## ⚙️ .env Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DISCORD_TOKEN` | — | **Required**. Discord bot token |
| `FFMPEG_PATH` | auto | Path to ffmpeg. Leave empty / set to `auto` for auto-detection |
| `DJ_ROLE_NAME` | `DJ` | Name of DJ role on the server |
| `SKIP_VOTE_THRESHOLD` | `50` | % of votes needed to skip (50 = 50%) |
| `MAX_QUEUE_SIZE` | `100` | Maximum songs in queue |
| `DEFAULT_VOLUME` | `50` | Default volume (0-100) |
| `SSL_VERIFY` | `true` | Set to `false` if you have SSL errors |
| `RATE_LIMIT_ENABLED` | `true` | Enable/disable command rate limiter |
| `RATE_LIMIT_TOKENS` | `5` | Max burst of same command per window |
| `RATE_LIMIT_REFILL_RATE` | `1` | Tokens added per refill period |
| `RATE_LIMIT_REFILL_SECONDS` | `5` | Refill period in seconds |
| `AUDIT_LOG_PATH` | `audit_log.json` | Path for command audit log |
| `AUDIT_LOG_MAX_SIZE` | `10485760` | Max audit log size (bytes) before rotation |
| `SPOTIFY_REDIRECT_URI` | `http://localhost:8889/callback` | OAuth callback URI |

---

## ⚠️ Troubleshooting

### `FFmpeg not found`
- **Arch**: `sudo pacman -S ffmpeg`
- **Windows**: `winget install Gyan.FFmpeg` then restart terminal
- Or set manually in `.env`: `FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe`

### Bot not responding to slash commands
- Make sure the bot was invited with `applications.commands` scope
- Wait 1-2 minutes after bot goes online for commands to sync

### No audio / bot muted
- Check bot has **Speak** permission in voice channel
- Check volume: `/volume 50`
- Run `python diagnose.py` to check FFmpeg & dependencies

### Error during installation on Arch Linux
```bash
# If pip error due to PEP 668, make sure to use venv:
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'nacl'`
```bash
pip install PyNaCl
```
Voice won't work without PyNaCl.

### Update yt-dlp (if YouTube suddenly stops working)
```bash
pip install -U yt-dlp
```

---

## 📝 Notes

- Bot for personal/educational use
- Respect YouTube and Discord Terms of Service
- Don't spam `/play` to avoid rate limits

## 📄 License

MIT License — free to use and modify.
