import asyncio
import discord
import yt_dlp as youtube_dl
from config import Config
from utils import format_duration

ytdl = youtube_dl.YoutubeDL(Config.YTDL_FORMAT_OPTIONS)





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
    async def from_url(cls, url, *, loop=None, stream=True, requester=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None,
            lambda: ytdl.extract_info(url, download=not stream)
        )

        if 'entries' in data:
            data = data['entries'][0]

        filename = data['url'] if stream else ytdl.prepare_filename(data)

        print(f"Extracted audio URL for: {data.get('title', 'Unknown')}")
        print(f"Format: {data.get('format', 'Unknown')}")
        print(f"Protocol: {data.get('protocol', 'Unknown')}")
        if filename:
            print(f"URL starts with: {filename[:60]}...")

        try:
            ffmpeg_audio = discord.FFmpegPCMAudio(
                filename,
                executable=Config.FFMPEG_PATH,
                before_options=Config.FFMPEG_OPTIONS.get('before_options', ''),
                options=Config.FFMPEG_OPTIONS.get('options', '-vn')
            )
        except Exception as e:
            print(f"Error creating FFmpegPCMAudio: {e}")
            raise

        source = cls(ffmpeg_audio, data=data)
        source.requester = requester
        return source

    @classmethod
    def _pick_best(cls, entries, query):
        """Score candidates by view count + title relevance, return best entry."""
        query_words = set(query.lower().split())
        best = None
        best_score = -1

        for entry in entries:
            if not entry:
                continue

            views = entry.get('view_count') or 0
            title = (entry.get('title') or '').lower()
            duration = entry.get('duration') or 0

            # Skip likely non-music: very short (<30s) or very long (>10min live streams)
            if duration < 30 or duration > 1500:
                continue

            # View score: log scale 0-50
            import math
            view_score = math.log10(views + 1) * 2.5 if views > 0 else 0

            # Relevance: ratio of query words found in title
            matched = sum(1 for w in query_words if w in title)
            relevance_score = (matched / max(len(query_words), 1)) * 25

            # Bonus: official/audio channels
            uploader = (entry.get('uploader') or '').lower()
            channel_bonus = 10 if any(k in uploader or k in title for k in ['official', 'audio', 'topic']) else 0

            score = view_score + relevance_score + channel_bonus

            if score > best_score:
                best_score = score
                best = entry

        # Fallback to first if all filtered out
        return best or entries[0]

    @classmethod
    async def search(cls, query, *, loop=None, requester=None):
        loop = loop or asyncio.get_event_loop()

        # Fetch 5 candidates
        raw = await loop.run_in_executor(
            None,
            lambda: ytdl.extract_info(f"ytsearch5:{query}", download=False)
        )
        entries = [e for e in (raw.get('entries') or []) if e]
        if not entries:
            raise Exception(f"No results for: {query}")

        best = cls._pick_best(entries, query)

        # Now get full stream URL for the chosen entry
        webpage_url = best.get('webpage_url') or best.get('url')
        return await cls.from_url(webpage_url, loop=loop, requester=requester)

    @classmethod
    async def refresh(cls, song, *, loop=None):
        """Re-extract a fresh stream URL right before playback."""
        loop = loop or asyncio.get_event_loop()
        webpage_url = song.webpage_url
        if not webpage_url:
            return song

        data = await loop.run_in_executor(
            None,
            lambda: ytdl.extract_info(webpage_url, download=False)
        )

        if 'entries' in data:
            data = data['entries'][0]

        stream_url = data['url']

        print(f"Refreshed stream URL for: {data.get('title', 'Unknown')}")
        print(f"Format: {data.get('format', 'Unknown')}")
        print(f"URL starts with: {stream_url[:60]}...")

        ffmpeg_audio = discord.FFmpegPCMAudio(
            stream_url,
            executable=Config.FFMPEG_PATH,
            before_options=Config.FFMPEG_OPTIONS.get('before_options', ''),
            options=Config.FFMPEG_OPTIONS.get('options', '-vn')
        )

        refreshed = cls(ffmpeg_audio, data=data, volume=song.volume)
        refreshed.requester = song.requester
        return refreshed

    def format_duration(self):
        return format_duration(self.duration)


class GuildMusicState:
    def __init__(self, guild_id):
        self.guild_id = guild_id
        self.queue = []
        self.current_song = None
        self.skip_votes = set()
        self.is_paused = False
        self.volume = Config.DEFAULT_VOLUME / 100
        self.now_playing_message = None
        self.loop_mode = 'off'  # 'off' | 'one' | 'all'
        self.song_start_time = None   # time.time() when current song started
        self.pause_start_time = None  # time.time() when paused
        self.paused_duration = 0      # total seconds spent paused

    def get_elapsed(self):
        """Seconds elapsed in current song, accounting for pauses."""
        import time
        if self.song_start_time is None:
            return 0
        elapsed = time.time() - self.song_start_time - self.paused_duration
        if self.is_paused and self.pause_start_time:
            elapsed -= (time.time() - self.pause_start_time)
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
        if 0 <= from_idx < len(self.queue):
            if 0 <= to_idx < len(self.queue):
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

    def get_queue_text(self, start=0, count=10):
        if not self.queue:
            return "Queue is empty"

        lines = []
        for i, song in enumerate(self.queue[start:start+count], start=start+1):
            duration = song.format_duration() if song.duration else "?:??"
            title = song.title[:50] + "..." if len(song.title) > 50 else song.title
            lines.append(f"**{i}.** {title} | `{duration}`")

        if len(self.queue) > start + count:
            lines.append(f"*...and {len(self.queue) - start - count} more*")

        return "\n".join(lines)


# Global state storage
guild_states = {}


def get_guild_state(guild_id):
    if guild_id not in guild_states:
        guild_states[guild_id] = GuildMusicState(guild_id)
    return guild_states[guild_id]


def cleanup_guild_state(guild_id):
    if guild_id in guild_states:
        del guild_states[guild_id]


async def play_next_song(voice_client, guild_state, bot_loop):
    loop_mode = guild_state.loop_mode

    # Loop one — re-queue current song at front
    if loop_mode == 'one' and guild_state.current_song:
        next_song = guild_state.current_song
    elif guild_state.queue:
        next_song = guild_state.queue.pop(0)
        # Loop all — push finished song to back
        if loop_mode == 'all' and guild_state.current_song:
            guild_state.queue.append(guild_state.current_song)
    else:
        # Loop all but queue empty (only 1 song ever) — replay current
        if loop_mode == 'all' and guild_state.current_song:
            next_song = guild_state.current_song
        else:
            guild_state.current_song = None
            return

    guild_state.current_song = next_song
    guild_state.skip_votes.clear()

    try:
        next_song = await YTDLSource.refresh(next_song, loop=bot_loop)
        guild_state.current_song = next_song
    except Exception as e:
        print(f"Error refreshing stream URL for '{next_song.title}': {e}")
        asyncio.run_coroutine_threadsafe(
            play_next_song(voice_client, guild_state, bot_loop),
            bot_loop
        )
        return

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
        guild_state.song_start_time = time.time()
        guild_state.paused_duration = 0
        guild_state.pause_start_time = None
        voice_client.play(next_song, after=after_playing)

        if hasattr(voice_client.source, 'volume') and voice_client.source.volume is not None:
            voice_client.source.volume = guild_state.volume

        print(f"Now playing: {next_song.title}")

    except Exception as e:
        print(f"Error starting playback: {e}")
        import traceback
        traceback.print_exc()