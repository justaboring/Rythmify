# 🎵 Discord Music Bot (Rythmify)

Bot Discord yang memutar musik dari YouTube langsung di voice channel.  
Mendukung: **Arch Linux** (utama), Linux lain, dan **Windows**.

---

## ✨ Fitur

- 🎵 Play dari YouTube (URL / search query)
- 🎧 YouTube Music search (`/ytmusic`, `/ytmusic_search`)
- 📋 Queue system dengan loop, shuffle, move
- ⏭️ Skip vote + force skip (DJ)
- ⏸️ Pause / Resume / Stop
- 🔊 Volume control
- 📻 Artist radio & mood playlist
- 🎚️ Persistent control panel (`/controlpanel`)
- 📢 Song request channel
- 🔁 Autoplay (radio mode)

---

## 🛠️ Prerequisites

| Kebutuhan | Versi Minimum |
|-----------|---------------|
| Python    | 3.10+         |
| FFmpeg    | 4.0+          |
| Discord Bot Token | — |

---

## 📦 Install FFmpeg

### 🐧 Arch Linux / Manjaro / EndeavourOS / Garuda

```bash
sudo pacman -S ffmpeg
```

FFmpeg otomatis masuk ke PATH, bot langsung detect.

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

1. Download dari https://www.gyan.dev/ffmpeg/builds/ (pilih `ffmpeg-release-full`)
2. Extract ke `C:\ffmpeg\`
3. Tambah `C:\ffmpeg\bin\` ke Environment Variable PATH  
   *atau* set `FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe` di file `.env`

---

## 🚀 Setup & Instalasi

### Cara Cepat — Pakai Script Otomatis

**Arch Linux / Manjaro / EndeavourOS:**
```bash
chmod +x install_arch.sh
./install_arch.sh
```

**Windows:**
```
install_windows.bat  (double-click atau jalankan di CMD)
```

---

### Cara Manual

#### 1. Clone / download repo

```bash
git clone <repo-url>
cd discord-music-bot
```

#### 2. Buat Python virtual environment

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

> ⚠️ **Arch Linux**: venv **wajib** karena PEP 668 melarang `pip install` langsung ke system Python.

#### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

#### 4. Setup .env

```bash
cp .env.example .env
```

Edit `.env` dan isi token bot:

```env
DISCORD_TOKEN=token_discord_bot_kamu
```

#### 5. Dapatkan Discord Bot Token

1. Buka [Discord Developer Portal](https://discord.com/developers/applications)
2. Klik **New Application** → beri nama
3. Tab **Bot** → klik **Reset Token** → copy token
4. Aktifkan:
   - ✅ **MESSAGE CONTENT INTENT**
   - ✅ **SERVER MEMBERS INTENT**

#### 6. Invite Bot ke Server

1. Tab **OAuth2** → **URL Generator**
2. Scopes: `bot`, `applications.commands`
3. Permissions: `Send Messages`, `Connect`, `Speak`, `Embed Links`, `Read Message History`, `Use Voice Activity`
4. Buka URL di browser → pilih server

---

## ▶️ Jalankan Bot

**Linux:**
```bash
./run_bot.sh
```

**Windows:**
```
run_bot.bat  (double-click)
```

**Manual (setelah activate venv):**
```bash
python bot.py
```

---

## 🔍 Diagnostik

Cek apakah semua dependency sudah bener:

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

| Command | Deskripsi |
|---------|-----------|
| `/play <query>` | Play dari YouTube (URL / search) |
| `/ytmusic <query>` | Play via YouTube Music (lebih akurat) |
| `/ytmusic_search` | Search YT Music, pilih dari hasil |
| `/artist <name>` | Artist radio dari YT Music |
| `/mood <mood>` | Play by mood (chill, party, sad…) |
| `/ytplaylist <id>` | Load YouTube Music playlist |
| `/search <query>` | Search YouTube, pilih dari hasil |
| `/soundcloud <query>` | SoundCloud — play hasil pertama |
| `/soundcloud_search` | SoundCloud — pilih dari hasil |
| `/loop <mode>` | Loop: off / one / all |
| `/pause` | Pause |
| `/resume` | Resume |
| `/skip` | Vote skip |
| `/forceskip` | Skip langsung (DJ only) |
| `/stop` | Stop & clear queue (DJ only) |
| `/queue` | Lihat antrian |
| `/nowplaying` | Info lagu sekarang |
| `/volume <0-100>` | Set volume |
| `/remove <pos>` | Hapus lagu dari queue (DJ only) |
| `/move <from> <to>` | Pindah posisi lagu (DJ only) |
| `/shuffle` | Acak queue (DJ only) |
| `/clear` | Hapus semua queue (DJ only) |
| `/join` | Join voice channel |
| `/leave` | Leave voice channel (DJ only) |
| `/setrequestchannel` | Set channel request lagu |
| `/controlpanel` | Toggle panel kontrol permanen |
| `/help` | Tampilkan semua command |

---

## ⚙️ Konfigurasi `.env`

| Variable | Default | Keterangan |
|----------|---------|------------|
| `DISCORD_TOKEN` | — | **Wajib**. Token bot Discord |
| `FFMPEG_PATH` | auto | Path ke ffmpeg. Kosongkan / isi `auto` untuk auto-detect |
| `DJ_ROLE_NAME` | `DJ` | Nama role DJ di server |
| `SKIP_VOTE_THRESHOLD` | `50` | % vote untuk skip (50 = 50%) |
| `MAX_QUEUE_SIZE` | `100` | Maksimum lagu dalam queue |
| `DEFAULT_VOLUME` | `50` | Volume default (0-100) |
| `SSL_VERIFY` | `true` | Set `false` jika ada SSL error |

---

## ⚠️ Troubleshooting

### `FFmpeg not found`
- **Arch:** `sudo pacman -S ffmpeg`
- **Windows:** `winget install Gyan.FFmpeg` lalu restart terminal
- Atau set manual di `.env`: `FFMPEG_PATH=C:\ffmpeg\bin\ffmpeg.exe`

### Bot tidak merespons slash command
- Pastikan bot sudah di-invite dengan scope `applications.commands`
- Tunggu 1-2 menit setelah bot online untuk command sync

### No audio / bot mute
- Cek bot punya permission **Speak** di voice channel
- Cek volume: `/volume 50`
- Jalankan `python diagnose.py` untuk cek FFmpeg & dependencies

### Error saat install di Arch Linux
```bash
# Jika pip error karena PEP 668, pastikan pakai venv:
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### `ModuleNotFoundError: No module named 'nacl'`
```bash
pip install PyNaCl
```
Voice tidak akan jalan tanpa PyNaCl.

### Update yt-dlp (jika YouTube tiba-tiba error)
```bash
pip install -U yt-dlp
```

---

## 📝 Notes

- Bot untuk personal/educational use
- Respect ToS YouTube dan Discord
- Jangan spam `/play` untuk hindari rate limit

## 📄 License

MIT License — bebas dipakai dan dimodifikasi.
