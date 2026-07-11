import discord

from discord.ext import commands
from discord import app_commands
import asyncio
import os
import json
import sys
import datetime

from config import Config
from music_player import (
    YTDLSource, GuildMusicState, get_guild_state,
    cleanup_guild_state, play_next_song, guild_states
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
    get_mood_playlists, get_mood_tracks,
    get_playlist_tracks, track_to_source_data
)
from spotify_module import SpotifyClient
from web_dashboard import start_dashboard
from playlist_store import (
    create_playlist, save_queue_as_playlist, get_playlist,
    get_user_playlists, delete_playlist, add_to_playlist, remove_from_playlist
)
from backup_restore import create_backup, list_backups, restore_backup, delete_backup, get_backup_info
from recommendation_engine import reset_recommendations, get_interaction_stats
from quality_store import get_quality, set_quality
from command_rate_limiter import check_rate_limit, get_rate_limit_config
from audit_log import record_command, flush as flush_audit_log, get_stats as get_audit_stats

Config.setup_ssl()
Config.validate()

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.members = True

all_bots = [] # Store all bot instances for coordination

class MusicBot(commands.Bot):
    def __init__(self, is_primary: bool = False):
        super().__init__(command_prefix='!', intents=intents, help_command=None)
        self.spotify = SpotifyClient(Config.SPOTIFY_CLIENT_ID, Config.SPOTIFY_CLIENT_SECRET)
        self.is_primary = is_primary # Flag to identify the main bot

    async def _trigger_restore(self, guild_id: int, info: dict):
        """Restore a guild session from saved state after bot restart."""
        await asyncio.sleep(5)  # Give bot time to establish connections
        await restore_guild_session(self, guild_id, info)

    async def setup_hook(self):
        if self.is_primary:
            try:
                # Clear guild-level commands (often causes duplicates in menu)
                target_guild = discord.Object(id=1106192482083016726)
                self.tree.clear_commands(guild=target_guild)
                await self.tree.sync(guild=target_guild)

                # Sync globally (only primary bot has commands in its tree)
                synced = await self.tree.sync()
                print(f"Synced {len(synced)} global commands for PRIMARY bot: {self.user}")
            except Exception as e:
                print(f"Error syncing for PRIMARY bot: {e}")
        else:
            # Secondary bots: ensure no commands are registered (guild or global)
            try:
                target_guild = discord.Object(id=1106192482083016726)
                self.tree.clear_commands(guild=target_guild)
                await self.tree.sync(guild=target_guild)
            except:
                pass

            try:
                await self.tree.sync()
            except Exception as e:
                print(f"Error clearing secondary bot commands: {e}")

    async def on_ready(self):
        print(f'Bot online as {self.user}!')

        # Auto-join owner's voice channel (ONLY for the primary bot)
        if self.is_primary and Config.OWNER_ID:
            for guild in self.guilds:
                owner = guild.get_member(Config.OWNER_ID)
                if owner and owner.voice and owner.voice.channel:
                    print(f"[Startup] Primary Bot {self.user} auto-joining owner in: {owner.voice.channel.name}")
                    try:
                        await owner.voice.channel.connect(timeout=60.0, reconnect=True)
                    except: pass

        # ── Restore States from previous session (Primary Only) ─────
        if self.is_primary and os.path.exists("restart_state.json"):
            try:
                with open("restart_state.json", "r") as f:
                    restore_data = json.load(f)
                os.remove("restart_state.json")
                print(f"[Restore] Found {len(restore_data)} sessions to resume.")
                for gid_str, info in restore_data.items():
                    # Find which bot can see this guild
                    self.loop.create_task(self._trigger_restore(int(gid_str), info))
            except Exception as e:
                print(f"[Restore] Initialization error: {e}")

        # Only primary bot sets initial presence
        if self.is_primary:
            await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))
        else:
            await self.change_presence(activity=None) # No activity for secondary bots

    async def on_message(self, message):
        await handle_message_request(self, message)

    async def on_voice_state_update(self, member, before, after):
        await handle_voice_update(self, member, before, after)

    async def on_track_update(self, guild, guild_state):
        await refresh_panel(guild, guild_state, self)
        # Only primary bot updates its presence
        if self.is_primary:
            if guild_state.current_song:
                await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=guild_state.current_song.title[:128]))
            else:
                await self.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name="/help"))

soundcloud_client = SoundCloudClient()
global_spotify = SpotifyClient(Config.SPOTIFY_CLIENT_ID, Config.SPOTIFY_CLIENT_SECRET)

async def process_spotify_list(interaction, voice_client, guild_state, queries):
    """Process Spotify tracks with parallel fetching (up to 4 concurrent)."""
    await interaction.followup.send(f"⏳ Processing {len(queries)} tracks from Spotify...", ephemeral=True)

    sem = asyncio.Semaphore(4)
    added = 0

    async def _resolve(sq):
        nonlocal added
        if len(guild_state.queue) >= Config.MAX_QUEUE_SIZE:
            return
        async with sem:
            try:
                source = await YTDLSource.from_url(f"ytsearch:{sq}", loop=interaction.client.loop, stream=True, requester=interaction.user)
                if guild_state.add_to_queue(source):
                    added += 1
            except Exception:
                pass

    await asyncio.gather(*[_resolve(sq) for sq in queries[:50]])

    if added > 0:
        already_playing = voice_client.is_playing() or voice_client.is_paused()
        await interaction.followup.send(f"🎵 Added **{added}** tracks to queue!", ephemeral=True)
        if not already_playing:
            await play_next_song(voice_client, guild_state, interaction.client.loop)
        await refresh_panel(interaction.guild, guild_state, interaction.client)
    else:
        await interaction.followup.send("❌ Could not load any tracks from that playlist.", ephemeral=True)

def find_voice_client(guild_id: int):
    """Find the active voice_client among all bots connected to this guild."""
    for b in all_bots:
        guild = b.get_guild(guild_id)
        if guild and guild.voice_client:
            return guild.voice_client
    return None

def handle_spotify_urls_sync(query: str) -> list:
    match = parse_spotify_url(query)
    if not match:
        return []
    url_type, spotify_id = match
    if url_type == 'track':
        q = global_spotify.get_track_query(spotify_id)
        return [q] if q else []
    elif url_type == 'playlist':
        return global_spotify.get_playlist_queries(spotify_id)
    elif url_type == 'album':
        return global_spotify.get_album_queries(spotify_id)
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

async def refresh_panel(guild: discord.Guild, guild_state, current_bot=None):
    msg = await get_panel_message(guild)
    if not msg:
        return

    if not current_bot:
        vc = find_voice_client(guild.id)
        current_bot = vc.client if vc else all_bots[0]

    cog = MusicCog(current_bot)
    embed = create_control_panel_embed(guild_state)
    view  = ControlPanelView(cog, guild_state, timeout=None)

    try:
        await msg.edit(embed=embed, view=view)
    except Exception:
        pass

# ────────────────────────────────────────────── 
# VOICE HELPERS 
# ──────────────────────────────────────────────

async def _parallel_load_tracks(tracks, interaction, guild_state, voice_client, max_tracks=50, success_msg="Added **{added}** tracks!"):
    """Load multiple tracks in parallel with a concurrency limit. Returns added count."""
    sem = asyncio.Semaphore(4)
    added = 0

    async def _load(track):
        nonlocal added
        if len(guild_state.queue) >= max_tracks:
            return
        async with sem:
            try:
                source = await YTDLSource.from_url(track["url"], loop=interaction.client.loop, stream=True, requester=interaction.user)
                if guild_state.add_to_queue(source):
                    added += 1
            except Exception:
                pass

    await asyncio.gather(*[_load(t) for t in tracks])

    if added == 0:
        return 0

    already_playing = voice_client.is_playing() or voice_client.is_paused()
    if not already_playing:
        await play_next_song(voice_client, guild_state, interaction.client.loop)
    await refresh_panel(interaction.guild, guild_state, interaction.client)
    return added

async def ensure_voice(interaction: discord.Interaction):
    async def send_error(message: str):
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    if not interaction.user.voice:
        await send_error("❌ You must be in a voice channel!")
        return None

    user_vc = interaction.user.voice.channel

    # ── Check bot permissions ──────────────────────────────────────
    bot_member = interaction.guild.me
    if bot_member:
        perms = user_vc.permissions_for(bot_member)
        if not perms.connect:
            await send_error(f"❌ Bot cannot connect to {user_vc.name} (missing Connect permission)")
            return None
        if not perms.speak:
            await send_error(f"❌ Bot cannot speak in {user_vc.name} (missing Speak permission)")
            return None

    # Logika Multi-Bot: Cari bot yang available
    target_bot = None

    # 1. Cek apakah ada bot yang sudah berada di VC user
    for b in all_bots:
        guild = b.get_guild(interaction.guild_id)
        if guild and guild.voice_client and guild.voice_client.channel.id == user_vc.id:
            target_bot = b
            break

    # 2. Jika tidak, cari bot yang sedang menganggur (idle) di server ini
    if not target_bot:
        for b in all_bots:
            guild = b.get_guild(interaction.guild_id)
            if guild and not guild.voice_client:
                target_bot = b
                break

    # 3. Fallback ke bot yang menerima interaksi (Primary)
    if not target_bot:
        target_bot = interaction.client

    guild = target_bot.get_guild(interaction.guild_id)
    voice_client = guild.voice_client if guild else None

    if voice_client is None:
        # Ambil objek channel dari perspektif bot yang dipilih
        bot_vc = target_bot.get_channel(user_vc.id)
        voice_client = await bot_vc.connect(timeout=60.0, reconnect=True)
    elif voice_client.channel.id != user_vc.id:
        await send_error(f"❌ {target_bot.user.name} is already busy in another channel!")
        return None

    return voice_client

# ────────────────────────────────────────────── 
# MUSIC COG 
# ──────────────────────────────────────────────

class MusicCog:
    def __init__(self, bot):
        self.bot = bot

    def get_voice_client(self, guild_id: int):
        return find_voice_client(guild_id)

    async def dashboard_callback(self, interaction: discord.Interaction):
        guild_state  = get_guild_state(interaction.guild_id)
        voice_client = find_voice_client(interaction.guild_id)
        embed = create_dashboard_embed(guild_state, voice_client=voice_client, guild=interaction.guild)

        # Provide the Web Dashboard link for the specific guild
        url = f"http://localhost:{Config.DASHBOARD_PORT}/guild/{interaction.guild_id}"
        content = f"🌐 **Web Dashboard Access**\nView real-time monitoring and full queue here:\n{url}\n\n*(Note: If accessing remotely, replace 'localhost' with your server's IP address)*"

        await interaction.response.send_message(content=content, embed=embed, ephemeral=True)

    async def pause_callback(self, interaction: discord.Interaction):
        voice_client = find_voice_client(interaction.guild_id)
        guild_state  = get_guild_state(interaction.guild_id)

        if not voice_client:
            return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

        if voice_client.is_paused():
            voice_client.resume()
            guild_state.is_paused = False
            await interaction.response.send_message("▶️ Resumed!", ephemeral=True)
        else:
            voice_client.pause()
            guild_state.is_paused = True
            await interaction.response.send_message("⏸️ Paused!", ephemeral=True)

        await refresh_panel(interaction.guild, guild_state, interaction.client)

    async def skip_callback(self, interaction: discord.Interaction):
        voice_client = find_voice_client(interaction.guild_id)
        if not voice_client:
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

        await refresh_panel(interaction.guild, guild_state, interaction.client)

    async def stop_callback(self, interaction: discord.Interaction):
        if not is_dj(interaction.user):
            return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

        voice_client = find_voice_client(interaction.guild_id)
        if not voice_client:
            return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        guild_state.clear()
        voice_client.stop()
        await interaction.response.send_message("⏹️ Stopped and cleared queue!", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state, interaction.client)

    async def volume_up_callback(self, interaction: discord.Interaction):
        voice_client = find_voice_client(interaction.guild_id)
        if not voice_client or not voice_client.source:
            return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        new_vol = min(1.0, guild_state.volume + 0.1)
        guild_state.volume = new_vol
        voice_client.source.volume = new_vol
        await interaction.response.send_message(f"🔊 Volume: {int(new_vol * 100)}%", ephemeral=True)

    async def volume_down_callback(self, interaction: discord.Interaction):
        voice_client = find_voice_client(interaction.guild_id)
        if not voice_client or not voice_client.source:
            return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        new_vol = max(0.0, guild_state.volume - 0.1)
        guild_state.volume = new_vol
        voice_client.source.volume = new_vol
        await interaction.response.send_message(f"🔉 Volume: {int(new_vol * 100)}%", ephemeral=True)

    async def shuffle_callback(self, interaction: discord.Interaction):
        if not is_dj(interaction.user):
            return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        if not guild_state.queue:
            return await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)

        shuffle_queue(guild_state)
        await interaction.response.send_message("🔀 Queue shuffled!", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state, interaction.client)

    async def clear_callback(self, interaction: discord.Interaction):
        if not is_dj(interaction.user):
            return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

        guild_state = get_guild_state(interaction.guild_id)
        clear_queue(guild_state)
        await interaction.response.send_message("🗑️ Queue cleared!", ephemeral=True)
        await refresh_panel(interaction.guild, guild_state, interaction.client)

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
                source = await YTDLSource.search(query, loop=interaction.client.loop, requester=interaction.user)
            else:
                source = song_data
                source.requester = interaction.user

            already_playing = voice_client.is_playing() or voice_client.is_paused()

            if not guild_state.add_to_queue(source):
                return await interaction.followup.send("❌ Queue is full!", ephemeral=True)

            embed = create_added_embed(source, len(guild_state.queue))
            await interaction.followup.send(embed=embed, ephemeral=True)

            if not already_playing:
                await play_next_song(voice_client, guild_state, interaction.client.loop)

            await refresh_panel(interaction.guild, guild_state, interaction.client)

        except Exception as e:
            await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

# ────────────────────────────────────────────── 
# HELPERS 
# ──────────────────────────────────────────────

def is_authorized(user: discord.Member) -> bool:
    """Check if user is OWNER OR IN A VOICE CHANNEL"""
    if user.id == Config.OWNER_ID:
        return True
    # Check if user is in a voice channel
    if user.voice and user.voice.channel:
        return True
    return False


# ── Rate Limiter + Audit Log Helpers ─────────────────────────────────────

async def rate_limit_check(interaction: discord.Interaction) -> bool:
    """Check rate limit and log command usage. Returns True if allowed."""
    cmd_name = interaction.command.name if interaction.command else "unknown"
    user_id = interaction.user.id

    # Check rate limit
    allowed = await check_rate_limit(user_id, cmd_name)
    if not allowed:
        if not interaction.response.is_done():
            await interaction.response.send_message(
                f"⏳ Slow down! You're using **/{cmd_name}** too fast. Please wait a moment.",
                ephemeral=True
            )
        return False

    # Log command usage
    record_command(
        user_id=user_id,
        user_name=str(interaction.user),
        guild_id=interaction.guild_id,
        guild_name=interaction.guild.name if interaction.guild else None,
        command=cmd_name,
        options=dict(interaction.data.get("options", {})) if interaction.data else {}
    )

    return True


async def periodic_audit_flush(interval: int = 30):
    """Periodically flush audit log entries to disk."""
    while True:
        await asyncio.sleep(interval)
        try:
            n = flush_audit_log()
            if n:
                print(f"[audit_log] Flushed {n} entries to disk")
        except Exception as e:
            print(f"[audit_log] Flush error: {e}")


# ── Spotify Connect Imports ──────────────────────────────────────────────

try:
    from spotify_auth import (
        has_user_token, get_user_token, remove_user_token,
        build_authorize_url, wait_for_callback,
        start_callback_server, refresh_user_token,
    )
    _SPOTIFY_AUTH_AVAILABLE = True
except ImportError:
    _SPOTIFY_AUTH_AVAILABLE = False
    print("[bot] spotify_auth.py not found — Spotify Connect commands disabled")

# ────────────────────────────────────────────── 
# COMMANDS 
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
    view  = ControlPanelView(MusicCog(interaction.client), guild_state, timeout=None)

    panel_msg = await interaction.channel.send(embed=embed, view=view)
    set_panel(guild_id, interaction.channel_id, panel_msg.id)

    await interaction.followup.send(
        f"✅ Control panel active in {interaction.channel.mention}!\n"
        f"Use `/play` to add songs — panel updates automatically.",
        ephemeral=True
    )

@app_commands.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    if not interaction.user.voice:
        return await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if voice_client:
        await interaction.response.send_message(f"✅ Joined **{voice_client.channel.name}**", ephemeral=True)
@app_commands.command(name="play", description="Play music (YouTube, Spotify URL, or Spotify Playlist Name)")
@app_commands.describe(query="Song name, URL, or 'playlist: judul playlist'")
async def play(interaction: discord.Interaction, query: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        # Fitur baru: Mencari playlist global jika diawali dengan 'playlist:'
        if query.lower().startswith("playlist:"):
            search_query = query[9:].strip()
            await interaction.followup.send(f"🔍 Searching global Spotify playlist: **{search_query}**...", ephemeral=True)
            spotify_queries = await interaction.client.loop.run_in_executor(None, global_spotify.search_playlist_queries, search_query)
            if spotify_queries:
                # Gunakan logika penambahan queue yang sudah ada untuk playlist
                await process_spotify_list(interaction, voice_client, guild_state, spotify_queries)
                return
            else:
                return await interaction.followup.send("❌ No Spotify playlist found with that name.", ephemeral=True)

        is_spotify = "spotify.com" in query
        if is_spotify:
            spotify_queries = await interaction.client.loop.run_in_executor(None, handle_spotify_urls_sync, query)
            if not spotify_queries:
                return await interaction.followup.send("❌ Failed to resolve Spotify link or it's empty.", ephemeral=True)

            # Defer update for long playlists
            await process_spotify_list(interaction, voice_client, guild_state, spotify_queries)
            return

        if not query.startswith('http'):
            # Try to resolve via Spotify search first
            spotify_search = await interaction.client.loop.run_in_executor(None, global_spotify.search_track, query)
            if spotify_search:
                query = f"ytsearch:{spotify_search}"
            else:
                query = f"ytsearch:{query}"

        source = await YTDLSource.from_url(query, loop=interaction.client.loop, stream=True, requester=interaction.user)

        already_playing = voice_client.is_playing() or voice_client.is_paused()

        if not guild_state.add_to_queue(source):
            return await interaction.followup.send("❌ Queue is full!", ephemeral=True)

        embed = create_added_embed(source, len(guild_state.queue))
        await interaction.followup.send(embed=embed, ephemeral=True)

        if not already_playing:
            await play_next_song(voice_client, guild_state, interaction.client.loop)

        await refresh_panel(interaction.guild, guild_state, interaction.client)
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@app_commands.command(name="search", description="Search YouTube and choose from results")
@app_commands.describe(query="Song name to search")
async def search(interaction: discord.Interaction, query: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

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
                sources.append(type('SongPreview', (), {
                    'title':     entry.get('title'),
                    'uploader':  entry.get('uploader'),
                    'duration':  entry.get('duration'),
                    'thumbnail': entry.get('thumbnail'),
                    'data':      entry,
                })())

        if not sources:
            return await interaction.followup.send("❌ No results found!", ephemeral=True)

        view = SongSelectView(MusicCog(interaction.client), sources, is_spotify=False)
        await interaction.followup.send("🎵 Select a song:", view=view, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@app_commands.command(name="soundcloud", description="Search SoundCloud, play first result")
@app_commands.describe(query="Song name or artist")
async def soundcloud_play(interaction: discord.Interaction, query: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    tracks = soundcloud_client.search_track(query, limit=1)
    if not tracks:
        return await interaction.followup.send("❌ No SoundCloud results found!", ephemeral=True)
    await MusicCog(interaction.client).song_selected_callback(interaction, tracks[0], True)

@app_commands.command(name="soundcloud_search", description="Search SoundCloud and choose from results")
@app_commands.describe(query="Song name or artist")
async def soundcloud_search(interaction: discord.Interaction, query: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    tracks = soundcloud_client.search_track(query, limit=5)
    if not tracks:
        return await interaction.followup.send("❌ No SoundCloud results found!", ephemeral=True)
    view = SongSelectView(MusicCog(interaction.client), tracks, is_spotify=True)
    await interaction.followup.send("🎵 Select a SoundCloud track:", view=view, ephemeral=True)

@app_commands.command(name="skip", description="Vote to skip current song")
async def skip(interaction: discord.Interaction):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
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

    await refresh_panel(interaction.guild, guild_state, interaction.client)

@app_commands.command(name="forceskip", description="Skip immediately (DJ only)")
async def forceskip(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
    if not voice_client or not voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    await interaction.response.send_message("⏭️ Force skipped!", ephemeral=True)
    voice_client.stop()

@app_commands.command(name="pause", description="Pause the music")
async def pause(interaction: discord.Interaction):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
    if not voice_client or not voice_client.is_playing():
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    voice_client.pause()
    guild_state = get_guild_state(interaction.guild_id)
    guild_state.is_paused = True
    await interaction.response.send_message("⏸️ Paused!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state, interaction.client)

@app_commands.command(name="resume", description="Resume the music")
async def resume(interaction: discord.Interaction):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
    if not voice_client or not voice_client.is_paused():
        return await interaction.response.send_message("❌ Nothing is paused!", ephemeral=True)

    voice_client.resume()
    guild_state = get_guild_state(interaction.guild_id)
    guild_state.is_paused = False
    await interaction.response.send_message("▶️ Resumed!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state, interaction.client)

@app_commands.command(name="stop", description="Stop playback and clear queue (DJ only)")
async def stop(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
    if not voice_client:
        return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    guild_state.clear()
    voice_client.stop()
    await interaction.response.send_message("⏹️ Stopped and cleared queue!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state, interaction.client)

@app_commands.command(name="queue", description="Show the music queue (only you can see this)")
async def show_queue(interaction: discord.Interaction):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)

    if not guild_state.queue and not guild_state.current_song:
        return await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)

    embed = create_queue_embed(guild_state, page=0)
    view  = QueueView(MusicCog(interaction.client), guild_state, page=0)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@app_commands.command(name="nowplaying", description="Show current song info")
async def nowplaying(interaction: discord.Interaction):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)

    if not guild_state.current_song:
        return await interaction.response.send_message("❌ Nothing is playing!", ephemeral=True)

    embed = create_now_playing_embed(guild_state.current_song, guild_state)
    view  = NowPlayingView(MusicCog(interaction.client), guild_state, timeout=None)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@app_commands.command(name="volume", description="Set volume (0-100)")
@app_commands.describe(level="Volume level (0-100)")
async def volume(interaction: discord.Interaction, level: int):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    if not 0 <= level <= 100:
        return await interaction.response.send_message("❌ Volume must be 0-100!", ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
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
        await refresh_panel(interaction.guild, guild_state, interaction.client)
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
        await refresh_panel(interaction.guild, guild_state, interaction.client)
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
    await refresh_panel(interaction.guild, guild_state, interaction.client)

@app_commands.command(name="clear", description="Clear the queue (DJ only)")
async def clear(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    clear_queue(guild_state)
    await interaction.response.send_message("🗑️ Queue cleared!", ephemeral=True)
    await refresh_panel(interaction.guild, guild_state, interaction.client)

@app_commands.command(name="leave", description="Leave voice channel (DJ only)")
async def leave(interaction: discord.Interaction):
    if not is_dj(interaction.user):
        return await interaction.response.send_message("❌ DJ only command!", ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
    if not voice_client:
        return await interaction.response.send_message("❌ Not in a voice channel!", ephemeral=True)

    cleanup_guild_state(interaction.guild_id)
    await voice_client.disconnect()
    await interaction.response.send_message("👋 Bye!", ephemeral=True)

# ────────────────────────────────────────────── 
# PLAYLIST COMMANDS 
# ──────────────────────────────────────────────

@app_commands.command(name="playlist_create", description="Create a new playlist")
@app_commands.describe(name="Name of the playlist")
async def playlist_create(interaction: discord.Interaction, name: str):
    if create_playlist(interaction.guild_id, interaction.user.id, name):
        await interaction.response.send_message(f"✅ Playlist **{name}** created successfully!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Playlist **{name}** already exists!", ephemeral=True)

@app_commands.command(name="playlist_save", description="Save current queue as a playlist")
@app_commands.describe(name="Name of the playlist")
async def playlist_save(interaction: discord.Interaction, name: str):
    guild_state = get_guild_state(interaction.guild_id)
    if not guild_state.queue:
        return await interaction.response.send_message("❌ Queue is empty!", ephemeral=True)

    if save_queue_as_playlist(interaction.guild_id, interaction.user.id, name, guild_state.queue):
        await interaction.response.send_message(f"✅ Queue saved as playlist **{name}**!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Playlist **{name}** already exists!", ephemeral=True)

@app_commands.command(name="playlist_load", description="Load a playlist into the queue")
@app_commands.describe(name="Name of the playlist")
async def playlist_load(interaction: discord.Interaction, name: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    await interaction.response.defer(ephemeral=True)
    playlist = get_playlist(interaction.guild_id, interaction.user.id, name)
    if not playlist:
        return await interaction.followup.send(f"❌ Playlist **{name}** not found!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    songs = playlist.get("songs", [])
    sem = asyncio.Semaphore(4)
    added_count = 0

    async def _load_song(song_data):
        nonlocal added_count
        if len(guild_state.queue) >= Config.MAX_QUEUE_SIZE:
            return
        async with sem:
            try:
                url = song_data.get("webpage_url") or song_data.get("url")
                if url:
                    song = await YTDLSource.from_url(url, loop=interaction.client.loop, requester=interaction.user)
                    if guild_state.add_to_queue(song):
                        added_count += 1
            except Exception as e:
                print(f"Error loading song: {e}")

    await asyncio.gather(*[_load_song(s) for s in songs])
    await interaction.followup.send(f"✅ Loaded **{added_count}** songs from playlist **{name}**!", ephemeral=True)

    if not voice_client.is_playing() and guild_state.queue:
        await play_next_song(voice_client, guild_state, interaction.client.loop)

@app_commands.command(name="playlist_list", description="List all your playlists")
async def playlist_list(interaction: discord.Interaction):
    playlists = get_user_playlists(interaction.guild_id, interaction.user.id)

    if not playlists:
        return await interaction.response.send_message("❌ You have no playlists!", ephemeral=True)

    embed = discord.Embed(
        title="📋 Your Playlists",
        color=discord.Color.blue()
    )

    for playlist in playlists:
        song_count = len(playlist.get("songs", []))
        embed.add_field(
            name=playlist["name"],
            value=f"{song_count} songs",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="playlist_delete", description="Delete a playlist")
@app_commands.describe(name="Name of the playlist to delete")
async def playlist_delete(interaction: discord.Interaction, name: str):
    if delete_playlist(interaction.guild_id, interaction.user.id, name):
        await interaction.response.send_message(f"✅ Playlist **{name}** deleted!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Playlist **{name}** not found!", ephemeral=True)

# ────────────────────────────────────────────── 
# BACKUP & RESTORE COMMANDS 
# ──────────────────────────────────────────────

@app_commands.command(name="backup", description="Create a backup (Owner only)")
async def backup(interaction: discord.Interaction):
    if interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message("❌ Owner only command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    backup_path = create_backup()
    await interaction.followup.send(f"✅ Backup created: `{backup_path}`", ephemeral=True)

@app_commands.command(name="backup_list", description="List all available backups (Owner only)")
async def backup_list(interaction: discord.Interaction):
    if interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message("❌ Owner only command!", ephemeral=True)

    backups = list_backups()

    if not backups:
        return await interaction.response.send_message("❌ No backups found!", ephemeral=True)

    embed = discord.Embed(
        title="📦 Backups",
        color=discord.Color.green()
    )

    for backup in backups:
        size_mb = backup["size"] / (1024 * 1024)
        created_time = datetime.datetime.fromtimestamp(backup["created"]).strftime("%Y-%m-%d %H:%M:%S")
        embed.add_field(
            name=backup["name"],
            value=f"Size: {size_mb:.2f} MB\nCreated: {created_time}",
            inline=False
        )

    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="restore", description="Restore from a backup (Owner only)")
@app_commands.describe(backup_name="Name of the backup file to restore")
async def restore(interaction: discord.Interaction, backup_name: str):
    if interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message("❌ Owner only command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    if restore_backup(backup_name):
        await interaction.followup.send(f"✅ Restored from **{backup_name}**! Please restart the bot.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ Failed to restore **{backup_name}**!", ephemeral=True)

@app_commands.command(name="backup_delete", description="Delete a backup (Owner only)")
@app_commands.describe(backup_name="Name of the backup file to delete")
async def backup_delete(interaction: discord.Interaction, backup_name: str):
    if interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message("❌ Owner only command!", ephemeral=True)

    if delete_backup(backup_name):
        await interaction.response.send_message(f"✅ Deleted backup **{backup_name}**!", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Backup **{backup_name}** not found!", ephemeral=True)

@app_commands.command(name="quality", description="Set or check audio quality (DJ only)")
@app_commands.describe(quality="Quality preset (optional, leave empty to check current)")
@app_commands.choices(quality=[
    app_commands.Choice(name="Low - Bandwidth Friendly", value="low"),
    app_commands.Choice(name="Medium - Balanced", value="medium"),
    app_commands.Choice(name="High - Clear Audio", value="high"),
    app_commands.Choice(name="Lossless - Best Quality", value="lossless"),
])
async def quality(interaction: discord.Interaction, quality: str = None):
    # Check permission (DJ or Admin)
    if not (is_dj(interaction.user) or interaction.user.guild_permissions.administrator):
        return await interaction.response.send_message("❌ DJ or Administrator only!", ephemeral=True)

    guild_id = interaction.guild.id
    guild_name = interaction.guild.name
    user_id = interaction.user.id
    user_name = str(interaction.user)

    if not quality:
        # Show current quality
        current_quality = get_quality(guild_id)
        preset = Config.VOICE_QUALITY_PRESETS.get(current_quality)
        embed = discord.Embed(
            title="🎵 Audio Quality Settings",
            color=preset['color'] if preset else discord.Color.blurple()
        )
        embed.add_field(
            name="Current Quality",
            value=f"**{current_quality.capitalize()}**\n{preset['description']}",
            inline=False
        )
        embed.add_field(
            name="Bitrate",
            value=f"`{preset['bitrate']}`",
            inline=True
        )
        embed.add_field(
            name="Buffer",
            value=f"`{preset['buffersize']}`",
            inline=True
        )
        embed.set_footer(text="Use /quality [preset] to change quality")
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    # Set new quality
    if quality not in Config.VOICE_QUALITY_PRESETS:
        return await interaction.response.send_message("❌ Invalid quality!", ephemeral=True)

    changed = set_quality(guild_id, guild_name, quality, user_id, user_name)
    preset = Config.VOICE_QUALITY_PRESETS[quality]

    embed = discord.Embed(
        title="🎵 Audio Quality Updated",
        color=preset['color']
    )
    embed.add_field(
        name="New Quality",
        value=f"**{quality.capitalize()}**\n{preset['description']}",
        inline=False
    )
    embed.add_field(
        name="Bitrate",
        value=f"`{preset['bitrate']}`",
        inline=True
    )
    embed.add_field(
        name="Buffer",
        value=f"`{preset['buffersize']}`",
        inline=True
    )
    if changed:
        embed.set_footer(text="Changes apply to next song")
    else:
        embed.set_footer(text="Quality already set to this preset")

    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="rec_reset", description="Reset all recommendations (Owner only)")
async def rec_reset(interaction: discord.Interaction):
    if interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message("❌ Owner only command!", ephemeral=True)

    reset_recommendations()
    await interaction.response.send_message("✅ All recommendations have been reset!", ephemeral=True)

@app_commands.command(name="rec_stats", description="Get recommendation interaction stats (Owner only)")
async def rec_stats(interaction: discord.Interaction):
    if interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message("❌ Owner only command!", ephemeral=True)

    stats = get_interaction_stats()
    embed = discord.Embed(
        title="📊 Recommendation Statistics",
        color=discord.Color.blue()
    )
    embed.add_field(name="Total Interactions", value=stats["total"], inline=False)
    embed.add_field(name="Completed", value=stats["completed"], inline=True)
    embed.add_field(name="Dismissed", value=stats["dismissed"], inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=True)

@app_commands.command(name="help", description="Show available commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎵 Music Bot Commands",
        description="Slash commands - use `/` to see all commands",
        color=discord.Color.blue()
    )

    # Music Commands
    music_cmds = [
        ("/play <query>",         "Play from YouTube or URL"),
        ("/ytmusic <query>",      "Play from YouTube Music (more accurate)"),
        ("/ytmusic_search <q>",   "Search YouTube Music, pick from results"),
        ("/artist <name>",        "Artist radio from YouTube Music"),
        ("/mood <mood>",          "Play by mood/genre (chill, party, sad...)"),
        ("/ytplaylist <id>",      "Load public YT Music playlist"),
        ("/search <query>",       "Search YouTube, pick from results"),
        ("/soundcloud <query>",   "SoundCloud – play first result"),
        ("/soundcloud_search",    "SoundCloud – pick from results"),
    ]
    embed.add_field(name="🎶 Music", value="\n".join([f"**{cmd}**: {desc}" for cmd, desc in music_cmds]), inline=False)

    # Playback Controls
    playback_cmds = [
        ("/loop <mode>",          "Loop off/one/all"),
        ("/pause",                "Pause playback"),
        ("/resume",               "Resume playback"),
        ("/skip",                 "Vote to skip"),
        ("/forceskip",            "Skip immediately (DJ only)"),
        ("/stop",                 "Stop & clear queue (DJ only)"),
        ("/volume <0-100>",       "Set volume"),
    ]
    embed.add_field(name="⏯️ Playback", value="\n".join([f"**{cmd}**: {desc}" for cmd, desc in playback_cmds]), inline=False)

    # Queue Management
    queue_cmds = [
        ("/queue",                "View full queue (only you see it)"),
        ("/nowplaying",           "Current song info"),
        ("/remove <pos>",         "Remove song (DJ only)"),
        ("/move <from> <to>",     "Reorder queue (DJ only)"),
        ("/shuffle",              "Shuffle queue (DJ only)"),
        ("/clear",                "Clear queue (DJ only)"),
    ]
    embed.add_field(name="📋 Queue", value="\n".join([f"**{cmd}**: {desc}" for cmd, desc in queue_cmds]), inline=False)

    # Playlist Management
    playlist_cmds = [
        ("/playlist_create <name>",  "Create a new playlist"),
        ("/playlist_save <name>",    "Save current queue as a playlist"),
        ("/playlist_load <name>",    "Load a playlist into queue"),
        ("/playlist_list",           "List all your playlists"),
        ("/playlist_delete <name>",  "Delete a playlist"),
    ]
    embed.add_field(name="💾 Playlists", value="\n".join([f"**{cmd}**: {desc}" for cmd, desc in playlist_cmds]), inline=False)

    # Utilities
    utils_cmds = [
        ("/join",                 "Join voice channel"),
        ("/leave",                "Leave voice channel (DJ only)"),
        ("/setrequestchannel",    "Set song request channel (DJ/Admin)"),
        ("/controlpanel",         "Toggle persistent music panel (DJ/Admin)"),
        ("/filter",               "Apply audio filters"),
        ("/lyrics",               "Get lyrics for current song"),
    ]
    embed.add_field(name="🛠️ Utilities", value="\n".join([f"**{cmd}**: {desc}" for cmd, desc in utils_cmds]), inline=False)

    # Spotify Connect
    spotify_cmds = [
        ("/spotify_connect",     "Link your Spotify account"),
        ("/spotify_token",       "Complete OAuth verification"),
        ("/spotify_disconnect",  "Unlink Spotify account"),
        ("/spotify_status",      "Check connection status"),
    ]
    embed.add_field(name="🎧 Spotify Connect", value="\n".join([f"**{cmd}**: {desc}" for cmd, desc in spotify_cmds]), inline=False)

    # Backup/Restore (Owner only)
    if interaction.user.id == Config.OWNER_ID:
        backup_cmds = [
            ("/backup",               "Create a backup"),
            ("/backup_list",          "List all backups"),
            ("/restore <name>",       "Restore from backup"),
            ("/backup_delete <name>", "Delete a backup"),
        ]
        embed.add_field(name="📦 Backup", value="\n".join([f"**{cmd}**: {desc}" for cmd, desc in backup_cmds]), inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────
# SPOTIFY CONNECT COMMANDS
# ──────────────────────────────────────────────

@app_commands.command(name="spotify_connect", description="Link your Spotify account for Spotify Connect control")
async def spotify_connect(interaction: discord.Interaction):
    """Start OAuth to link a Spotify account for Connect control."""
    if not _SPOTIFY_AUTH_AVAILABLE:
        return await interaction.response.send_message("❌ Spotify Connect not available (spotify_auth.py missing).", ephemeral=True)
    if not Config.SPOTIFY_CLIENT_ID or not Config.SPOTIFY_CLIENT_SECRET:
        return await interaction.response.send_message("❌ SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not configured.", ephemeral=True)

    if not await rate_limit_check(interaction):
        return

    # Check if already linked
    if has_user_token(interaction.user.id):
        await interaction.response.send_message(
            "🔗 Your Spotify account is already linked!\n"
            "Use `/spotify status` to check connection.\n"
            "Use `/spotify reconnect` to re-link.",
            ephemeral=True
        )
        return

    auth_url = build_authorize_url(interaction.user.id)
    await interaction.response.send_message(
        f"🔗 **Link your Spotify account**\n\n"
        f"1. Click this link to authorize:\n"
        f"   {auth_url}\n\n"
        f"2. After authorizing, you'll see a success page.\n"
        f"3. Then run `/spotify token` to verify the connection.\n\n"
        f"_The link expires in 2 minutes._",
        ephemeral=True
    )


@app_commands.command(name="spotify_token", description="Complete Spotify OAuth and verify your connection")
async def spotify_token(interaction: discord.Interaction):
    """Wait for the OAuth callback and verify the stored token."""
    if not _SPOTIFY_AUTH_AVAILABLE:
        return await interaction.response.send_message("❌ Spotify Connect not available.", ephemeral=True)

    if not await rate_limit_check(interaction):
        return

    # Check if already linked
    if has_user_token(interaction.user.id):
        await interaction.response.send_message("✅ Your Spotify account is already linked!", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    # Wait for the OAuth callback (user should have already authorized)
    success = await wait_for_callback(interaction.user.id, timeout=30.0)
    if success:
        await interaction.followup.send(
            "✅ **Spotify account linked!**\n\n"
            "Use `/spotify status` to see your connection.\n"
            "Use `/spotify disconnect` to unlink.",
            ephemeral=True
        )
    else:
        await interaction.followup.send(
            "❌ No OAuth callback received.\n\n"
            "Make sure you:\n"
            "1. Ran `/spotify connect` and clicked the link\n"
            "2. Authorized in your browser\n"
            "3. Ran `/spotify token` within 2 minutes",
            ephemeral=True
        )


@app_commands.command(name="spotify_disconnect", description="Unlink your Spotify account")
async def spotify_disconnect(interaction: discord.Interaction):
    """Remove stored Spotify token for this user."""
    if not _SPOTIFY_AUTH_AVAILABLE:
        return await interaction.response.send_message("❌ Spotify Connect not available.", ephemeral=True)

    if not await rate_limit_check(interaction):
        return

    if remove_user_token(interaction.user.id):
        await interaction.response.send_message("🗑️ Your Spotify account has been unlinked.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ No linked Spotify account found.", ephemeral=True)


@app_commands.command(name="spotify_status", description="Check your Spotify Connect connection status")
async def spotify_status(interaction: discord.Interaction):
    """Show whether the user has a linked Spotify account and token info."""
    if not _SPOTIFY_AUTH_AVAILABLE:
        return await interaction.response.send_message("❌ Spotify Connect not available.", ephemeral=True)

    if not await rate_limit_check(interaction):
        return

    if not Config.SPOTIFY_CLIENT_ID or not Config.SPOTIFY_CLIENT_SECRET:
        embed = discord.Embed(
            title="🎵 Spotify Connect",
            description="Spotify API credentials not configured.",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    token = get_user_token(interaction.user.id)
    embed = discord.Embed(
        title="🎵 Spotify Connect",
        color=discord.Color.gold() if token else discord.Color.dark_gray()
    )

    if token:
        embed.description = "✅ **Connected**"
        embed.add_field(name="Expires", value=f"<t:{int(token.get('expires_at', 0))}:R>", inline=True)
        scope_str = token.get("scope", "N/A")
        embed.add_field(name="Scopes", value=f"```{scope_str[:80]}```", inline=False)
        embed.set_footer(text="Use /spotify disconnect to unlink")
    else:
        embed.description = "❌ **Not connected**"
        embed.add_field(name="How to link", value="Run `/spotify connect` to link your Spotify account.", inline=False)
        embed.set_footer(text="Requires Spotify API credentials in .env")

    await interaction.response.send_message(embed=embed, ephemeral=True)


# ──────────────────────────────────────────────

@app_commands.command(name="lyrics", description="Get lyrics for the current song or a specific query")
@app_commands.describe(query="Song name (optional, defaults to current song)")
async def lyrics(interaction: discord.Interaction, query: str = None):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    if not query:
        guild_state = get_guild_state(interaction.guild_id)
        if not guild_state.current_song:
            return await interaction.followup.send("❌ Nothing is playing and no query provided!", ephemeral=True)
        query = guild_state.current_song.title

    # Hint: Lu bisa pakai API lyrics.ovh (gratis & simple) atau Genius API
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://api.lyrics.ovh/v1/_/_") as resp: # Placeholder logic
            # Implementasi fetch lirik di sini
            pass

    await interaction.followup.send(f"🔍 Searching lyrics for: **{query}**...\n*(Implement a lyrics API like Genius to see results here!)*", ephemeral=True)

@app_commands.command(name="filter", description="Apply audio filters to the music")
@app_commands.describe(mode="Choose an audio filter")
@app_commands.choices(mode=[
    app_commands.Choice(name="None (Reset)", value="none"),
    app_commands.Choice(name="Bassboost (Heavy)", value="bass=g=15,firequalizer=gain_entry='entry(0,10);entry(250,0)'"),
    app_commands.Choice(name="Nightcore (Fast & High Pitch)", value="asetrate=48000*1.25,atempo=1.25"),
    app_commands.Choice(name="Vaporwave (Slow & Low Pitch)", value="asetrate=48000*0.8,atempo=0.8"),
    app_commands.Choice(name="Low Pass (Muffled)", value="lowpass=f=450"),
    app_commands.Choice(name="Karaoke (Experimental)", value="stereotools=mplevel=2:mprelay=1")
])
async def audio_filter(interaction: discord.Interaction, mode: app_commands.Choice[str]):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    voice_client = find_voice_client(interaction.guild_id)
    if not voice_client or not (voice_client.is_playing() or voice_client.is_paused()):
        return await interaction.followup.send("❌ Nothing is playing!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)

    if mode.value == "none":
        guild_state.active_filter = None
        msg = "✨ Filters cleared."
    else:
        guild_state.active_filter = mode.value
        msg = f"🎧 Filter applied: **{mode.name}**"

    # To apply filters, we MUST restart the current song because FFmpeg processes filters at startup
    if guild_state.current_song:
        # Put current song back to the start of the queue
        current = guild_state.current_song
        # Create a fresh copy to avoid issues
        guild_state.queue.insert(0, current)

        # Stop the voice client - this will trigger 'after_playing'
        # which calls play_next_song automatically
        voice_client.stop()

        # We need to inform play_next_song NOT to treat this as a "skip"
        # but the current logic handles guild_state.queue nicely.
        await interaction.followup.send(f"{msg} (Restarting track to apply...)", ephemeral=True)
    else:
        await interaction.followup.send(msg, ephemeral=True)

    await refresh_panel(interaction.guild, guild_state)

@app_commands.command(name="crossfade", description="Set crossfade duration between songs (0 = off)")
@app_commands.describe(seconds="Crossfade duration in seconds (0 to disable, max 10)")
async def crossfade(interaction: discord.Interaction, seconds: int = 3):
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    if not 0 <= seconds <= 10:
        return await interaction.response.send_message("❌ Crossfade must be between 0 and 10 seconds!", ephemeral=True)

    guild_state = get_guild_state(interaction.guild_id)
    guild_state.crossfade_seconds = seconds

    if seconds == 0:
        msg = "❌ Crossfade disabled."
    else:
        msg = f"🎧 Crossfade set to **{seconds}s** between songs."

    await interaction.response.send_message(msg, ephemeral=True)

@app_commands.command(name="restart", description="Restart the bot fully (Owner Only)")
@app_commands.default_permissions(administrator=True)
async def restart_bot(interaction: discord.Interaction):
    # Extra protection: Check if the caller is the Owner
    if Config.OWNER_ID != 0 and interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message(
            "❌ Sorry, this command is restricted. Only the Bot Owner can restart the bot!",
            ephemeral=True)

    await interaction.response.send_message("🔄 Restarting bot... Please wait a moment.", ephemeral=True)

    # ── Save State for Seamless Restart ────────────────────────
    try:
        state_data = {}
        for gid, state in guild_states.items():
            g = interaction.client.get_guild(gid)
            if g and g.voice_client:
                state_data[str(gid)] = {
                    "channel_id": g.voice_client.channel.id,
                    "loop_mode": state.loop_mode,
                    "autoplay": state.autoplay,
                    "volume": state.volume,
                    "active_filter": state.active_filter,
                    "current": {"url": state.current_song.webpage_url or state.current_song.url, "title": state.current_song.title} if state.current_song else None,
                    "queue": [{"url": s.webpage_url or s.url, "title": s.title} for s in state.queue if hasattr(s, 'url') or hasattr(s, 'webpage_url')]
                }
        with open("restart_state.json", "w") as f:
            json.dump(state_data, f)
    except Exception as e:
        print(f"[Restart] Error saving state: {e}")

    # This exits the python process, and our bash script loop will restart it
    sys.exit(0)

@app_commands.command(name="shutdown", description="Shut down the bot completely (Owner Only)")
@app_commands.default_permissions(administrator=True)
async def shutdown_bot(interaction: discord.Interaction):
    # Extra protection: Check if the caller is the Owner
    if Config.OWNER_ID != 0 and interaction.user.id != Config.OWNER_ID:
        return await interaction.response.send_message(
            "❌ Sorry, this command is restricted. Only the Bot Owner can shut down the bot!",
            ephemeral=True)

    await interaction.response.send_message("🛑 Shutting down bot... Goodbye!", ephemeral=True)

    # Cleanup voice connections for all bots
    for b in all_bots:
        for vc in b.voice_clients:
            try: await vc.disconnect()
            except: pass

    # Exit code 130 tells run_bot.sh to stop the loop and exit the script
    sys.exit(130)

# ────────────────────────────────────────────── 
# YT MUSIC COMMANDS 
# ──────────────────────────────────────────────

@app_commands.command(name="ytmusic", description="Play from YouTube Music (more accurate than /play)")
@app_commands.describe(query="Song name or artist")
async def ytmusic_play(interaction: discord.Interaction, query: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        tracks = await interaction.client.loop.run_in_executor(None, search_songs, query, 1)
        if not tracks:
            # fallback to video search
            tracks = await interaction.client.loop.run_in_executor(None, search_videos, query, 1)
        if not tracks:
            return await interaction.followup.send("❌ No results found on YouTube Music!", ephemeral=True)

        track = tracks[0]
        source = await YTDLSource.from_url(track["url"], loop=interaction.client.loop, stream=True, requester=interaction.user)

        already_playing = voice_client.is_playing() or voice_client.is_paused()

        if not guild_state.add_to_queue(source):
            return await interaction.followup.send("❌ Queue is full!", ephemeral=True)

        embed = create_added_embed(source, len(guild_state.queue))
        await interaction.followup.send(embed=embed, ephemeral=True)

        if not already_playing:
            await play_next_song(voice_client, guild_state, interaction.client.loop)

        await refresh_panel(interaction.guild, guild_state, interaction.client)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@app_commands.command(name="ytmusic_search", description="Search YouTube Music and pick from results")
@app_commands.describe(query="Song name or artist")
async def ytmusic_search(interaction: discord.Interaction, query: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    try:
        tracks = await interaction.client.loop.run_in_executor(None, search_songs, query, 5)
        if not tracks:
            tracks = await interaction.client.loop.run_in_executor(None, search_videos, query, 5)
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
                bot_instance = inter.client

                vc = await ensure_voice(inter)
                if not vc:
                    return

                gs = get_guild_state(inter.guild_id)
                try:
                    source = await YTDLSource.from_url(track["url"], loop=bot_instance.loop, stream=True, requester=inter.user)
                    already = vc.is_playing() or vc.is_paused()
                    if not gs.add_to_queue(source):
                        return await inter.followup.send("❌ Queue is full!", ephemeral=True)
                    embed = create_added_embed(source, len(gs.queue))
                    await inter.followup.send(embed=embed, ephemeral=True)
                    if not already:
                        await play_next_song(vc, gs, bot_instance.loop)
                    await refresh_panel(inter.guild, gs, bot_instance)
                except Exception as e:
                    await inter.followup.send(f"❌ Error: {e}", ephemeral=True)

        await interaction.followup.send("🎵 Select a song:", view=YTMusicSelectView(), ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@app_commands.command(name="artist", description="Play artist radio from YouTube Music")
@app_commands.describe(name="Artist name")
async def artist_radio(interaction: discord.Interaction, name: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        tracks = await interaction.client.loop.run_in_executor(None, get_artist_radio, name, 20)
        if not tracks:
            return await interaction.followup.send(f"❌ No artist radio found for **{name}**!", ephemeral=True)

        added = await _parallel_load_tracks(tracks, interaction, guild_state, voice_client, max_tracks=20)
        if added == 0:
            return await interaction.followup.send("❌ Failed to load tracks!", ephemeral=True)
        await interaction.followup.send(f"📻 Added **{added}** songs from **{name}** radio!", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@app_commands.command(name="mood", description="Play music by mood/genre from YouTube Music")
@app_commands.describe(mood="Mood or genre (e.g. chill, workout, sad, party, focus)")
async def mood_play(interaction: discord.Interaction, mood: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    voice_client = await ensure_voice(interaction)
    if not voice_client:
        return

    guild_state = get_guild_state(interaction.guild_id)

    try:
        # Get mood categories and find matching one
        moods = await interaction.client.loop.run_in_executor(None, get_mood_playlists)

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

        tracks = await interaction.client.loop.run_in_executor(None, get_mood_tracks, matched_params, 15)
        if not tracks:
            return await interaction.followup.send("❌ No tracks found for this mood!", ephemeral=True)

        added = await _parallel_load_tracks(tracks, interaction, guild_state, voice_client, max_tracks=15)
        if added == 0:
            return await interaction.followup.send("❌ Failed to load tracks!", ephemeral=True)
        await interaction.followup.send(f"🎭 Added **{added}** songs for mood: **{mood}**!", ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

@app_commands.command(name="ytplaylist", description="Load a public YouTube Music playlist")
@app_commands.describe(playlist_id="Playlist ID (from URL: ?list=XXXX)")
async def ytplaylist(interaction: discord.Interaction, playlist_id: str):
    # Check: Owner OR in Voice Channel
    if not is_authorized(interaction.user):
        return await interaction.response.send_message("❌ You must be in a voice channel (or be owner) to use this command!", ephemeral=True)

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
        tracks = await interaction.client.loop.run_in_executor(None, get_playlist_tracks, playlist_id, 50)
        if not tracks:
            return await interaction.followup.send("❌ Playlist not found or empty!", ephemeral=True)

        await interaction.followup.send(f"⏳ Loading {len(tracks)} tracks...", ephemeral=True)

        added = await _parallel_load_tracks(tracks, interaction, guild_state, voice_client)
        if added == 0:
            return await interaction.followup.send("❌ Failed to load any tracks!", ephemeral=True)
        await interaction.channel.send(f"📋 Loaded **{added}** songs from playlist!", delete_after=10)

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
    await refresh_panel(interaction.guild, guild_state, interaction.client)

GUILD = discord.Object(id=1106192482083016726)

# ────────────────────────────────────────────── 
# EVENTS 
# ──────────────────────────────────────────────

async def handle_message_request(current_bot, message):
    if message.author.bot: return

    request_channel_id = get_request_channel(message.guild.id) if message.guild else None
    if not request_channel_id or message.channel.id != request_channel_id: return

    # ── Coordination Logic ──────────────────────────────────────────────────
    # Decide which bot instance should handle this request.
    # Bot 2 works if Bot 1 is already busy in another VC.
    user_vc = message.author.voice.channel if message.author.voice else None
    should_handle = False

    if not user_vc:
        # If user not in VC, only the primary bot handles showing the error
        if getattr(current_bot, 'is_primary', False):
            should_handle = True
        else:
            return
    else:
        my_vc = message.guild.voice_client.channel if message.guild.voice_client else None

        if my_vc == user_vc:
            # I am already here, I handle it.
            should_handle = True
        elif my_vc is None:
            # I am idle. Step in only if no other bot is already in the user's channel
            # AND I am the first idle bot in the priority list.
            another_bot_there = False
            for b in all_bots:
                if b == current_bot: continue
                guild = b.get_guild(message.guild.id)
                if guild and guild.voice_client and guild.voice_client.channel == user_vc:
                    another_bot_there = True
                    break

            if not another_bot_there:
                for b in all_bots:
                    if b == current_bot:
                        should_handle = True
                        break
                    guild = b.get_guild(message.guild.id)
                    if guild and not guild.voice_client: # Someone before me is idle
                        break

    if not should_handle:
        return
    # ────────────────────────────────────────────────────────────────────────

    query = message.content.strip()
    if not query: return

    try: await message.delete()
    except: pass

    if not message.author.voice:
        await message.channel.send(f"❌ {message.author.mention} Join a voice channel first!", delete_after=5)
        return

    guild_state = get_guild_state(message.guild.id)
    if len(guild_state.queue) >= 50:
        await message.channel.send(f"❌ {message.author.mention} Queue is full! (50/50)", delete_after=5)
        return

    # Connect to voice if needed
    voice_client = message.guild.voice_client
    if voice_client is None:
        voice_client = await message.author.voice.channel.connect(timeout=60.0)

    loading_msg = await message.channel.send(f"🔍 Searching for **{query[:50]}**...")

    try:
        is_spotify = "spotify.com" in query
        if is_spotify:
            spotify_queries = await current_bot.loop.run_in_executor(None, handle_spotify_urls_sync, query)
            if not spotify_queries:
                await loading_msg.edit(content="❌ Failed to resolve Spotify link or it's empty.")
                await asyncio.sleep(3)
                await loading_msg.delete()
                return

            added = 0
            for sq in spotify_queries[:50]:
                if len(guild_state.queue) >= Config.MAX_QUEUE_SIZE:
                    break
                try:
                    source = await YTDLSource.from_url(f"ytsearch:{sq}", loop=current_bot.loop, stream=True, requester=message.author)
                    if guild_state.add_to_queue(source):
                        added += 1
                except Exception:
                    continue

            if added == 0:
                await loading_msg.edit(content="❌ Failed to load Spotify tracks!")
                await asyncio.sleep(3)
                await loading_msg.delete()
                return

            already_playing = voice_client.is_playing() or voice_client.is_paused()
            await loading_msg.edit(content=f"🎵 Added **{added}** tracks from Spotify by {message.author.mention}")
            await asyncio.sleep(3)
            await loading_msg.delete()

            if not already_playing:
                await play_next_song(voice_client, guild_state, current_bot.loop)

            await refresh_panel(message.guild, guild_state, current_bot)
            return

        if not query.startswith('http'):
            spotify_search = await current_bot.loop.run_in_executor(None, global_spotify.search_track, query)
            if spotify_search:
                search_query = f"ytsearch:{spotify_search}"
            else:
                search_query = f"ytsearch:{query}"
        else:
            search_query = query

        source = await YTDLSource.from_url(search_query, loop=current_bot.loop, stream=True, requester=message.author)

        already_playing = voice_client.is_playing() or voice_client.is_paused()

        if not guild_state.add_to_queue(source):
            await loading_msg.edit(content=f"❌ Queue is full!")
            await asyncio.sleep(3)
            await loading_msg.delete()
            return

        pos = len(guild_state.queue)
        dur = source.format_duration() if source.duration else "?:??"
        await loading_msg.edit(content=f"✅ **{source.title[:60]}** — `{dur}` added to queue #{pos} by {message.author.mention}")
        await asyncio.sleep(3)
        await loading_msg.delete()

        if not already_playing:
            await play_next_song(voice_client, guild_state, current_bot.loop)

        await refresh_panel(message.guild, guild_state, current_bot)

    except Exception as e:
        await loading_msg.edit(content=f"❌ Error: {str(e)[:100]}")
        await asyncio.sleep(3)
        await loading_msg.delete()

async def handle_voice_update(current_bot, member, before, after):
    # Only the primary bot follows the owner into different channels
    if getattr(current_bot, 'is_primary', False) and member.id == Config.OWNER_ID and after.channel:
        if before.channel != after.channel:
            vc = member.guild.voice_client
            if not vc: await after.channel.connect(timeout=60.0)
            elif vc.channel != after.channel: await vc.move_to(after.channel)

    if member == current_bot.user and before.channel and not after.channel:
        gs = get_guild_state(member.guild.id)
        gs.clear()
        await refresh_panel(member.guild, gs, current_bot)

async def restore_guild_session(bot_instance: commands.Bot, guild_id: int, info: dict):
    guild = bot_instance.get_guild(guild_id)
    if not guild: return
    channel = guild.get_channel(info["channel_id"])
    if not channel: return

    try:
        vc = await channel.connect(timeout=30.0, reconnect=True)
        state = get_guild_state(guild_id)
        state.loop_mode = info["loop_mode"]
        state.autoplay = info["autoplay"]
        state.volume = info["volume"]
        state.active_filter = info.get("active_filter")

        if info["current"]:
            source = await YTDLSource.from_url(info["current"]["url"], loop=bot_instance.loop, stream=True)
            for q in info["queue"]:
                # Mock song object for queue persistence
                dummy = type('Song', (), {
                    'title': q['title'],
                    'url': q['url'],
                    'webpage_url': q['url'],
                    'format_duration': lambda: "?:??",
                    'requester': None,
                    'data': {}
                })
                state.queue.append(dummy)

            # Start playback immediately
            state.current_song = source
            vc.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next_song(vc, state, bot_instance.loop), bot_instance.loop))
            if vc.source: vc.source.volume = state.volume
            await refresh_panel(guild, state, bot_instance)
            print(f"[Restore] Resumed playback in {guild.name}")
    except Exception as e:
        print(f"[Restore] Failed for {guild.name}: {e}")

if __name__ == '__main__':
    # First, define the command list ONCE before initializing any bots
    commands_list = [
        loop, setrequestchannel, ytmusic_play, ytmusic_search, artist_radio,
        mood_play, ytplaylist, controlpanel, join, play, search,
        soundcloud_play, soundcloud_search, skip, forceskip, pause,
        resume, stop, show_queue, nowplaying, volume, remove,
        move, shuffle, clear, leave, help_command, audio_filter, lyrics, crossfade, restart_bot, shutdown_bot,
        playlist_create, playlist_save, playlist_load, playlist_list, playlist_delete,
        backup, backup_list, restore, backup_delete, quality,
        rec_reset, rec_stats,
        # New features
        spotify_connect, spotify_token, spotify_disconnect, spotify_status,
    ]

    async def main():
        Config.validate()
        global all_bots
        all_bots = []
        for i, token in enumerate(Config.DISCORD_TOKENS):
            b = MusicBot(is_primary=(i == 0)) # First bot is primary
            all_bots.append(b)

        # ONLY PRIMARY BOT gets commands — secondary bots stay command-free
        # This way Discord only shows ONE set of commands (from primary bot)
        for cmd in commands_list:
            all_bots[0].tree.add_command(cmd)

        # Start background tasks
        asyncio.create_task(periodic_audit_flush(interval=30))

        # Start Spotify OAuth callback server if credentials exist
        if Config.SPOTIFY_CLIENT_ID and Config.SPOTIFY_CLIENT_SECRET and _SPOTIFY_AUTH_AVAILABLE:
            try:
                await start_callback_server()
            except Exception as e:
                print(f"[bot] Failed to start Spotify OAuth server: {e}")

        # Start Dashboard with the list of bots
        await start_dashboard(all_bots)

        # Run all bots concurrently
        await asyncio.gather(*[b.start(token) for b, token in zip(all_bots, Config.DISCORD_TOKENS)])

    try: asyncio.run(main())
    except KeyboardInterrupt: pass
