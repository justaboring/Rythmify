import asyncio
import math
import random
import re
import struct
import time
import traceback
import discord
import yt_dlp as youtube_dl
from config import Config
from utils import format_duration
from quality_store import get_quality
import concurrent.futures

process_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)  # Optimized for 4 concurrent downloads

def _extract_info_sync(url, download=False, quality_preset=None):
    """Run yt-dlp extraction in a thread pool executor.

    Args:
        url: The URL or search query to extract.
        download: Whether to download the file (vs. just extracting info).
        quality_preset: Optional quality preset key from Config.VOICE_QUALITY_PRESETS.

    Returns:
        A dict with extracted media information from yt-dlp.
    """
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
MAX_CACHE_SIZE = 10


def _cache_put(guild_id, source):
    """Add a source to the prefetch cache, evicting oldest if full."""
    if len(_prefetch_cache) >= MAX_CACHE_SIZE:
        oldest_key = next(iter(_prefetch_cache))
        _prefetch_cache.pop(oldest_key)
    _prefetch_cache[guild_id] = source

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
            _cache_put(guild_state.guild_id, refreshed)
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
            _cache_put(guild_state.guild_id, auto_song)
            print(f"Autoplay pre-fetch done: {auto_song.title}")
    except Exception as e:
        print(f"Autoplay pre-fetch failed: {e}")


class CrossfadeSource(discord.AudioSource):
    """Crossfade between two audio sources over a given duration."""
    SAMPLE_WIDTH = 2   # 16-bit PCM
    CHANNELS     = 2   # stereo

    def __init__(self, source_a, source_b, duration=3.0, volume=0.5):
        self.source_a       = source_a   # fading out
        self.source_b       = source_b   # fading in
        self.duration       = max(duration, 0.5)
        self.volume         = volume
        self._started       = time.time()
        self._finished      = False
        self._fade_complete = False  # True once fade is done, still reading source_b

    def read(self):
        if self._finished:
            return b''

        # After fade completes, just play source_b at full volume
        if self._fade_complete:
            data = self.source_b.read()
            if not data:
                self._finished = True
                return b''
            return self._scale(data, self.volume)

        elapsed  = time.time() - self._started
        progress = min(elapsed / self.duration, 1.0)
        fade_out = max(0.0, 1.0 - progress)
        fade_in  = progress

        data_a = self.source_a.read()
        data_b = self.source_b.read()

        # Both ended
        if not data_a and not data_b:
            self._finished = True
            return b''

        # source_a ended — transition to source_b-only mode
        if not data_a:
            self._fade_complete = True
            return self._scale(data_b, self.volume)

        # source_b ended early (shouldn't happen normally)
        if not data_b:
            return self._scale(data_a, self.volume * fade_out)

        # Both active — blend
        samples_a = struct.unpack(f'<{len(data_a) // self.SAMPLE_WIDTH}h', data_a)
        samples_b = struct.unpack(f'<{len(data_b) // self.SAMPLE_WIDTH}h', data_b)
        count = min(len(samples_a), len(samples_b))
        mixed = [
            int(samples_a[i] * fade_out * self.volume + samples_b[i] * fade_in * self.volume)
            for i in range(count)
        ]
        mixed = [max(-32768, min(32767, s)) for s in mixed]
        return struct.pack(f'<{count}h', *mixed)

    @staticmethod
    def _scale(data, vol):
        samples = struct.unpack(f'<{len(data) // 2}h', data)
        scaled  = [max(-32768, min(32767, int(s * vol))) for s in samples]
        return struct.pack(f'<{len(scaled)}h', *scaled)

    def cleanup(self):
        try:
            if hasattr(self.source_a, 'cleanup'):
                self.source_a.cleanup()
        except Exception:
            pass
        try:
            if hasattr(self.source_b, 'cleanup'):
                self.source_b.cleanup()
        except Exception:
            pass


class YTDLSource(discord.PCMVolumeTransformer):
    """Audio source that wraps yt-dlp extracted media as a Discord audio stream.

    Fetches audio from YouTube or other supported sites via yt-dlp, optionally
    applies quality presets and audio filters through FFmpeg, and provides the
    result as a PCM-volume-transformable audio source for Discord voice.
    """

    def __init__(self, source, *, data, volume=0.5):
        """Initialise the audio source.

        Args:
            source: An FFmpegPCMAudio instance (the raw audio stream).
            data: Metadata dict from yt-dlp extraction (title, url, duration, …).
            volume: Initial volume level (0.0 – 1.0).
        """
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
        """Create a YTDLSource from a URL or search query.

        Runs yt-dlp extraction in a thread-pool executor, then builds an FFmpeg
        audio stream with the appropriate quality preset and audio filter.

        Args:
            url: A YouTube / supported-site URL, or a ``ytsearch:…`` query.
            loop: The asyncio event loop (defaults to the running loop).
            stream: Whether to stream (True) or download the file (False).
            requester: The Discord member who requested the song.
            quality_preset: Quality preset name, or None to use guild default.

        Returns:
            A fully-initialised YTDLSource ready for playback.
        """
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
        print(f"Extracted: {data.get('title', 'Unknown')} ({data.get('format', '?')})")

        # Build FFmpeg options with quality-specific buffer
        active_filter = None
        if requester and hasattr(requester, 'guild'):
            active_filter = get_guild_state(requester.guild.id).active_filter

        base_options = cls._build_ffmpeg_options(quality_preset, active_filter)

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

    @staticmethod
    def _build_ffmpeg_options(quality_preset=None, active_filter=None):
        """Build FFmpeg options string from quality preset and filter."""
        preset = quality_preset or Config.DEFAULT_QUALITY
        cfg = Config.VOICE_QUALITY_PRESETS.get(preset, Config.VOICE_QUALITY_PRESETS[Config.DEFAULT_QUALITY])
        opts = ['-vn', '-bufsize', cfg['buffersize'], '-b:a', cfg['bitrate']]
        if active_filter:
            opts.extend(['-af', active_filter])
        return ' '.join(opts)

    @classmethod
    def _pick_best(cls, entries, query):
        """Score and pick the best match from a list of yt-dlp search entries.

        Applies a heuristic that favours official audio sources (Topic channels),
        penalises music videos and very short/long tracks, and rewards title
        keyword overlap with the original query.

        Args:
            entries: List of yt-dlp result dicts.
            query: The original search string (used for keyword matching).

        Returns:
            The highest-scoring entry dict, or the first entry as fallback.
        """
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
        """Search YouTube and return the best-matching YTDLSource.

        Performs a ``ytsearch5:`` query via yt-dlp, scores the results with
        ``_pick_best``, then loads the winner as a playable source.

        Args:
            query: Free-text search string.
            loop: The asyncio event loop.
            requester: The Discord member who requested the song.

        Returns:
            A YTDLSource for the top-ranked result.
        """
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
        """Re-extract the stream URL for an existing song (URLs expire).

        Calls yt-dlp again on the same webpage URL to get a fresh streaming
        URL, then rebuilds the FFmpegPCMAudio with current filters/quality.

        Args:
            song: The YTDLSource instance to refresh.
            loop: The asyncio event loop.
            quality_preset: Optional override quality preset.

        Returns:
            A new YTDLSource with a fresh stream URL.
        """
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
        state = get_guild_state(song.requester.guild.id) if song.requester else None
        active_filter = state.active_filter if state else None
        ffmpeg_options = cls._build_ffmpeg_options(quality_preset, active_filter)

        print(f"Refreshed: {data.get('title', 'Unknown')}")

        ffmpeg_audio = discord.FFmpegPCMAudio(
            stream_url,
            executable=Config.FFMPEG_PATH,
            before_options=Config.FFMPEG_OPTIONS.get('before_options', ''),
            options=ffmpeg_options
        )

        refreshed           = cls(ffmpeg_audio, data=data, volume=song.volume)
        refreshed.requester = song.requester
        return refreshed

    def format_duration(self):
        """Return the song duration as a human-readable MM:SS / HH:MM:SS string.

        Delegates to ``utils.format_duration``.
        """
        return format_duration(self.duration)

class GuildMusicState:
    """Per-guild playback state, including queue, loop mode, and filter settings.

    One instance exists per guild that has ever played music.  Access via
    ``get_guild_state(guild_id)``.
    """

    def __init__(self, guild_id):
        """Initialise an empty music state for a guild.

        Args:
            guild_id: The Discord guild (server) ID.
        """
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
        self.active_filter       = None  # format: filter string
        self.crossfade_seconds   = Config.CROSSFADE_SECONDS
        self._crossfade_task     = None
        self._crossfade_consumed_next = False

    def get_elapsed(self):
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
        random.shuffle(self.queue)

    def clear(self):
        self.queue.clear()
        self.skip_votes.clear()
        self.song_history.clear()
        self._crossfade_consumed_next = False
        if self._crossfade_task and not self._crossfade_task.done():
            self._crossfade_task.cancel()
        self._crossfade_task = None
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


guild_states: dict[int, GuildMusicState] = {}


def get_guild_state(guild_id: int) -> GuildMusicState:
    """Return the GuildMusicState for a guild, creating it on first access.

    The returned state object is shared — all callers mutate the same instance.
    """
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusicState(guild_id)
    return guild_states[guild_id]


def cleanup_guild_state(guild_id: int) -> None:
    """Remove a guild's playback state and drop its prefetch cache entry."""
    if guild_id in guild_states:
        del guild_states[guild_id]
    _prefetch_cache.pop(guild_id, None)


async def fetch_autoplay_suggestion(song, loop, history, song_history=None):
    """Fetch an autoplay suggestion from YouTube Music based on the current song.

    Uses ytmusicapi to get a watch playlist (radio) for the current song's video
    ID, then scores candidates by artist overlap with recent history for
    coherent transitions.

    Args:
        song: The currently playing YTDLSource.
        loop: The asyncio event loop.
        history: List of recently-played video IDs (to avoid repeats).
        song_history: Optional list of recent YTDLSource instances.

    Returns:
        A YTDLSource for the suggested next track, or None if nothing suitable.
    """
    def _fetch():
        import ytmusicapi
        ytm = ytmusicapi.YTMusic()
        video_id = song.data.get('id')
        if not video_id:
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

async def _crossfade_timer(voice_client, guild_state, bot_loop):
    """Wait until near end of current song, then start crossfade into the next track."""
    try:
        song = guild_state.current_song
        if not song or not song.duration:
            return

        duration = song.duration
        crossfade_secs = guild_state.crossfade_seconds

        # Skip crossfade for very short songs
        if duration < crossfade_secs * 2:
            return

        # Wait until (crossfade_secs) before the song ends
        wait_time = max(duration - crossfade_secs, 1)
        await asyncio.sleep(wait_time)

        # Bail if song was skipped/stopped while we slept
        if guild_state.current_song != song:
            return
        if not voice_client.is_playing() or voice_client.is_paused():
            return

        # Determine next track
        next_song = None
        if guild_state.queue:
            next_song = guild_state.queue.pop(0)
        elif guild_state.autoplay and guild_state.current_song:
            print("[Crossfade] Fetching autoplay suggestion...")
            next_song = await fetch_autoplay_suggestion(
                guild_state.current_song, bot_loop,
                guild_state.history, guild_state.song_history
            )

        if not next_song:
            return

        # Refresh/load the next song stream
        if not hasattr(next_song, 'original') or next_song.original is None:
            try:
                next_song = await YTDLSource.refresh(next_song, loop=bot_loop)
            except Exception as e:
                print(f"[Crossfade] Failed to refresh next song: {e}")
                # Put it back in queue so normal transition handles it
                if guild_state.queue or guild_state.autoplay:
                    pass  # already popped, can't undo cleanly
                return

        # Build the crossfade source
        current_source = voice_client.source
        if not current_source:
            return

        crossfade_source = CrossfadeSource(
            current_source, next_song,
            duration=crossfade_secs,
            volume=guild_state.volume
        )

        # Record history for next_song
        v_id = next_song.data.get('id')
        if not v_id:
            url = next_song.webpage_url or next_song.url or ""
            m = re.search(r"v=([a-zA-Z0-9_-]+)", url)
            if m:
                v_id = m.group(1)
        if v_id and v_id not in guild_state.history:
            guild_state.history.append(v_id)
            if len(guild_state.history) > 50:
                guild_state.history.pop(0)

        # Save current song to song_history for prev button
        if guild_state.current_song:
            guild_state.song_history.append(guild_state.current_song)
            if len(guild_state.song_history) > 10:
                guild_state.song_history.pop(0)

        # Swap source — player thread picks this up on the next read cycle
        guild_state.current_song = next_song
        guild_state._crossfade_consumed_next = True
        voice_client._source = crossfade_source

        # Re-arm the after callback so play_next_song fires when crossfade finishes
        def after_crossfade(error):
            if error:
                print(f"[Crossfade] Player error: {error}")
            try:
                asyncio.run_coroutine_threadsafe(
                    play_next_song(voice_client, guild_state, bot_loop),
                    bot_loop
                )
            except Exception as e:
                print(f"[Crossfade] Error scheduling next song: {e}")

        voice_client._after = after_crossfade
        print(f"[Crossfade] Started crossfade into: {next_song.title}")

    except asyncio.CancelledError:
        pass  # Expected when song is skipped/stopped
    except Exception as e:
        print(f"[Crossfade] Error: {e}")
        traceback.print_exc()


async def play_next_song(voice_client, guild_state, bot_loop):
    """Play the next song in the queue, respecting loop, autoplay, and crossfade.

    Core playback loop: determines the next source based on the current
    ``loop_mode`` and ``autoplay`` state, refreshes expired stream URLs,
    handles prefetch-cache hits, schedules crossfade timers, and dispatches
    ``track_update`` events for the UI panel.

    Args:
        voice_client: The guild's ``discord.VoiceClient``.
        guild_state: The guild's ``GuildMusicState`` instance.
        bot_loop: The asyncio event loop to schedule follow-up work on.
    """
    from stats_store import record_play

    # Cancel any pending crossfade task
    if guild_state._crossfade_task and not guild_state._crossfade_task.done():
        guild_state._crossfade_task.cancel()
    guild_state._crossfade_task = None

    loop_mode = guild_state.loop_mode
    previous_song = guild_state.current_song

    if guild_state._crossfade_consumed_next:
        # Crossfade timer already set current_song and loaded its stream
        guild_state._crossfade_consumed_next = False
        next_song = guild_state.current_song
        from_crossfade = True
        if loop_mode == 'all' and previous_song and previous_song != next_song:
            guild_state.queue.append(previous_song)
    elif loop_mode == 'one' and guild_state.current_song:
        next_song = guild_state.current_song
        from_crossfade = False
    elif guild_state.queue:
        from_crossfade = False
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
        from_crossfade = False
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
        guild_state.song_start_time  = time.time()
        guild_state.paused_duration  = 0
        guild_state.pause_start_time = None

        if from_crossfade:
            # CrossfadeSource is already playing — don't restart playback
            print(f"[Crossfade] Continuing playback: {next_song.title}")
        else:
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

        # Schedule crossfade timer if enabled
        if (guild_state.crossfade_seconds > 0
                and next_song.duration
                and (guild_state.queue or guild_state.autoplay)):
            guild_state._crossfade_task = asyncio.ensure_future(
                _crossfade_timer(voice_client, guild_state, bot_loop)
            )

    except Exception as e:
        print(f"Error starting playback: {e}")
        traceback.print_exc()
