import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os

from config import Config
from music_player import (
    YTDLSource, GuildMusicState, get_guild_state,
    cleanup_guild_state, play_next_song
)
from soundcloud_module import SoundCloudClient, soundcloud_to_youtube_query
from admin_module import is_dj, can_skip, SkipVoteManager, remove_from_queue, move_in_queue, shuffle_queue, clear_queue
from ui_components import (
    NowPlayingView, QueueView, SkipVoteView, SongSelectView,
    create_now_playing_embed, create_queue_embed, create_added_embed,
    ControlPanelView, create_control_panel_embed, create_dashboard_embed
)
from panel_store import get_panel, set_panel, clear_panel
from request_channel_store import get_request_channel, set_request_channel, clear_request_channel
from utils import parse_spotify_url, is_url
from ytmusic_module import (
    search_songs, search_videos, get_artist_radio,
    get_song_radio, get_mood_playlists, get_mood_tracks,
    get_playlist_tracks, track_to_source_data
)
from spotify_module import SpotifyClient

Config.setup_ssl()
Config.validate()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

soundcloud_client = SoundCloudClient()
spotify_client = SpotifyClient(Config.SPOTIFY_CLIENT_ID, Config.SPOTIFY_CLIENT_SECRET)


def handle_spotify_urls_sync(query: str) -> list:
    match = parse_spotify_url(query)
    if not match:
        return []
    url_type, spotify_id = match
    if url_type == 'track':
        q = spotify_client.get_track_query(spotify_id)
        return [q] if q else []
    elif url_type == 'playlist':
        return spotify_client.get_playlist_queries(spotify_id)
    elif url_type == 'album':
        return spotify_client.get_album_queries(spotify_id)
    return []



# ──────────────────────────────────────────────
# PANEL HELPERS
# ──────────────────────────────────────────────

async def get_panel_message(guild: discord.Guild):
    info = get_panel(guild.id)
    if not info:
        return None
    try:
        channel = guild.get_channel(info["channel_id"])
        if not channel:
            return None
        return await channel.fetch_message(info["message_id"])
    except Exception:
        return None


async def refresh_panel(guild: discord.Guild, guild_state):
    msg = await get_panel_message(guild)
    if not msg:
        return
    embed = create_control_panel_embed(guild_state)
    view  = ControlPanelView(MusicCog(bot), guild_state, timeout=None)
    try:
        await msg.edit(embed=embed, view=view)
    except Exception:
        pass


# ──────────────────────────────────────────────
# VOICE HELPERS
# ──────────────────────────────────────────────

async def ensure_voice(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)
        return None

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await interaction.user.voice.channel.connect()
        await asyncio.sleep(1)
    elif voice_client.channel != interaction.user.voice.channel:
        await interaction.response.send_message("❌ Bot is in a different voice channel!", ephemeral=True)
        return None

    return voice_client


# ──────────────────────────────────────────────
# MUSIC COG
# ──────────────────────────────────────────────

class MusicCog:
    def __init__(self, bot):
        self.bot = bot

    async def dashboard_callback(self, interaction: discord.Interaction):
        guild_state  = get_guild_state(interaction.guild_id)
        voice_client = interaction.guild.voice_client
        embed = create_dashboard_embed(guild_state, voice_client=voice_client, guild=interaction.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def pause_callback(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        guild_state  = get_guild_state(interaction.guild_id)

        if not voice_client or (not voice_client.is_playing() and not voice_client.is_paused()):
            return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

        if voice_client.is_paused():
            voice_client.resume()
            guild_state.is_paused = False
            await interaction.response.send_message("▶️ Resumed!", ephemeral=True)
        else:
            voice_client.pause()
            guild_state.is_paused = True
            await interaction.response.send_message("⏸️ Paused!", ephemeral=True)

        await refresh_panel(interaction.guild, guild_state)

    async def skip_callback(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.is_playing():
            return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)

        if is_dj(interaction.user):
            await interaction.response.send_message("⏭️ Skipped by DJ!", ephemeral=True)
            voice_client.stop()
        else:
            added, vote_message = SkipVoteManager.add_vote(interaction.user.id, guild_state)
            if not added:
                return await interaction.response.send_message(f"❌ {vote_message}", ephemeral=True)

            threshold     = SkipVoteManager.get_threshold(voice_client.channel)
            current_votes = SkipVoteManager.get_vote_count(guild_state)

            if current_votes >= threshold:
                await interaction.response.send_message(f"⏭️ Skip vote passed ({current_votes}/{threshold})!", ephemeral=True)
                voice_client.stop()
            else:
                await interaction.response.send_message(f"🗳️ Vote counted! ({current_votes}/{threshold} needed)", ephemeral=True)

        await refresh_panel(interaction.guild, guild_state)

    async def stop_callback(self, interaction: discord.Interaction):
        if not is_dj(interaction.user):
            return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

        voice_client = interaction.guild.voice_client
        if not voice_client:
            return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        guild_state.clear()
        voice_client.stop()
        await interaction.response.send_message("⏹️ Stopped and cleared queue!", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state)

    async def volume_up_callback(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.source:
            return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        new_vol = min(1.0, guild_state.volume + 0.1)
        guild_state.volume = new_vol
        voice_client.source.volume = new_vol
        await interaction.response.send_message(f"🔊 Volume: {int(new_vol * 100)}%", ephemeral=True)

    async def volume_down_callback(self, interaction: discord.Interaction):
        voice_client = interaction.guild.voice_client
        if not voice_client or not voice_client.source:
            return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        new_vol = max(0.0, guild_state.volume - 0.1)
        guild_state.volume = new_vol
        voice_client.source.volume = new_vol
        await interaction.response.send_message(f"🔊 Volume: {int(new_vol * 100)}%", ephemeral=True)

    async def shuffle_callback(self, interaction: discord.Interaction):
        if not is_dj(interaction.user):
            return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        if not guild_state.queue:
            return await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)

        shuffle_queue(guild_state)
        await interaction.response.send_message("🔀 Queue shuffled!", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state)

    async def clear_callback(self, interaction: discord.Interaction):
        if not is_dj(interaction.user):
            return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        clear_queue(guild_state)
        await interaction.response.send_message("🗑️ Queue cleared!", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state)

    async def update_queue_embed(self, interaction: discord.Interaction, page: int):
        guild_state = get_guild_state(interaction.guild_id)
        embed = create_queue_embed(guild_state, page)
        await interaction.response.edit_message(embed=embed)

    async def song_selected_callback(self, interaction: discord.Interaction, song_data, is_soundcloud: bool):
        await interaction.response.defer(ephemeral=True)

        voice_client = await ensure_voice(interaction)
        if not voice_client:
            return

        guild_state = get_guild_state(interaction.guild_id)

        try:
            if is_soundcloud:
                query  = soundcloud_to_youtube_query(song_data)
                source = await YTDLSource.search(query, loop=bot.loop, requester=interaction.user)
            else:
                source = song_data
                source.requester = interaction.user

            already_playing = voice_client.is_playing() or voice_client.is_paused()

            if not guild_state.add_to_queue(source):
                return await interaction.followup.send("❌ Queue is full!", ephemeral=True)

            embed = create_added_embed(source, len(guild_state.queue))
            await interaction.followup.send(embed=embed, ephemeral=True)

            if not already_playing:
                await play_next_song(voice_client, guild_state, bot.loop)

            await refresh_panel(interaction.guild, guild_state)

        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


# ──────────────────────────────────────────────
# SLASH COMMANDS
# ──────────────────────────────────────────────

@app_commands.command(name="controlpanel", description="Toggle persistent music control panel in this channel (DJ/Admin only)")
async def controlpanel(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ or Admin only!", ephemeral=True)

    guild_id = interaction.guild_id
    existing = get_panel(guild_id)

    if existing:
        try:
            ch  = interaction.guild.get_channel(existing["channel_id"])
            msg = await ch.fetch_message(existing["message_id"])
            await msg.delete()
        except Exception:
            pass
        clear_panel(guild_id)
        return await interaction.response.send_message("🗑️ Control panel disabled.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    guild_state = get_guild_state(guild_id)
    embed = create_control_panel_embed(guild_state)
    view  = ControlPanelView(MusicCog(bot), guild_state, timeout=None)

    panel_msg = await interaction.channel.send(embed=embed, view=view)
    set_panel(guild_id, interaction.channel_id, panel_msg.id)

    await interaction.followup.send(
        f"✅ Control panel active in {interaction.channel.mention}!\n"
        f"Use `/play` to add songs — panel updates automatically.",
        ephemeral=True
    )


@app_commands.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        await interaction.user.voice.channel.connect()
        await interaction.response.send_message(f"✅ Joined **{interaction.user.voice.channel.name}**", ephemeral=True)
    else:
        await voice_client.move_to(interaction.user.voice.channel)
        await interaction.response.send_message(f"✅ Moved to **{interaction.user.voice.channel.name}**", ephemeral=True)


@app_commands.command(name="play", description="Play music from YouTube or URL")
@app_commands.describe(query="Song name or URL")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        is_spotify = "spotify.com" in query
        if is_spotify:
            spotify_queries = await bot.loop.run_in_executor(None, handle_spotify_urls_sync, query)
            if not spotify_queries:
                return await interaction.followup.send("❌ Failed to resolve Spotify link or it's empty.", ephemeral=True)
            
            added = 0
            for sq in spotify_queries[:20]:
                if len(guild_state.queue) >= Config.MAX_QUEUE_SIZE:
                    break
                try:
                    source = await YTDLSource.from_url(f"ytsearch:{sq}", loop=bot.loop, stream=True, requester=interaction.user)
                    if guild_state.add_to_queue(source):
                        added += 1
                except Exception:
                    continue
            
            if added == 0:
                return await interaction.followup.send("❌ Failed to load Spotify tracks!", ephemeral=True)
            
            already_playing = voice_client.is_playing() or voice_client.is_paused()
            await interaction.followup.send(f"🎵 Added **{added}** tracks from Spotify!", ephemeral=True)
            
            if not already_playing:
                await play_next_song(voice_client, guild_state, bot.loop)
            
            await refresh_panel(interaction.guild, guild_state)
            return

        if not query.startswith('http'):
            # Try to resolve via Spotify search first
            spotify_search = await bot.loop.run_in_executor(None, spotify_client.search_track, query)
            if spotify_search:
                query = f"ytsearch:{spotify_search}"
            else:
                query = f"ytsearch:{query}"

        source = await YTDLSource.from_url(query, loop=bot.loop, stream=True, requester=interaction.user)

        already_playing = voice_client.is_playing() or voice_client.is_paused()

        if not guild_state.add_to_queue(source):
            return await interaction.followup.send("❌ Queue is full!", ephemeral=True)

        embed = create_added_embed(source, len(guild_state.queue))
        await interaction.followup.send(embed=embed, ephemeral=True)

        if not already_playing:
            await play_next_song(voice_client, guild_state, bot.loop)

        await refresh_panel(interaction.guild, guild_state)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@app_commands.command(name="search", description="Search YouTube and choose from results")
@app_commands.describe(query="Song name to search")
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)

    try:
        from music_player import process_pool, _extract_info_sync
        data = await asyncio.get_event_loop().run_in_executor(
            process_pool,
            _extract_info_sync,
            f"ytsearch5:{query}",
            False
        )

        sources = []
        if 'entries' in data:
            for entry in list(data['entries'])[:5]:
                source = type('obj', (object,), {
                    'title':     entry.get('title'),
                    'uploader':  entry.get('uploader'),
                    'duration':  entry.get('duration'),
                    'thumbnail': entry.get('thumbnail'),
                    'data':      entry
                })()
                sources.append(source)

        if not sources:
            return await interaction.followup.send("❌ No results found!", ephemeral=True)

        view = SongSelectView(MusicCog(bot), sources, is_spotify=False)
        await interaction.followup.send("🎵 Select a song:", view=view, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@app_commands.command(name="soundcloud", description="Search SoundCloud, play first result")
@app_commands.describe(query="Song name or artist")
async def soundcloud_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)
    tracks = soundcloud_client.search_track(query, limit=1)
    if not tracks:
        return await interaction.followup.send("❌ No SoundCloud results found!", ephemeral=True)
    await MusicCog(bot).song_selected_callback(interaction, tracks[0], True)


@app_commands.command(name="soundcloud_search", description="Search SoundCloud and choose from results")
@app_commands.describe(query="Song name or artist")
async def soundcloud_search(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)
    tracks = soundcloud_client.search_track(query, limit=5)
    if not tracks:
        return await interaction.followup.send("❌ No SoundCloud results found!", ephemeral=True)
    view = SongSelectView(MusicCog(bot), tracks, is_spotify=True)
    await interaction.followup.send("🎵 Select a SoundCloud track:", view=view, ephemeral=True)


@app_commands.command(name="skip", description="Vote to skip current song")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)

    if is_dj(interaction.user):
        await interaction.response.send_message("⏭️ Skipped by DJ!", ephemeral=True)
        voice_client.stop()
    else:
        added, vote_message = SkipVoteManager.add_vote(interaction.user.id, guild_state)
        if not added:
            return await interaction.response.send_message(f"❌ {vote_message}", ephemeral=True)

        threshold     = SkipVoteManager.get_threshold(voice_client.channel)
        current_votes = SkipVoteManager.get_vote_count(guild_state)

        if current_votes >= threshold:
            await interaction.response.send_message(f"⏭️ Skip vote passed ({current_votes}/{threshold})!", ephemeral=True)
            voice_client.stop()
        else:
            await interaction.response.send_message(f"🗳️ Vote counted! ({current_votes}/{threshold} needed)", ephemeral=True)

    await refresh_panel(interaction.guild, guild_state)


@app_commands.command(name="forceskip", description="Skip immediately (DJ only)")
async def forceskip(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    await interaction.response.send_message("⏭️ Force skipped!", ephemeral=True)
    voice_client.stop()


@app_commands.command(name="pause", description="Pause the music")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    voice_client.pause()
    guild_state = get_guild_state(interaction.guild_id)
    guild_state.is_paused = True
    await interaction.response.send_message("⏸️ Paused!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state)


@app_commands.command(name="resume", description="Resume the music")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.is_paused():
        return await interaction.response.send_message("❌ Nothing is paused!", ephemeral=True)

    voice_client.resume()
    guild_state = get_guild_state(interaction.guild_id)
    guild_state.is_paused = False
    await interaction.response.send_message("▶️ Resumed!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state)


@app_commands.command(name="stop", description="Stop playback and clear queue (DJ only)")
async def stop(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    voice_client = interaction.guild.voice_client
    if not voice_client:
        return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    guild_state.clear()
    voice_client.stop()
    await interaction.response.send_message("⏹️ Stopped and cleared queue!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state)


@app_commands.command(name="queue", description="Show the music queue (only you can see this)")
async def show_queue(interaction: discord.Interaction):
    guild_state = get_guild_state(interaction.guild_id)

    if not guild_state.queue and not guild_state.current_song:
        return await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)

    embed = create_queue_embed(guild_state, page=0)
    view  = QueueView(MusicCog(bot), guild_state, page=0)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@app_commands.command(name="nowplaying", description="Show current song info")
async def nowplaying(interaction: discord.Interaction):
    guild_state = get_guild_state(interaction.guild_id)

    if not guild_state.current_song:
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    embed = create_now_playing_embed(guild_state.current_song, guild_state)
    view  = NowPlayingView(MusicCog(bot), timeout=None)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@app_commands.command(name="volume", description="Set volume (0-100)")
@app_commands.describe(level="Volume level (0-100)")
async def volume(interaction: discord.Interaction, level: int):
    if not 0 <= level <= 100:
        return await interaction.response.send_message("❌ Volume must be 0-100!", ephemeral=True)

    voice_client = interaction.guild.voice_client
    if not voice_client or not voice_client.source:
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    guild_state.volume = level / 100
    voice_client.source.volume = guild_state.volume
    await interaction.response.send_message(f"🔊 Volume set to **{level}%**", ephemeral=True)


@app_commands.command(name="remove", description="Remove a song from queue (DJ only)")
@app_commands.describe(position="Position in queue to remove")
async def remove(interaction: discord.Interaction, position: int):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    removed = remove_from_queue(guild_state, position - 1)

    if removed:
        await interaction.response.send_message(f"🗑️ Removed: **{removed.title}**", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state)
    else:
        await interaction.response.send_message("❌ Invalid position!", ephemeral=True)


@app_commands.command(name="move", description="Move a song in queue (DJ only)")
@app_commands.describe(from_position="Current position", to_position="New position")
async def move(interaction: discord.Interaction, from_position: int, to_position: int):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    success = move_in_queue(guild_state, from_position - 1, to_position - 1)

    if success:
        await interaction.response.send_message(f"✅ Moved song from #{from_position} to #{to_position}", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state)
    else:
        await interaction.response.send_message("❌ Invalid positions!", ephemeral=True)


@app_commands.command(name="shuffle", description="Shuffle the queue (DJ only)")
async def shuffle(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    if not guild_state.queue:
        return await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)

    shuffle_queue(guild_state)
    await interaction.response.send_message("🔀 Queue shuffled!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state)


@app_commands.command(name="clear", description="Clear the queue (DJ only)")
async def clear(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    clear_queue(guild_state)
    await interaction.response.send_message("🗑️ Queue cleared!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state)


@app_commands.command(name="leave", description="Leave voice channel (DJ only)")
async def leave(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    voice_client = interaction.guild.voice_client
    if not voice_client:
        return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)

    cleanup_guild_state(interaction.guild_id)
    await voice_client.disconnect()
    await interaction.response.send_message("👋 Bye!", ephemeral=True)


@app_commands.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description="Slash commands - use `/` to see all commands",
        color=discord.Color.blue()
    )
    commands_list = [
        ("/play <query>",         "Play from YouTube or URL"),
        ("/ytmusic <query>",      "Play from YouTube Music (more accurate)"),
        ("/ytmusic_search <q>",   "Search YouTube Music, pick from results"),
        ("/artist <name>",        "Artist radio from YouTube Music"),
        ("/mood <mood>",          "Play by mood/genre (chill, party, sad...)"),
        ("/ytplaylist <id>",      "Load public YT Music playlist"),
        ("/search <query>",       "Search YouTube, pick from results"),
        ("/soundcloud <query>",   "SoundCloud – play first result"),
        ("/soundcloud_search",    "SoundCloud – pick from results"),
        ("/loop <mode>",          "Loop off/one/all"),
        ("/pause",                "Pause playback"),
        ("/resume",               "Resume playback"),
        ("/skip",                 "Vote to skip"),
        ("/forceskip",            "Skip immediately (DJ only)"),
        ("/stop",                 "Stop & clear queue (DJ only)"),
        ("/queue",                "View full queue (only you see it)"),
        ("/nowplaying",           "Current song info"),
        ("/volume <0-100>",       "Set volume"),
        ("/remove <pos>",         "Remove song (DJ only)"),
        ("/move <from> <to>",     "Reorder queue (DJ only)"),
        ("/shuffle",              "Shuffle queue (DJ only)"),
        ("/clear",                "Clear queue (DJ only)"),
        ("/join",                 "Join voice channel"),
        ("/leave",                "Leave voice channel (DJ only)"),
        ("/setrequestchannel",    "Set song request channel (DJ/Admin)"),
        ("/controlpanel",         "Toggle persistent music panel (DJ/Admin)"),
    ]
    for cmd, desc in commands_list:
        embed.add_field(name=cmd, value=desc, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────
# YT MUSIC COMMANDS
# ──────────────────────────────────────────────

@app_commands.command(name="ytmusic", description="Play from YouTube Music (more accurate than /play)")
@app_commands.describe(query="Song name or artist")
async def ytmusic_play(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        tracks = await asyncio.get_event_loop().run_in_executor(None, search_songs, query, 1)
        if not tracks:
            # fallback to video search
            tracks = await asyncio.get_event_loop().run_in_executor(None, search_videos, query, 1)
        if not tracks:
            return await interaction.followup.send("❌ No results found on YouTube Music!", ephemeral=True)

        track = tracks[0]
        source = await YTDLSource.from_url(track["url"], loop=bot.loop, stream=True, requester=interaction.user)

        already_playing = voice_client.is_playing() or voice_client.is_paused()

        if not guild_state.add_to_queue(source):
            return await interaction.followup.send("❌ Queue is full!", ephemeral=True)

        embed = create_added_embed(source, len(guild_state.queue))
        await interaction.followup.send(embed=embed, ephemeral=True)

        if not already_playing:
            await play_next_song(voice_client, guild_state, bot.loop)

        await refresh_panel(interaction.guild, guild_state)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@app_commands.command(name="ytmusic_search", description="Search YouTube Music and pick from results")
@app_commands.describe(query="Song name or artist")
async def ytmusic_search(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True)

    try:
        tracks = await asyncio.get_event_loop().run_in_executor(None, search_songs, query, 5)
        if not tracks:
            tracks = await asyncio.get_event_loop().run_in_executor(None, search_videos, query, 5)
        if not tracks:
            return await interaction.followup.send("❌ No results found!", ephemeral=True)

        # Convert to SongSelectView compatible format
        options = []
        for i, t in enumerate(tracks[:5]):
            label = t["title"][:50]
            desc = f"by {t['artist'][:50]}" if t["artist"] else "Unknown artist"
            options.append(discord.SelectOption(label=label, description=desc, value=str(i), emoji="🎵"))

        class YTMusicSelectView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
                select = discord.ui.Select(placeholder="🎵 Choose a song…", options=options)
                select.callback = self.select_callback
                self.add_item(select)

            async def select_callback(self, inter: discord.Interaction):
                idx = int(inter.data["values"][0])
                track = tracks[idx]
                await inter.response.defer(ephemeral=True)

                vc = await ensure_voice(inter)
                if not vc:
                    return

                gs = get_guild_state(inter.guild_id)
                try:
                    source = await YTDLSource.from_url(track["url"], loop=bot.loop, stream=True, requester=inter.user)
                    already = vc.is_playing() or vc.is_paused()
                    if not gs.add_to_queue(source):
                        return await inter.followup.send("❌ Queue is full!", ephemeral=True)
                    embed = create_added_embed(source, len(gs.queue))
                    await inter.followup.send(embed=embed, ephemeral=True)
                    if not already:
                        await play_next_song(vc, gs, bot.loop)
                    await refresh_panel(inter.guild, gs)
                except Exception as e:
                    await inter.followup.send(f"❌ Error: {e}", ephemeral=True)

        await interaction.followup.send("🎵 Select a song:", view=YTMusicSelectView(), ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@app_commands.command(name="artist", description="Play artist radio from YouTube Music")
@app_commands.describe(name="Artist name")
async def artist_radio(interaction: discord.Interaction, name: str):
    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        tracks = await asyncio.get_event_loop().run_in_executor(None, get_artist_radio, name, 20)
        if not tracks:
            return await interaction.followup.send(f"❌ No artist radio found for **{name}**!", ephemeral=True)

        added = 0
        for track in tracks:
            if len(guild_state.queue) >= 20:
                break
            try:
                source = await YTDLSource.from_url(track["url"], loop=bot.loop, stream=True, requester=interaction.user)
                if guild_state.add_to_queue(source):
                    added += 1
            except Exception:
                continue

        if added == 0:
            return await interaction.followup.send("❌ Failed to load tracks!", ephemeral=True)

        already_playing = voice_client.is_playing() or voice_client.is_paused()
        await interaction.followup.send(f"📻 Added **{added}** songs from **{name}** radio!", ephemeral=True)

        if not already_playing:
            await play_next_song(voice_client, guild_state, bot.loop)

        await refresh_panel(interaction.guild, guild_state)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@app_commands.command(name="mood", description="Play music by mood/genre from YouTube Music")
@app_commands.describe(mood="Mood or genre (e.g. chill, workout, sad, party, focus)")
async def mood_play(interaction: discord.Interaction, mood: str):
    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        # Get mood categories and find matching one
        moods = await asyncio.get_event_loop().run_in_executor(None, get_mood_playlists)

        matched_params = None
        mood_lower = mood.lower()

        for category, items in moods.items():
            for item in items:
                title = item.get("title", "").lower()
                if mood_lower in title or title in mood_lower:
                    matched_params = item.get("params")
                    break
            if matched_params:
                break

        if not matched_params:
            # List available moods
            all_moods = []
            for category, items in moods.items():
                for item in items:
                    all_moods.append(item.get("title", ""))
            mood_list = ", ".join(all_moods[:20])
            return await interaction.followup.send(
                f"❌ Mood **{mood}** not found!\nAvailable: {mood_list}",
                ephemeral=True
            )

        tracks = await asyncio.get_event_loop().run_in_executor(None, get_mood_tracks, matched_params, 15)
        if not tracks:
            return await interaction.followup.send("❌ No tracks found for this mood!", ephemeral=True)

        added = 0
        for track in tracks:
            if len(guild_state.queue) >= 15:
                break
            try:
                source = await YTDLSource.from_url(track["url"], loop=bot.loop, stream=True, requester=interaction.user)
                if guild_state.add_to_queue(source):
                    added += 1
            except Exception:
                continue

        if added == 0:
            return await interaction.followup.send("❌ Failed to load tracks!", ephemeral=True)

        already_playing = voice_client.is_playing() or voice_client.is_paused()
        await interaction.followup.send(f"🎭 Added **{added}** songs for mood: **{mood}**!", ephemeral=True)

        if not already_playing:
            await play_next_song(voice_client, guild_state, bot.loop)

        await refresh_panel(interaction.guild, guild_state)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@app_commands.command(name="ytplaylist", description="Load a public YouTube Music playlist")
@app_commands.describe(playlist_id="Playlist ID (from URL: ?list=XXXX)")
async def ytplaylist(interaction: discord.Interaction, playlist_id: str):
    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    # Extract ID from URL if full URL given
    if "list=" in playlist_id:
        import re
        match = re.search(r"list=([a-zA-Z0-9_-]+)", playlist_id)
        if match:
            playlist_id = match.group(1)

    try:
        tracks = await asyncio.get_event_loop().run_in_executor(None, get_playlist_tracks, playlist_id, 50)
        if not tracks:
            return await interaction.followup.send("❌ Playlist not found or empty!", ephemeral=True)

        await interaction.followup.send(f"⏳ Loading {len(tracks)} tracks...", ephemeral=True)

        added = 0
        for track in tracks:
            if len(guild_state.queue) >= Config.MAX_QUEUE_SIZE:
                break
            try:
                source = await YTDLSource.from_url(track["url"], loop=bot.loop, stream=True, requester=interaction.user)
                if guild_state.add_to_queue(source):
                    added += 1
            except Exception:
                continue

        if added == 0:
            return await interaction.followup.send("❌ Failed to load any tracks!", ephemeral=True)

        already_playing = voice_client.is_playing() or voice_client.is_paused()
        await interaction.channel.send(f"📋 Loaded **{added}** songs from playlist!", delete_after=10)

        if not already_playing:
            await play_next_song(voice_client, guild_state, bot.loop)

        await refresh_panel(interaction.guild, guild_state)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)


@app_commands.command(name="setrequestchannel", description="Set song request channel (DJ/Admin only)")
@app_commands.describe(channel="Channel for song requests, or leave empty to disable")
async def setrequestchannel(interaction: discord.Interaction, channel: discord.TextChannel = None):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ or Admin only!", ephemeral=True)

    if channel is None:
        clear_request_channel(interaction.guild_id)
        return await interaction.response.send_message("🗑️ Song request channel disabled.", ephemeral=True)

    set_request_channel(interaction.guild_id, channel.id)
    await interaction.response.send_message(
        f"✅ Song request channel set to {channel.mention}!\n"
        f"Users can now type a song name or YouTube URL there to queue songs.\n"
        f"Max queue size: 50",
        ephemeral=True
    )


@app_commands.command(name="loop", description="Set loop mode (off/one/all)")
@app_commands.describe(mode="off = no loop, one = loop current song, all = loop queue")
@app_commands.choices(mode=[
    app_commands.Choice(name="off", value="off"),
    app_commands.Choice(name="one", value="one"),
    app_commands.Choice(name="all", value="all"),
])
async def loop(interaction: discord.Interaction, mode: str):
    guild_state = get_guild_state(interaction.guild_id)
    guild_state.loop_mode = mode

    icons = {"off": "➡️", "one": "🔂", "all": "🔁"}
    labels = {"off": "Loop Off", "one": "Loop One", "all": "Loop All"}
    await interaction.response.send_message(f"{icons[mode]} **{labels[mode]}**", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state)


# ──────────────────────────────────────────────
# REGISTER COMMANDS
# ──────────────────────────────────────────────

GUILD = discord.Object(id=1106192482083016726)

bot.tree.add_command(loop, guild=GUILD)
bot.tree.add_command(setrequestchannel, guild=GUILD)
bot.tree.add_command(ytmusic_play, guild=GUILD)
bot.tree.add_command(ytmusic_search, guild=GUILD)
bot.tree.add_command(artist_radio, guild=GUILD)
bot.tree.add_command(mood_play, guild=GUILD)
bot.tree.add_command(ytplaylist, guild=GUILD)
bot.tree.add_command(controlpanel, guild=GUILD)
bot.tree.add_command(join, guild=GUILD)
bot.tree.add_command(play, guild=GUILD)
bot.tree.add_command(search, guild=GUILD)
bot.tree.add_command(soundcloud_play, guild=GUILD)
bot.tree.add_command(soundcloud_search, guild=GUILD)
bot.tree.add_command(skip, guild=GUILD)
bot.tree.add_command(forceskip, guild=GUILD)
bot.tree.add_command(pause, guild=GUILD)
bot.tree.add_command(resume, guild=GUILD)
bot.tree.add_command(stop, guild=GUILD)
bot.tree.add_command(show_queue, guild=GUILD)
bot.tree.add_command(nowplaying, guild=GUILD)
bot.tree.add_command(volume, guild=GUILD)
bot.tree.add_command(remove, guild=GUILD)
bot.tree.add_command(move, guild=GUILD)
bot.tree.add_command(shuffle, guild=GUILD)
bot.tree.add_command(clear, guild=GUILD)
bot.tree.add_command(leave, guild=GUILD)
bot.tree.add_command(help_command, guild=GUILD)


# ──────────────────────────────────────────────
# EVENTS
# ──────────────────────────────────────────────

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Check if message is in request channel
    request_channel_id = get_request_channel(message.guild.id) if message.guild else None
    if not request_channel_id or message.channel.id != request_channel_id:
        await bot.process_commands(message)
        return

    query = message.content.strip()
    if not query:
        return

    # Delete user message to keep channel clean
    try:
        await message.delete()
    except Exception:
        pass

    # Check if user is in voice channel
    if not message.author.voice:
        msg = await message.channel.send(f"❌ {message.author.mention} Join a voice channel first!", delete_after=5)
        return

    guild_state = get_guild_state(message.guild.id)

    # Check queue size
    if len(guild_state.queue) >= 50:
        await message.channel.send(f"❌ {message.author.mention} Queue is full! (50/50)", delete_after=5)
        return

    # Connect to voice if needed
    voice_client = message.guild.voice_client
    if voice_client is None:
        voice_client = await message.author.voice.channel.connect()
        await asyncio.sleep(1)
    elif voice_client.channel != message.author.voice.channel:
        await message.channel.send(f"❌ {message.author.mention} Bot is in a different voice channel!", delete_after=5)
        return

    # Send loading message
    loading_msg = await message.channel.send(f"🔍 Searching for **{query[:50]}**...")

    try:
        is_spotify = "spotify.com" in query
        if is_spotify:
            spotify_queries = await bot.loop.run_in_executor(None, handle_spotify_urls_sync, query)
            if not spotify_queries:
                await loading_msg.edit(content="❌ Failed to resolve Spotify link or it's empty.")
                await asyncio.sleep(5)
                await loading_msg.delete()
                return
            
            added = 0
            for sq in spotify_queries[:20]:
                if len(guild_state.queue) >= Config.MAX_QUEUE_SIZE:
                    break
                try:
                    source = await YTDLSource.from_url(f"ytsearch:{sq}", loop=bot.loop, stream=True, requester=message.author)
                    if guild_state.add_to_queue(source):
                        added += 1
                except Exception:
                    continue
            
            if added == 0:
                await loading_msg.edit(content="❌ Failed to load Spotify tracks!")
                await asyncio.sleep(5)
                await loading_msg.delete()
                return
            
            already_playing = voice_client.is_playing() or voice_client.is_paused()
            await loading_msg.edit(content=f"🎵 Added **{added}** tracks from Spotify by {message.author.mention}")
            await asyncio.sleep(5)
            await loading_msg.delete()
            
            if not already_playing:
                await play_next_song(voice_client, guild_state, bot.loop)
            
            await refresh_panel(message.guild, guild_state)
            await bot.process_commands(message)
            return

        if not query.startswith('http'):
            # Try to resolve via Spotify search first
            spotify_search = await bot.loop.run_in_executor(None, spotify_client.search_track, query)
            if spotify_search:
                search_query = f"ytsearch:{spotify_search}"
            else:
                search_query = f"ytsearch:{query}"
        else:
            search_query = query

        source = await YTDLSource.from_url(search_query, loop=bot.loop, stream=True, requester=message.author)

        already_playing = voice_client.is_playing() or voice_client.is_paused()

        if not guild_state.add_to_queue(source):
            await loading_msg.edit(content=f"❌ Queue is full!")
            await asyncio.sleep(5)
            await loading_msg.delete()
            return

        pos = len(guild_state.queue)
        dur = source.format_duration() if source.duration else "?:??"
        await loading_msg.edit(content=f"✅ **{source.title[:60]}** — `{dur}` added to queue #{pos} by {message.author.mention}")
        await asyncio.sleep(5)
        await loading_msg.delete()

        if not already_playing:
            await play_next_song(voice_client, guild_state, bot.loop)

        await refresh_panel(message.guild, guild_state)

    except Exception as e:
        await loading_msg.edit(content=f"❌ Error: {str(e)[:100]}")
        await asyncio.sleep(5)
        await loading_msg.delete()

    await bot.process_commands(message)


@bot.event
async def on_track_update(guild, guild_state):
    await refresh_panel(guild, guild_state)
    # Update bot status to show current song
    if guild_state.current_song:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=guild_state.current_song.title[:128]
            )
        )
    else:
        await bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name="/help")
        )

@bot.event
async def on_ready():
    print(f'Bot online as {bot.user}!')
    print(f'ID: {bot.user.id}')
    print('------')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands globally")
        synced = await bot.tree.sync(guild=discord.Object(id=1106192482083016726))
        print(f"Synced {len(synced)} slash commands to guild")
    except Exception as e:
        print(f"Error syncing commands: {e}")

    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.listening, name="/help")
    )

    for guild in bot.guilds:
        info = get_panel(guild.id)
        if info:
            try:
                ch  = guild.get_channel(info["channel_id"])
                msg = await ch.fetch_message(info["message_id"])
                guild_state = get_guild_state(guild.id)
                view = ControlPanelView(MusicCog(bot), guild_state, timeout=None)
                await msg.edit(view=view)
            except Exception:
                clear_panel(guild.id)


@bot.event
async def on_voice_state_update(member, before, after):
    if member == bot.user and before.channel and not after.channel:
        guild_state = get_guild_state(member.guild.id)
        guild_state.clear()
        guild_state.current_song = None
        await refresh_panel(member.guild, guild_state)


if __name__ == '__main__':
    token = Config.DISCORD_TOKEN
    if not token:
        print("❌ DISCORD_TOKEN not set in .env file!")
    else:
        bot.run(token)