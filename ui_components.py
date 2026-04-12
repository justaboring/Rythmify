import discord
from config import Config


class Colors:
    CREAM_WHITE  = 0xFFFEF9
    SOFT_WHITE   = 0xF0F0F0
    LIGHT_BLUE   = 0xADD8E6
    PASTEL_PINK  = 0xFFB6C1
    MINT         = 0x98FB98
    LAVENDER     = 0xE6E6FA
    PEACH        = 0xFFDAB9
    ACCENT_BLUE  = 0x5865F2
    ACCENT_GREEN = 0x57F287
    ACCENT_RED   = 0xED4245
    TEAL         = 0x1ABC9C


# ──────────────────────────────────────────────
# DASHBOARD EMBED
# ──────────────────────────────────────────────

def create_dashboard_embed(guild_state, voice_client=None, guild=None) -> discord.Embed:
    from stats_store import get_stats

    embed = discord.Embed(title="📊 Music Dashboard", color=Colors.ACCENT_BLUE)

    # Who's listening
    if voice_client and voice_client.channel:
        members = [m for m in voice_client.channel.members if not m.bot]
        names   = "\n".join(f"🎧 {m.display_name}" for m in members) if members else "*Nobody here*"
        embed.add_field(
            name=f"🔊 {voice_client.channel.name} ({len(members)} listening)",
            value=names,
            inline=False
        )
    else:
        embed.add_field(name="🔊 Voice", value="*Bot not in voice channel*", inline=False)

    # Queue full list
    if guild_state.current_song:
        st  = "⏸" if guild_state.is_paused else "▶"
        dur = guild_state.current_song.format_duration() if guild_state.current_song.duration else "?:??"
        now = f"{st} **{guild_state.current_song.title[:55]}** — `{dur}`"
    else:
        now = "*Nothing playing*"

    if guild_state.queue:
        lines = [now]
        for i, s in enumerate(guild_state.queue[:10], start=1):
            d = s.format_duration() if s.duration else "?:??"
            t = s.title[:50] + "…" if len(s.title) > 50 else s.title
            lines.append(f"`{i}.` {t} — `{d}`")
        if len(guild_state.queue) > 10:
            lines.append(f"*…and {len(guild_state.queue) - 10} more*")
        queue_text = "\n".join(lines)
    else:
        queue_text = now + "\n*Queue is empty*"

    embed.add_field(name="📋 Queue", value=queue_text, inline=False)

    # Stats
    if guild:
        stats = get_stats(guild.id)
        total = stats["total_played"]
        top   = stats["top_songs"]
        top_text = "\n".join(
            f"`{i}.` {title[:45]} — `{count}x`"
            for i, (title, count) in enumerate(top, start=1)
        ) if top else "*No songs played yet*"
        embed.add_field(
            name=f"🎵 Stats — {total} songs played total",
            value=top_text,
            inline=False
        )

    embed.set_footer(text=f"Volume: {int(guild_state.volume * 100)}%  |  {len(guild_state.queue)} in queue")
    return embed


# ──────────────────────────────────────────────
# CONTROL PANEL VIEW
# ──────────────────────────────────────────────

class ControlPanelView(discord.ui.View):
    def __init__(self, music_cog, guild_state, page=0, timeout=None):
        super().__init__(timeout=timeout)
        self.music_cog   = music_cog
        self.guild_state = guild_state
        self.page        = page
        self.per_page    = 8
        self._update_button_states()

    def _update_button_states(self):
        for child in self.children:
            if getattr(child, 'custom_id', None) == "cp_pause":
                child.label = "Resume" if self.guild_state.is_paused else "Pause"
                child.emoji = discord.PartialEmoji(name="▶️") if self.guild_state.is_paused else discord.PartialEmoji(name="⏸️")
                child.style = discord.ButtonStyle.secondary if self.guild_state.is_paused else discord.ButtonStyle.primary
            elif getattr(child, 'custom_id', None) == "cp_autoplay":
                child.style = discord.ButtonStyle.success if getattr(self.guild_state, 'autoplay', False) else discord.ButtonStyle.secondary

    @discord.ui.button(emoji="🔉", label="Vol -",    style=discord.ButtonStyle.secondary, custom_id="cp_vol_down",  row=0)
    async def vol_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.volume_down_callback(interaction)

    @discord.ui.button(emoji="⏮️", label="Prev",     style=discord.ButtonStyle.primary, custom_id="cp_prev_song", row=0)
    async def prev_song_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏮️ No previous song support yet.", ephemeral=True)

    @discord.ui.button(emoji="⏸️", label="Pause",    style=discord.ButtonStyle.primary,   custom_id="cp_pause",     row=0)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.pause_callback(interaction)
        self._update_button_states()
        await self._refresh_panel(interaction)

    @discord.ui.button(emoji="⏭️", label="Skip",     style=discord.ButtonStyle.primary, custom_id="cp_skip",      row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.skip_callback(interaction)

    @discord.ui.button(emoji="🔊", label="Vol +",    style=discord.ButtonStyle.secondary, custom_id="cp_vol_up",    row=0)
    async def vol_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.volume_up_callback(interaction)

    @discord.ui.button(emoji="🔀", label="Shuffle",  style=discord.ButtonStyle.secondary, custom_id="cp_shuffle",  row=1)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.shuffle_callback(interaction)
        await self._refresh_panel(interaction)

    @discord.ui.button(emoji="🔁", label="AutoPlay", style=discord.ButtonStyle.secondary, custom_id="cp_autoplay", row=1)
    async def autoplay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.guild_state.autoplay = not self.guild_state.autoplay
        self._update_button_states()
        state_str = "ON" if self.guild_state.autoplay else "OFF"
        await interaction.response.send_message(f"🔁 AutoPlay is now **{state_str}**", ephemeral=True)
        await self._refresh_panel(interaction)

    @discord.ui.button(emoji="🤍", label="Like",     style=discord.ButtonStyle.secondary, custom_id="cp_like",     row=1)
    async def like_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🤍 Favorited!", ephemeral=True)

    @discord.ui.button(emoji="⏹️", label="Stop",    style=discord.ButtonStyle.danger,    custom_id="cp_stop",     row=1)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.stop_callback(interaction)
        await self._refresh_panel(interaction)

    @discord.ui.button(emoji="📊", label="Stats",    style=discord.ButtonStyle.secondary, custom_id="cp_dash",     row=1)
    async def dashboard_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.dashboard_callback(interaction)

    async def _refresh_panel(self, interaction: discord.Interaction):
        self._update_button_states()
        embed = create_control_panel_embed(self.guild_state)
        try:
            msg = interaction.message
            if msg:
                await msg.edit(embed=embed, view=self)
        except Exception:
            pass

    def update_pause_button(self, is_paused: bool):
        pass


NowPlayingView = ControlPanelView

BANNER_URL = "https://i.imgur.com/4M7IWwP.png"


def create_control_panel_embed(guild_state) -> discord.Embed:
    if guild_state.current_song is None:
        embed = discord.Embed(
            title="Music Controller",
            description="Waiting for music…\nSend the name or link of a music",
            color=Colors.ACCENT_BLUE,
        )
        embed.set_image(url=BANNER_URL)
        embed.set_footer(text="Controller System")
        return embed

    song    = guild_state.current_song
    status  = "⏸ Paused" if guild_state.is_paused else "Now playing"
    title   = song.title[:80] + "…" if len(song.title) > 80 else song.title
    dur     = song.format_duration() if song.duration else "?:??"
    vol_pct = int(guild_state.volume * 100)

    next_line = ""
    if guild_state.queue:
        nxt     = guild_state.queue[0]
        nxt_t   = nxt.title[:50] + "…" if len(nxt.title) > 50 else nxt.title
        nxt_dur = nxt.format_duration() if nxt.duration else "?:??"
        next_line = f"**Next song:**\n{nxt_t} — `{nxt_dur}`\n\n"

    q_count     = len(guild_state.queue)
    q_dur_total = sum(s.duration or 0 for s in guild_state.queue)
    q_summary   = _fmt_dur(q_dur_total) if q_dur_total else "?:??"

    description = (
        f"{next_line}"
        f"**{status}**\n"
        f"**{title}** — `{dur}`\n"
    )
    if song.requester:
        description += f"Requested by {song.requester.mention}\n"
    if q_count:
        description += (
            f"\n`{q_count}` song{'s' if q_count != 1 else ''} in queue "
            f"for `{q_summary}` of listening  |  Volume: `{vol_pct}%`"
        )
    if getattr(guild_state, 'autoplay', False):
        description += "\n🔁 **AutoPlay is ON**"

    embed = discord.Embed(description=description, color=Colors.TEAL)
    if song.thumbnail:
        embed.set_image(url=song.thumbnail)
    embed.set_footer(text="Controller System")
    return embed


# ──────────────────────────────────────────────
# LEGACY HELPERS
# ──────────────────────────────────────────────

def create_panel_embed(guild_state, page=0, per_page=8):
    return create_control_panel_embed(guild_state)


def create_now_playing_embed(song, guild_state):
    return create_control_panel_embed(guild_state)


def create_queue_embed(guild_state, page=0, per_page=10):
    embed = discord.Embed(title="📋 Your Queue View", color=Colors.ACCENT_BLUE)

    if not guild_state.queue and not guild_state.current_song:
        embed.description = "Queue is empty."
        return embed

    lines = []
    if guild_state.current_song:
        s   = guild_state.current_song
        dur = s.format_duration() if s.duration else "?:??"
        st  = "⏸" if guild_state.is_paused else "▶"
        lines.append(f"{st} **{s.title[:60]}** — `{dur}` ← Now Playing")

    start = page * per_page
    for i, s in enumerate(guild_state.queue[start:start + per_page], start=start + 1):
        dur = s.format_duration() if s.duration else "?:??"
        t   = s.title[:55] + "…" if len(s.title) > 55 else s.title
        lines.append(f"`{i}.` {t} — `{dur}`")

    total = len(guild_state.queue)
    if total > start + per_page:
        lines.append(f"*…and {total - start - per_page} more*")

    embed.description = "\n".join(lines)
    return embed


def create_added_embed(song, position=None):
    dur   = song.format_duration() if song.duration else "?:??"
    title = song.title[:80] + "…" if len(song.title) > 80 else song.title
    pos   = f" at #{position}" if position else ""
    embed = discord.Embed(
        description=f"✅  Added **{title}** — `{dur}`  to the queue{pos}.",
        color=Colors.ACCENT_GREEN,
    )
    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)
    return embed


def create_error_embed(title, message):
    return discord.Embed(title=f"❌ {title}", description=message, color=Colors.ACCENT_RED)


def create_success_embed(title, message):
    return discord.Embed(title=f"✅ {title}", description=message, color=Colors.ACCENT_GREEN)


def create_info_embed(title, message):
    return discord.Embed(title=f"ℹ️ {title}", description=message, color=Colors.ACCENT_BLUE)


# ──────────────────────────────────────────────
# OTHER VIEWS
# ──────────────────────────────────────────────

class QueueView(discord.ui.View):
    def __init__(self, music_cog, guild_state, page=0):
        super().__init__(timeout=60)
        self.music_cog   = music_cog
        self.guild_state = guild_state
        self.page        = page
        self.per_page    = 10

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            await self.music_cog.update_queue_embed(interaction, self.page)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = len(self.guild_state.queue) // self.per_page
        if self.page < max_page:
            self.page += 1
            await self.music_cog.update_queue_embed(interaction, self.page)

    @discord.ui.button(emoji="🔀", label="Shuffle", style=discord.ButtonStyle.primary)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.shuffle_callback(interaction)

    @discord.ui.button(emoji="🗑️", label="Clear", style=discord.ButtonStyle.danger)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.clear_callback(interaction)


class SkipVoteView(discord.ui.View):
    def __init__(self, music_cog, current_votes, threshold):
        super().__init__(timeout=30)
        self.music_cog     = music_cog
        self.current_votes = current_votes
        self.threshold     = threshold

    @discord.ui.button(label="Vote to Skip", emoji="⏭️", style=discord.ButtonStyle.primary)
    async def vote_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.skip_vote_callback(interaction)

    def update_label(self, votes, threshold):
        for child in self.children:
            if hasattr(child, 'label'):
                child.label = f"Vote to Skip ({votes}/{threshold})"


class SongSelectView(discord.ui.View):
    def __init__(self, music_cog, songs, is_spotify=False):
        super().__init__(timeout=60)
        self.music_cog  = music_cog
        self.songs      = songs
        self.is_spotify = is_spotify

        options = []
        for i, song in enumerate(songs[:5]):
            name   = song['name']   if is_spotify else song.title
            artist = song.get('artist', '') if is_spotify else song.uploader
            label  = f"{name[:50]}"
            desc   = f"by {artist[:50]}" if artist else "Unknown artist"
            options.append(
                discord.SelectOption(label=label, description=desc, value=str(i), emoji="🎵")
            )

        self.select          = discord.ui.Select(placeholder="🎶 Choose a song to play…", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        selected = int(self.select.values[0])
        await self.music_cog.song_selected_callback(interaction, self.songs[selected], self.is_spotify)


# ──────────────────────────────────────────────
# INTERNAL HELPERS
# ──────────────────────────────────────────────

def _fmt_dur(seconds: int) -> str:
    if seconds <= 0:
        return "0:00"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"
