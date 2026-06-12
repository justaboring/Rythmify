"""
Cross-platform diagnostic script for Discord Music Bot
Supports: Arch Linux, other Linux distros, Windows
"""
import subprocess
import sys
import os
import shutil
import platform
import time

# ── Banner ──────────────────────────────────────────────────────────────────
print("=" * 60)
print("  DISCORD MUSIC BOT — DIAGNOSTIC TOOL")
print("=" * 60)

# ── System Info ─────────────────────────────────────────────────────────────
print("\n[0] System Information")
_system = platform.system()
print(f"  OS         : {_system} {platform.release()}")
print(f"  Python     : {platform.python_version()} ({sys.executable})")
print(f"  Architecture: {platform.machine()}")

# Detect Arch-based
_is_arch = False
if _system == "Linux":
    try:
        with open("/etc/os-release") as _f:
            _os_release = _f.read().lower()
        _arch_ids = {"arch", "cachyos", "manjaro", "endeavouros", "garuda", "artix", "arco", "parabola"}
        for _line in _os_release.splitlines():
            if _line.startswith("id=") or _line.startswith("id_like="):
                _val = _line.split("=", 1)[1].strip().strip('"').strip("'")
                for _tok in _val.replace(",", " ").split():
                    if _tok in _arch_ids:
                        _is_arch = True
                        break
        # Pretty name
        for _line in _os_release.splitlines():
            if _line.startswith("pretty_name="):
                _pretty = _line.split("=", 1)[1].strip().strip('"')
                print(f"  Distro     : {_pretty}" + (" (Arch-based ✓)" if _is_arch else ""))
                break
    except Exception:
        pass

# ── 1. FFmpeg ────────────────────────────────────────────────────────────────
print("\n[1/5] FFmpeg")

# Try to find FFmpeg using the same logic as Config
def _find_ffmpeg():
    env = os.getenv("FFMPEG_PATH", "").strip()
    if env and env.lower() != "auto":
        return env
    found = shutil.which("ffmpeg")
    if found:
        return found
    if _system == "Windows":
        candidates = [
            r'C:\ffmpeg\bin\ffmpeg.exe',
            r'C:\ffmpeg\ffmpeg.exe',
            r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
            r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
            r'C:\tools\ffmpeg\bin\ffmpeg.exe',
            os.path.expanduser(r'~\ffmpeg\bin\ffmpeg.exe'),
        ]
        for p in candidates:
            if os.path.isfile(p):
                return p
    if _system == "Linux":
        for p in ["/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/opt/bin/ffmpeg"]:
            if os.path.isfile(p):
                return p
    return "ffmpeg"

ffmpeg_path = _find_ffmpeg()
print(f"  Path: {ffmpeg_path}")

_ffmpeg_ok = False
try:
    result = subprocess.run(
        [ffmpeg_path, "-version"],
        capture_output=True, text=True, timeout=10
    )
    if result.returncode == 0:
        ver_line = result.stdout.splitlines()[0] if result.stdout else "unknown"
        print(f"  Version: {ver_line}")
        print("  [OK] FFmpeg found and working ✓")
        _ffmpeg_ok = True
    else:
        print(f"  [FAIL] FFmpeg returned error code {result.returncode}")
        print(f"  Stderr: {result.stderr[:200]}")
except FileNotFoundError:
    print("  [FAIL] FFmpeg not found in PATH or known locations!")
    if _system == "Linux":
        if _is_arch:
            print("  → Install with: sudo pacman -S ffmpeg")
        else:
            print("  → Install with: sudo apt install ffmpeg  (Debian/Ubuntu)")
            print("                  sudo dnf install ffmpeg  (Fedora)")
    elif _system == "Windows":
        print("  → Install with: winget install Gyan.FFmpeg")
        print("             or: choco install ffmpeg")
        print("             or: Download from https://www.gyan.dev/ffmpeg/builds/")
except Exception as e:
    print(f"  [FAIL] FFmpeg error: {e}")

# ── 2. YouTube Extraction ────────────────────────────────────────────────────
print("\n[2/5] YouTube Extraction (yt-dlp)")
try:
    import yt_dlp
    print(f"  yt-dlp version: {yt_dlp.version.__version__}")
    ytdl = yt_dlp.YoutubeDL({'format': 'bestaudio/best', 'quiet': True})
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    data = ytdl.extract_info(test_url, download=False)
    if 'entries' in data:
        data = data['entries'][0]
    audio_url = data['url']
    print(f"  Title   : {data.get('title', 'Unknown')}")
    print(f"  Protocol: {data.get('protocol', 'unknown')}")
    print(f"  URL len : {len(audio_url)} chars")
    print("  [OK] YouTube extraction working ✓")
    _yt_ok = True
except ImportError:
    print("  [FAIL] yt-dlp not installed! Run: pip install yt-dlp")
    _yt_ok = False
    audio_url = None
except Exception as e:
    print(f"  [FAIL] Extraction failed: {e}")
    _yt_ok = False
    audio_url = None

# ── 3. FFmpeg with Audio URL ─────────────────────────────────────────────────
print("\n[3/5] FFmpeg Audio Stream Test")
if not _ffmpeg_ok:
    print("  [SKIP] FFmpeg not available, skipping stream test")
elif not _yt_ok or not audio_url:
    print("  [SKIP] No audio URL available, skipping stream test")
else:
    cmd = [
        ffmpeg_path,
        '-reconnect', '1', '-reconnect_streamed', '1', '-reconnect_delay_max', '5',
        '-i', audio_url,
        '-vn', '-f', 's16le', '-ar', '48000', '-ac', '2',
        'pipe:1'
    ]
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        time.sleep(3)  # Give FFmpeg time to connect and buffer
        stderr_data = b''
        try:
            stderr_data = process.stderr.read1(4096) if hasattr(process.stderr, 'read1') else process.stderr.read(4096)
        except Exception:
            pass
        if stderr_data:
            stderr_text = stderr_data.decode('utf-8', errors='ignore')
            if 'error' in stderr_text.lower() and 'connection' not in stderr_text.lower():
                print(f"  FFmpeg stderr: {stderr_text[:300]}")
        if process.poll() is None:
            print("  [OK] FFmpeg streaming audio successfully ✓")
            process.terminate()
        else:
            print(f"  [FAIL] FFmpeg exited early (code: {process.returncode})")
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        print("  [OK] FFmpeg stream test complete (process terminated after timeout) ✓")
    except Exception as e:
        print(f"  [FAIL] Stream test failed: {e}")

# ── 4. Python Dependencies ───────────────────────────────────────────────────
print("\n[4/5] Python Dependencies")

deps = [
    ("discord",        "discord.py",         None),
    ("yt_dlp",         "yt-dlp",             None),
    ("dotenv",         "python-dotenv",      None),
    ("nacl",           "PyNaCl (voice)",     None),
    ("aiohttp",        "aiohttp",            None),
    ("ytmusicapi",     "ytmusicapi",         None),
    ("spotipy",        "spotipy",            None),
]

_all_ok = True
for module, label, _ in deps:
    try:
        mod = __import__(module)
        # discord.py exposes version via discord.__version__
        if module == "discord":
            ver = getattr(mod, '__version__', '?')
        elif module == "yt_dlp":
            ver = getattr(mod.version, '__version__', '?')
        else:
            ver = getattr(mod, '__version__', '?')
        print(f"  [OK] {label:<22} {ver}")
    except ImportError as e:
        print(f"  [MISS] {label:<21} NOT INSTALLED  ({e})")
        _all_ok = False

# Special: check opus (needed for voice)
try:
    import discord
    if discord.opus.is_loaded():
        print("  [OK] Opus loaded (system)      ✓")
    else:
        # Try to load manually — common library names per OS
        _opus_names = []
        if _system == "Linux":
            _opus_names = ["libopus.so.0", "libopus.so", "opus"]
        elif _system == "Windows":
            _opus_names = ["opus", "libopus-0"]
        _opus_loaded = False
        for _oname in _opus_names:
            try:
                discord.opus.load_opus(_oname)
                if discord.opus.is_loaded():
                    print(f"  [OK] Opus loaded ({_oname})   ✓")
                    _opus_loaded = True
                    break
            except Exception:
                continue
        if not _opus_loaded:
            print("  [WARN] Opus not loaded — voice may not work")
            if _is_arch:
                print("         Install: sudo pacman -S opus")
            elif _system == "Linux":
                print("         Install: sudo apt install libopus0")
            elif _system == "Windows":
                print("         PyNaCl usually bundles Opus. Try: pip install -U PyNaCl")
except Exception as e:
    print(f"  [WARN] Opus check: {e}")

# ── 5. Package Manager Check (Arch/Windows only) ─────────────────────────────
print("\n[5/5] System Package Manager")
if _is_arch:
    _pacman = shutil.which("pacman")
    if _pacman:
        print(f"  [OK] pacman found: {_pacman}")
        # Check if ffmpeg is installed via pacman
        try:
            r = subprocess.run(["pacman", "-Q", "ffmpeg"], capture_output=True, text=True)
            if r.returncode == 0:
                print(f"  [OK] ffmpeg via pacman: {r.stdout.strip()}")
            else:
                print("  [INFO] ffmpeg not installed via pacman (may be in PATH another way)")
        except Exception:
            pass
    else:
        print("  [WARN] pacman not found")
elif _system == "Windows":
    _winget = shutil.which("winget")
    _choco  = shutil.which("choco")
    if _winget:
        print(f"  [OK] winget found: {_winget}")
    if _choco:
        print(f"  [OK] Chocolatey found: {_choco}")
    if not _winget and not _choco:
        print("  [INFO] No package manager detected (winget/choco). FFmpeg must be installed manually.")
elif _system == "Linux":
    for pm in ["apt", "dnf", "zypper", "pacman"]:
        found = shutil.which(pm)
        if found:
            print(f"  [OK] Package manager: {pm} ({found})")
            break

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  DIAGNOSTIC COMPLETE")
print("=" * 60)

if not _ffmpeg_ok:
    print("\n⚠️  FFmpeg is missing — the bot CANNOT play audio without it.")
    if _is_arch:
        print("   Fix: sudo pacman -S ffmpeg")
    elif _system == "Linux":
        print("   Fix: sudo apt install ffmpeg")
    elif _system == "Windows":
        print("   Fix: winget install Gyan.FFmpeg")

if not _all_ok:
    print("\n⚠️  Some Python packages are missing.")
    print("   Fix: pip install -r requirements.txt")

if _ffmpeg_ok and _yt_ok and _all_ok:
    print("\n✅ Everything looks good! Run the bot with:")
    if _system == "Windows":
        print("   run_bot.bat")
    else:
        print("   ./run_bot.sh")
