import asyncio
import discord
import yt_dlp as youtube_dl
from config import Config
from utils import format_duration
from quality_store import get_quality
import concurrent.futures

process_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)  # Optimized for 4 concurrent downloads

def _extract_info_sync(url, download=False, quality_preset=None):
    import yt_dlp
    from config import Config

    # Use quality-specific format if provided, otherwise default
    ytdl_opts = Config.YTDL_FORMAT_OPTIONS.copy()
    if quality_preset and quality_preset in Config.VOICE_QUALITY_PRESETS:
        ytdl_opts['format'] = Config.VOICE_QUALITY_PRESETS[quality_preset]['ytdl_format']

    ytdl = yt_dlp.YoutubeDL(ytdl_opts)
    return ytdl.extract_info(url, download=download)

ytdl = youtube_dl.YoutubeDL(Config.YTDL_FORMAT_OPTIONS)

# ────────────────────────────────────────────── 
# PREFETCH CACHE 
# ──────────────────────────────────────────────

# guild_id -> prefetched YTDLSource (next song ready to play)
_prefetch_cache: dict = {}
# Limit cache size to prevent memory bloat
MAX_CACHE_SIZE = 10

async def prefetch_next(guild_state, bot_loop):
    """Pre-fetch the next song in queue in background."""
    if not guild_state.queue:
        return
    next_song = guild_state.queue[0]
    # Already a full YTDLSource (has ffmpeg ready) — skip
    if isinstance(next_song, YTDLSource) and next_song.url and next_song.url.startswith("http"):
        try:
            print(f"Pre-fetching: {next_song.title}")
            refreshed = await YTDLSource.refresh(next_song, loop=bot_loop)
            # Manage cache size
            if len(_prefetch_cache) >= MAX_CACHE_SIZE:
                # Remove oldest entry
                oldest_key = next(iter(_prefetch_cache))
                _prefetch_cache.pop(oldest_key)
            _prefetch_cache[guild_state.guild_id] = refreshed
            print(f"Pre-fetch done: {refreshed.title}")
        except Exception as e:
            print(f"Pre-fetch failed: {e}")

async def _prefetch_autoplay(guild_state, current_song, bot_loop):
    """Pre-fetch autoplay suggestion in background while current song plays."""
    if _prefetch_cache.get(guild_state.guild_id):
        return  # already have something cached
    try:
        print(f"Pre-fetching autoplay suggestion...")
        auto_song = await fetch_autoplay_suggestion(current_song, bot_loop, guild_state.history, guild_state.song_history)
        if auto_song and not _prefetch_cache.get(guild_state.guild_id):
            # Manage cache size
            if len(_prefetch_cache) >= MAX_CACHE_SIZE:
                # Remove oldest entry
                oldest_key = next(iter(_prefetch_cache))
                _prefetch_cache.pop(oldest_key)
            _prefetch_cache[guild_state.guild_id] = auto_song
            print(f"Autoplay pre-fetch done: {auto_song.title}")
    except Exception as e:
        print(f"Autoplay pre-fetch failed: {e}")

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get('title', 'Unknown Title')
        self.url = data.get('url')
        self.duration = data.get('duration')
        self.thumbnail = data.get('thumbnail')
        self.uploader = data.get('uploader', 'Unknown')
        self.webpage_url = data.get('webpage_url')
        self.requester = None

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True, requester=None, quality_preset=None):
        loop = loop or asyncio.get_event_loop()

        # Get quality from guild if not specified
        if not quality_preset and requester and hasattr(requester, 'guild'):
            quality_preset = get_quality(requester.guild.id)

        data = await loop.run_in_executor(
            process_pool,
            _extract_info_sync,
            url,
            not stream,
            quality_preset
        )

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)

        print(f"Extracted audio URL for: {data.get('title', 'Unknown')}")
        print(f"Format: {data.get('format', 'Unknown')}")
        print(f"Protocol: {data.get('protocol', 'Unknown')}")
        if filename:
            print(f"URL starts with: {filename[:60]}...")

        # Build FFmpeg options with quality-specific buffer
        quality_preset = quality_preset or Config.DEFAULT_QUALITY
        preset_config = Config.VOICE_QUALITY_PRESETS.get(quality_preset, Config.VOICE_QUALITY_PRESETS[Config.DEFAULT_QUALITY])
        buffer_size = preset_config['buffersize']
        bitrate = preset_config['bitrate']

        base_options_list = ['-vn', '-bufsize', buffer_size]

        # Add bitrate constraint for consistent output
        base_options_list.extend(['-b:a', bitrate])

        # Handle filters properly: combine into a single -af flag
        active_filter = None
        if requester and hasattr(requester, 'guild'):
            st = get_guild_state(requester.guild.id)
            active_filter = st.active_filter

        if active_filter:
            base_options_list.extend(['-af', active_filter])

        base_options = ' '.join(base_options_list)

        try:
            ffmpeg_audio = discord.FFmpegPCMAudio(
                filename,
                executable=Config.FFMPEG_PATH,
                before_options=Config.FFMPEG_OPTIONS.get('before_options', ''),
                options=base_options
            )
        except Exception as e:
            print(f"Error creating FFmpegPCMAudio: {e}")
            raise

        source = cls(ffmpeg_audio, data=data)
        source.requester = requester
        return source

    @classmethod
    def _pick_best(cls, entries, query):
        query_words = set(query.lower().split())
        best = None
        best_score = -1

        for entry in entries:
            if not entry:
                continue

            views    = entry.get('view_count') or 0
            title    = (entry.get('title') or '').lower()
            duration = entry.get('duration') or 0

            if duration < 30 or duration > 1500:
                continue

            import math
            view_score      = math.log10(views + 1) * 2.5 if views > 0 else 0
            matched         = sum(1 for w in query_words if w in title)
            relevance_score = (matched / max(len(query_words), 1)) * 25
            uploader        = (entry.get('uploader') or '').lower()
            # Spotify focuses on studio high-quality versions (Topic channels)
            channel_bonus   = 45 if any(k in uploader for k in ['- topic', 'topic']) else \
                              15 if any(k in uploader or k in title for k in ['official audio', 'audio only']) else \
                              10 if any(k in uploader or k in title for k in ['official', 'audio']) else -15

            # Penalty for music videos (usually not full song)
            mv_keywords = ['music video', 'official video', 'official mv', '(mv)', '| mv', 'video clip', 'videoclip', 'lyric video', 'official lyric', 'lyrics video', 'lirik', 'liric']
            mv_penalty  = -50 if any(k in title for k in mv_keywords) else 0

            score = view_score + relevance_score + channel_bonus + mv_penalty

            if score > best_score:
                best_score = score
                best = entry

        return best or entries[0]

    @classmethod
    async def search(cls, query, *, loop=None, requester=None):
        loop = loop or asyncio.get_event_loop()

        raw = await loop.run_in_executor(
            process_pool,
            _extract_info_sync,
            f"ytsearch5:{query}",
            False
        )
        entries = [e for e in (raw.get('entries') or []) if e]
        if not entries:
            raise Exception(f"No results for: {query}")

        best        = cls._pick_best(entries, query)
        webpage_url = best.get('webpage_url') or best.get('url')
        return await cls.from_url(webpage_url, loop=loop, requester=requester)

    @classmethod
    async def refresh(cls, song, *, loop=None, quality_preset=None):
        loop        = loop or asyncio.get_event_loop()
        webpage_url = song.webpage_url
        if not webpage_url:
            return song

        try:
            if hasattr(song, 'original') and song.original:
                song.original.cleanup()
        except Exception:
            pass

        # Get quality from requester's guild if not specified
        if not quality_preset and song.requester and hasattr(song.requester, 'guild'):
            quality_preset = get_quality(song.requester.guild.id)

        data = await loop.run_in_executor(
            process_pool,
            _extract_info_sync,
            webpage_url,
            False,
            quality_preset
        )

        if 'entries' in data:
            data = data['entries'][0]

        stream_url = data['url']

        # Rebuild options with current filters and quality
        quality_preset = quality_preset or Config.DEFAULT_QUALITY
        preset_config = Config.VOICE_QUALITY_PRESETS.get(quality_preset, Config.VOICE_QUALITY_PRESETS[Config.DEFAULT_QUALITY])
        buffer_size = preset_config['buffersize']
        bitrate = preset_config['bitrate']

        ffmpeg_opts = ['-vn', '-bufsize', buffer_size, '-b:a', bitrate]

        state = get_guild_state(song.requester.guild.id) if song.requester else None
        if state and state.active_filter:
            ffmpeg_opts.extend(['-af', state.active_filter])

        print(f"Refreshed stream URL for: {data.get('title', 'Unknown')}")

        ffmpeg_audio = discord.FFmpegPCMAudio(
            stream_url,
            executable=Config.FFMPEG_PATH,
            before_options=Config.FFMPEG_OPTIONS.get('before_options', ''),
            options=' '.join(ffmpeg_opts)
        )

        refreshed           = cls(ffmpeg_audio, data=data, volume=song.volume)
        refreshed.requester = song.requester
        return refreshed

    def format_duration(self):
        return format_duration(self.duration)

class GuildMusicState:
    def __init__(self, guild_id):
        self.guild_id            = guild_id
        self.queue               = []
        self.current_song        = None
        self.skip_votes          = set()
        self.is_paused           = False
        self.volume              = Config.DEFAULT_VOLUME / 100
        self.now_playing_message = None
        self.loop_mode           = 'off'
        self.autoplay            = False
        self.history             = []
        self.song_history        = []  # stores last 10 YTDLSource for prev button
        self.song_start_time     = None
        self.pause_start_time    = None
        self.paused_duration     = 0
        self.active_filter       = None # format: filter string

    def get_elapsed(self):
        import time
        if self.song_start_time is None:
            return 0
        
        elapsed = time.time() - self.song_start_time
        
        if self.is_paused:
            # When paused, subtract the current pause duration
            if self.pause_start_time:
                elapsed -= (time.time() - self.pause_start_time)
        else:
            # When playing normally, subtract only accumulated paused time
            elapsed -= self.paused_duration
        
        return max(0, int(elapsed))

    def add_to_queue(self, song):
        if len(self.queue) >= Config.MAX_QUEUE_SIZE:
            return False
        self.queue.append(song)
        return True

    def remove_from_queue(self, index):
        if 0 <= index < len(self.queue):
            return self.queue.pop(index)
        return None

    def move_in_queue(self, from_idx, to_idx):
        if 0 <= from_idx < len(self.queue) and 0 <= to_idx < len(self.queue):
            song = self.queue.pop(from_idx)
            self.queue.insert(to_idx, song)
            return True
        return False

    def shuffle(self):
        import random
        random.shuffle(self.queue)

    def clear(self):
        self.queue.clear()
        self.skip_votes.clear()
        self.song_history.clear()
        _prefetch_cache.pop(self.guild_id, None)

    def get_queue_text(self, start=0, count=10):
        if not self.queue:
            return "Queue is empty"
        lines = []
        for i, song in enumerate(self.queue[start:start+count], start=start+1):
            duration = song.format_duration() if song.duration else "?:??"
            title    = song.title[:50] + "..." if len(song.title) > 50 else song.title
            lines.append(f"**{i}.** {title} | `{duration}`")
        if len(self.queue) > start + count:
            lines.append(f"*...and {len(self.queue) - start - count} more*")
        return "\n".join(lines)

guild_states = {}

def get_guild_state(guild_id):
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusicState(guild_id)
    return guild_states[guild_id]

def cleanup_guild_state(guild_id):
    if guild_id in guild_states:
        del guild_states[guild_id]
    _prefetch_cache.pop(guild_id, None)

async def fetch_autoplay_suggestion(song, loop, history, song_history=None):
    def _fetch():
        import ytmusicapi
        ytm = ytmusicapi.YTMusic()
        video_id = song.data.get('id')
        if not video_id:
            import re
            url = song.webpage_url or song.url or ""
            match = re.search(r"v=([a-zA-Z0-9_-]+)", url)
            if match:
                video_id = match.group(1)
            else:
                match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
                if match:
                    video_id = match.group(1)

        if not video_id:
            results = ytm.search(song.title, filter="songs", limit=1)
            if results and results[0].get('videoId'):
                video_id = results[0]['videoId']

        if not video_id:
            return None

        try:
            # YouTube Music's 'watch playlist' is essentially their algorithmic radio
            watch = ytm.get_watch_playlist(videoId=video_id, radio=True, limit=50)
            tracks = watch.get('tracks', [])

            # Get artists from recent songs to maintain 'vibe' consistency
            recent_artists = set()
            if song_history:
                for s in song_history[-3:]:
                    if hasattr(s, 'uploader'): recent_artists.add(s.uploader.lower())

            candidates = []
            for track in tracks:
                t_id = track.get('videoId')
                if not t_id or t_id == video_id or t_id in history:
                    continue

                # Spotify-style scoring logic
                score = 0
                t_artists = [a.get('name', '').lower() for a in track.get('artists', [])]

                # Favor related artists (vibe) while allowing new ones (discovery)
                if any(artist in recent_artists for artist in t_artists):
                    score += 15 # High relevance
                else:
                    score += 5  # Exploration

                candidates.append((score, track))

            if candidates:
                import random
                # Sort by score and pick from top 10 for high-quality transitions
                candidates.sort(key=lambda x: x[0], reverse=True)
                top_pool = candidates[:10]
                chosen_score, chosen_track = random.choice(top_pool)
                return f"https://www.youtube.com/watch?v={chosen_track['videoId']}"

        except Exception as e:
            print(f"ytmusicapi error: {e}")
        return None

    next_url = await loop.run_in_executor(None, _fetch)
    if next_url:
        return await YTDLSource.from_url(next_url, loop=loop, requester=song.requester)
    return None

async def play_next_song(voice_client, guild_state, bot_loop):
    from stats_store import record_play

    loop_mode = guild_state.loop_mode
    previous_song = guild_state.current_song

    if loop_mode == 'one' and guild_state.current_song:
        next_song = guild_state.current_song
    elif guild_state.queue:
        # Check prefetch cache first
        cached = _prefetch_cache.pop(guild_state.guild_id, None)
        queued = guild_state.queue.pop(0)

        if cached and cached.webpage_url == queued.webpage_url:
            print(f"Using pre-fetched: {cached.title}")
            next_song = cached
        else:
            if cached:
                try:
                    cached.original.cleanup()
                except Exception:
                    pass
            next_song = queued

        if loop_mode == 'all' and guild_state.current_song:
            guild_state.queue.append(guild_state.current_song)
    else:
        if loop_mode == 'all' and guild_state.current_song:
            next_song = guild_state.current_song
        elif guild_state.autoplay and guild_state.current_song:
            print("Autoplay looking for next song...")
            try:
                # Check prefetch cache first
                cached = _prefetch_cache.pop(guild_state.guild_id, None)
                if cached:
                    print(f"Using pre-fetched autoplay: {cached.title}")
                    next_song = cached
                else:
                    auto_song = await fetch_autoplay_suggestion(guild_state.current_song, bot_loop, guild_state.history, guild_state.song_history)
                    if auto_song:
                        next_song = auto_song
                    else:
                        guild_state.current_song = None
                        if getattr(voice_client, 'client', None):
                            voice_client.client.dispatch('track_update', voice_client.guild, guild_state)
                        return
            except Exception as e:
                print(f"Autoplay failed: {e}")
                guild_state.current_song = None
                if getattr(voice_client, 'client', None):
                    voice_client.client.dispatch('track_update', voice_client.guild, guild_state)
                return
        else:
            guild_state.current_song = None
            if getattr(voice_client, 'client', None):
                voice_client.client.dispatch('track_update', voice_client.guild, guild_state)
            return

    guild_state.skip_votes.clear()

    # Record history
    v_id = next_song.data.get('id')
    if not v_id:
        import re
        url = next_song.webpage_url or next_song.url or ""
        match = re.search(r"v=([a-zA-Z0-9_-]+)", url)
        if match:
            v_id = match.group(1)
        else:
            match = re.search(r"youtu\.be/([a-zA-Z0-9_-]+)", url)
            if match:
                v_id = match.group(1)
    if v_id and v_id not in guild_state.history:
        guild_state.history.append(v_id)
        if len(guild_state.history) > 50:
            guild_state.history.pop(0)

    # ── FIX #6: Refresh BEFORE setting to guild_state ────────────────────────
    # Only refresh if it's an old song or from autoplay
    # If it's a fresh YTDLSource with an active original stream, we don't need to refresh
    if not hasattr(next_song, 'original') or next_song.original is None:
        try:
            next_song = await YTDLSource.refresh(next_song, loop=bot_loop)
        except Exception as e:
            print(f"Error refreshing stream URL for '{next_song.title}': {e}")
            # Try next song instead of raising
            return await play_next_song(voice_client, guild_state, bot_loop)

    # NOW set to guild_state after refresh succeeds
    guild_state.current_song = next_song

    def after_playing(error):
        if error:
            print(f"Player error: {error}")
        try:
            asyncio.run_coroutine_threadsafe(
                play_next_song(voice_client, guild_state, bot_loop),
                bot_loop
            )
        except Exception as e:
            print(f"Error scheduling next song: {e}")

    try:
        if not voice_client.is_connected():
            print("Voice client not connected, cannot play")
            guild_state.queue.insert(0, next_song)
            return

        print(f"Starting playback: {next_song.title}")
        import time
        guild_state.song_start_time  = time.time()
        guild_state.paused_duration  = 0
        guild_state.pause_start_time = None

        # ── FIX #3: Better error handling ──────────────────────────────────────
        if next_song and hasattr(next_song, 'read'):
            voice_client.play(next_song, after=after_playing)
        else:
            raise Exception("Invalid audio source. Ensure FFmpeg is working correctly and cookies.txt exists if needed.")

        if hasattr(voice_client.source, 'volume') and voice_client.source.volume is not None:
            voice_client.source.volume = guild_state.volume

        record_play(
            guild_state.guild_id,
            next_song.title,
            duration=next_song.duration,
            uploader=next_song.uploader if hasattr(next_song, 'uploader') else None
        )
        print(f"Now playing: {next_song.title}")

        # Save to song history for prev button
        if previous_song and previous_song != next_song:
            guild_state.song_history.append(previous_song)
            if len(guild_state.song_history) > 10:
                guild_state.song_history.pop(0)

        if getattr(voice_client, 'client', None):
            voice_client.client.dispatch('track_update', voice_client.guild, guild_state)

        # Start pre-fetching next song in background
        if guild_state.queue:
            asyncio.run_coroutine_threadsafe(
                prefetch_next(guild_state, bot_loop),
                bot_loop
            )
        elif guild_state.autoplay:
            # Pre-fetch autoplay suggestion in background
            asyncio.run_coroutine_threadsafe(
                _prefetch_autoplay(guild_state, next_song, bot_loop),
                bot_loop
            )

    except Exception as e:
        print(f"Error starting playback: {e}")
        import traceback
        traceback.print_exc()
