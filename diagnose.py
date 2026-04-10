"""
Full diagnostic script for audio playback
"""
import subprocess
import sys
import os

# Add site-packages to path
sys.path.insert(0, 'C:/Users/TinKan/AppData/Local/Programs/Python/Python313/Lib/site-packages')

import yt_dlp
import shutil
import time

print("=" * 60)
print("DISCORD MUSIC BOT DIAGNOSTIC")
print("=" * 60)

# Test 1: FFmpeg
print("\n[1/4] Testing FFmpeg...")
ffmpeg_path = r'C:\FFMPEG\ffmpeg.exe'

if not os.path.exists(ffmpeg_path):
    ffmpeg_path = shutil.which('ffmpeg')

print(f"  Path: {ffmpeg_path}")
print(f"  Exists: {os.path.exists(ffmpeg_path) if ffmpeg_path else False}")

try:
    result = subprocess.run([ffmpeg_path, '-version'], capture_output=True, text=True)
    print(f"  Version: {result.stdout.splitlines()[0] if result.stdout else 'Unknown'}")
    print("  [OK] FFmpeg working")
except Exception as e:
    print(f"  [FAIL] FFmpeg error: {e}")
    sys.exit(1)

# Test 2: YouTube extraction
print("\n[2/4] Testing YouTube audio extraction...")
test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

ytdl_opts = {
    'format': 'bestaudio/best',
    'quiet': True,
}
ytdl = yt_dlp.YoutubeDL(ytdl_opts)

try:
    data = ytdl.extract_info(test_url, download=False)
    if 'entries' in data:
        data = data['entries'][0]

    audio_url = data['url']
    title = data.get('title', 'Unknown')
    protocol = data.get('protocol', 'unknown')

    print(f"  Title: {title}")
    print(f"  Protocol: {protocol}")
    print(f"  URL length: {len(audio_url)}")
    print("  [OK] Extraction working")
except Exception as e:
    print(f"  [FAIL] Extraction failed: {e}")
    sys.exit(1)

# Test 3: FFmpeg with audio URL
print("\n[3/4] Testing FFmpeg with audio URL...")

cmd = [
    ffmpeg_path,
    '-reconnect', '1',
    '-reconnect_streamed', '1',
    '-reconnect_delay_max', '5',
    '-i', audio_url,
    '-vn',
    '-f', 's16le',
    '-ar', '48000',
    '-ac', '2',
    'pipe:1'
]

try:
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Wait for data
    time.sleep(2)

    # Read stderr
    stderr_data = process.stderr.read1(4096) if hasattr(process.stderr, 'read1') else process.stderr.read(4096)

    if stderr_data:
        stderr_text = stderr_data.decode('utf-8', errors='ignore')
        if 'error' in stderr_text.lower():
            print(f"  FFmpeg errors detected:")
            print(f"  {stderr_text[:500]}")
        else:
            print(f"  FFmpeg stderr (info only):")
            print(f"  {stderr_text[:200]}...")

    # Check if process is still running
    if process.poll() is None:
        print("  [OK] FFmpeg is running with audio URL")
        process.terminate()
    else:
        return_code = process.returncode
        print(f"  [FAIL] FFmpeg exited early (code: {return_code})")

    process.wait(timeout=2)

except Exception as e:
    print(f"  [FAIL] FFmpeg test failed: {e}")
    import traceback
    traceback.print_exc()

# Test 4: Check Discord dependencies
print("\n[4/4] Checking Discord dependencies...")
try:
    import discord
    print(f"  discord.py version: {discord.__version__}")

    # Check voice support
    try:
        import discord.opus
        print("  [OK] Opus support available")
    except Exception as e:
        print(f"  [WARN] Opus error: {e}")

    print("  [OK] Discord.py working")
except Exception as e:
    print(f"  [FAIL] Discord error: {e}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)
print("\nIf all tests passed but bot still has no audio:")
print("1. Check bot has permission to speak in voice channel")
print("2. Check Windows volume mixer for the Python process")
print("3. Try using /volume 50 command to ensure volume is up")
print("4. Check if bot is muted/deafened in Discord")
