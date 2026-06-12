"""
Minimal test bot for audio playback
"""
import sys
sys.path.insert(0, 'C:/Users/TinKan/AppData/Local/Programs/Python/Python313/Lib/site-packages')

import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'Bot ready: {bot.user}')

@bot.command()
async def debug(ctx):
    """Debug voice connection"""
    if not ctx.author.voice:
        return await ctx.send("Join voice channel first!")

    # Connect
    if not ctx.voice_client:
        await ctx.send("Connecting...")
        vc = await ctx.author.voice.channel.connect()
        await asyncio.sleep(1)
    else:
        vc = ctx.voice_client

    await ctx.send(f"Connected: {vc.is_connected()}\nChannel: {vc.channel.name}")

    # Extract audio
    await ctx.send("Extracting audio...")

    import yt_dlp
    ytdl = yt_dlp.YoutubeDL({'format': 'bestaudio', 'quiet': True})
    data = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: ytdl.extract_info("https://www.youtube.com/watch?v=jNQXAC9IVRw", download=False)
    )

    audio_url = data['url']
    await ctx.send(f"Got audio URL ({len(audio_url)} chars)")

    # Create source
    await ctx.send("Creating FFmpegPCMAudio...")

    ffmpeg_path = r'C:\Users\TinKan\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffmpeg.exe'

    try:
        source = discord.FFmpegPCMAudio(
            audio_url,
            executable=ffmpeg_path,
            before_options='-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            options='-vn'
        )
        await ctx.send("FFmpegPCMAudio created")
    except Exception as e:
        return await ctx.send(f"Error creating source: {e}")

    # Play
    await ctx.send("Starting playback...")

    if vc.is_playing():
        vc.stop()
        await asyncio.sleep(0.5)

    vc.play(source)
    await asyncio.sleep(1)

    await ctx.send(f"is_playing: {vc.is_playing()}\nis_paused: {vc.is_paused()}")

    # Wait a bit
    await asyncio.sleep(5)
    await ctx.send(f"After 5s - is_playing: {vc.is_playing()}")

@bot.command()
async def stop(ctx):
    """Stop playback"""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("Stopped")
    else:
        await ctx.send("Not playing")

@bot.command()
async def leave(ctx):
    """Leave voice"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("Left")

if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("DISCORD_TOKEN not set!")
    else:
        print("Starting test bot...")
        print("Commands: !debug, !stop, !leave")
        bot.run(token)
