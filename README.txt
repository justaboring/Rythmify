# 🤖 Discord Music Bot

Bot Discord yang bisa memutar musik dari YouTube langsung di voice channel server Discord kamu.

## ✨ Fitur

- 🎵 Play musik dari YouTube (URL atau search)
- 📋 Queue system (bisa antriin banyak lagu)
- ⏭️ Skip lagu
- ⏸️ Pause & Resume
- 🔊 Volume control
- 📊 Now playing info dengan thumbnail

## 🛠️ Prerequisites

1. **Python 3.8+** - Download di [python.org](https://python.org)
2. **FFmpeg** - Download di [ffmpeg.org](https://ffmpeg.org/download.html) atau pakai package manager
3. **Discord Bot Token** - Buat di [Discord Developer Portal](https://discord.com/developers/applications)

## 📦 Install FFmpeg

### Windows (pakai Chocolatey):
```bash
choco install ffmpeg
```

### Windows (manual):
1. Download dari https://www.gyan.dev/ffmpeg/builds/
2. Extract ke folder (contoh: `C:\ffmpeg`)
3. Tambah ke PATH environment variable

### Mac:
```bash
brew install ffmpeg
```

### Linux:
```bash
sudo apt-get install ffmpeg
```

## 🚀 Setup Bot

### 1. Clone/download repository ini

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Setup environment variables
1. Copy file `.env.example` jadi `.env`
2. Edit `.env` dan masukin token Discord bot kamu:
```
DISCORD_TOKEN=MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNA.Example.Token
```

### 4. Dapatkan Discord Bot Token

1. Buka [Discord Developer Portal](https://discord.com/developers/applications)
2. Klik "New Application"
3. Beri nama bot kamu
4. Pergi ke tab "Bot" di sidebar
5. Klik "Reset Token" atau copy token yang ada
6. **PASTIKAN** nyalain toggle:
   - ☑️ MESSAGE CONTENT INTENT (di tab "Bot")

### 5. Invite Bot ke Server

1. Di Discord Developer Portal, pergi ke tab "OAuth2" → "URL Generator"
2. Pilih scopes: `bot`
3. Pilih permissions:
   - Send Messages
   - Connect
   - Speak
   - Read Message History
   - Add Reactions
   - Embed Links
   - Use Voice Activity
4. Copy URL yang muncul dan buka di browser
5. Pilih server Discord kamu dan invite

## ▶️ Run Bot

```bash
python bot.py
```

## 📝 Commands

Prefix: `!`

| Command | Deskripsi |
|---------|-----------|
| `!play <judul/url>` | Putar lagu dari YouTube |
| `!skip` | Skip lagu sekarang |
| `!pause` | Pause musik |
| `!resume` | Lanjutkan musik |
| `!stop` | Stop musik & hapus queue |
| `!queue` | Lihat daftar antrian |
| `!nowplaying` | Lihat lagu yang diputar |
| `!volume <0-100>` | Atur volume |
| `!join` | Join voice channel |
| `!leave` | Keluar dari voice channel |
| `!help` | Tampilkan bantuan |

## 📌 Contoh Penggunaan

```
!play shape of you
!play https://youtube.com/watch?v=...
!skip
!volume 75
!queue
```

## ⚠️ Troubleshooting

**"FFmpeg not found"**
- Pastikan FFmpeg sudah terinstall dan ada di PATH

**"Bot gak respon"**
- Cek token Discord sudah benar
- Pastikan MESSAGE CONTENT INTENT sudah diaktifkan

**"Gak bisa join voice"**
- Pastikan bot punya permission Connect & Speak

**"Error saat play"**
- Cek internet connection
- Coba update yt-dlp: `pip install -U yt-dlp`

## 📝 Notes

- Bot ini hanya untuk personal/educational use
- Respect copyright dan ToS Discord
- Jangan spam play biar gak kena rate limit

## 🐛 Bug Report

Kalau ada masalah, cek:
1. FFmpeg sudah terinstall dengan benar
2. Token Discord valid
3. Dependencies sudah di-install: `pip install -r requirements.txt`

## 📄 License

MIT License - Bebas dipake dan dimodifikasi.
