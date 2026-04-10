import discord
from config import Config


class Colors:
    CREAM_WHITE = 0xFFFEF9
    SOFT_WHITE = 0xF0F0F0
    LIGHT_BLUE = 0xADD8E6
    PASTEL_PINK = 0xFFB6C1
    MINT = 0x98FB98
    LAVENDER = 0xE6E6FA
    PEACH = 0xFFDAB9
    ACCENT_BLUE = 0x5865F2
    ACCENT_GREEN = 0x57F287
    ACCENT_RED = 0xED4245


class ControlPanelView(discord.ui.View):
    """Single permanent control panel with all buttons."""
    def __init__(self, music_cog, guild_state, page=0, timeout=None):
        super().__init__(timeout=timeout)
        self.music_cog = music_cog
        self.guild_state = guild_state
        self.page = page
        self.per_page = 8

    # Row 0 — playback controls
    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.primary, custom_id="cp_pause", row=0)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.pause_callback(interaction)
        await self._refresh_panel(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.primary, custom_id="cp_skip", row=0)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.skip_callback(interaction)

    @discord.ui.button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="cp_stop", row=0)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.stop_callback(interaction)
        await self._refresh_panel(interaction)

    @discord.ui.button(emoji="🔉", style=discord.ButtonStyle.secondary, custom_id="cp_vol_down", row=0)
    async def vol_down_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.volume_down_callback(interaction)

    @discord.ui.button(emoji="🔊", style=discord.ButtonStyle.secondary, custom_id="cp_vol_up", row=0)
    async def vol_up_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.volume_up_callback(interaction)

    # Row 1 — queue controls
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary, custom_id="cp_prev", row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
        embed = create_panel_embed(self.guild_state, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary, custom_id="cp_next", row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, (len(self.guild_state.queue) - 1) // self.per_page)
        if self.page < max_page:
            self.page += 1
        embed = create_panel_embed(self.guild_state, self.page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="🔀", label="Shuffle", style=discord.ButtonStyle.primary, custom_id="cp_shuffle", row=1)
    async def shuffle_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.shuffle_callback(interaction)
        await self._refresh_panel(interaction)

    @discord.ui.button(emoji="🗑️", label="Clear", style=discord.ButtonStyle.danger, custom_id="cp_clear", row=1)
    async def clear_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.music_cog.clear_callback(interaction)
        await self._refresh_panel(interaction)

    async def _refresh_panel(self, interaction: discord.Interaction):
        """Edit the panel message in-place after an action that already responded."""
        guild_state = self.guild_state
        embed = create_panel_embed(guild_state, self.page)
        try:
            # If the interaction was already responded to, use followup edit
            msg = interaction.message
            if msg:
                await msg.edit(embed=embed, view=self)
        except Exception:
            pass

    def update_pause_button(self, is_paused):
        for child in self.children:
            if getattr(child, 'custom_id', None) == "cp_pause":
                child.emoji = "▶️" if is_paused else "⏸️"


# Keep old NowPlayingView as alias so bot.py doesn't break
NowPlayingView = ControlPanelView


class QueueView(discord.ui.View):
    def __init__(self, music_cog, guild_state, page=0):
        super().__init__(timeout=60)
        self.music_cog = music_cog
        self.guild_state = guild_state
        self.page = page
        self.per_page = 10

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
        self.music_cog = music_cog
        self.current_votes = current_votes
        self.threshold = threshold

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
        self.music_cog = music_cog
        self.songs = songs
        self.is_spotify = is_spotify

        options = []
        for i, song in enumerate(songs[:5]):
            name = song['name'] if is_spotify else song.title
            artist = song.get('artist', '') if is_spotify else song.uploader
            label = f"{name[:50]}"
            description = f"by {artist[:50]}" if artist else "Unknown artist"
            options.append(
                discord.SelectOption(label=label, description=description, value=str(i), emoji="🎵")
            )

        self.select = discord.ui.Select(placeholder="🎶 Choose a song to play...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        selected = int(self.select.values[0])
        await self.music_cog.song_selected_callback(interaction, self.songs[selected], self.is_spotify)


# ──────────────────────────────────────────────
# UNIFIED PANEL EMBED
# ──────────────────────────────────────────────

def create_panel_embed(guild_state, page=0, per_page=8):
    """Single embed: now playing info + queue list below."""
    embed = discord.Embed(color=Colors.ACCENT_BLUE)

    # ── Now Playing section ──
    if guild_state.current_song:
        song = guild_state.current_song
        status = "⏸️ Paused" if guild_state.is_paused else "▶️ Now Playing"
        title = song.title[:90] + "..." if len(song.title) > 90 else song.title
        embed.title = f"{status} — {title}"

        info = []
        if song.uploader:
            info.append(f"🎤 **{song.uploader}**")
        if song.duration:
            info.append(f"⏱️ `{song.format_duration()}`")
        if song.requester:
            info.append(f"👤 {song.requester.mention}")
        embed.description = "  ".join(info) if info else ""

        if song.thumbnail:
            embed.set_thumbnail(url=song.thumbnail)
    else:
        embed.title = "🎵 Music Panel"
        embed.description = "*Nothing playing. Use `/play` to start!*"

    # ── Queue section ──
    if guild_state.queue:
        start = page * per_page
        end = start + per_page
        lines = []
        for i, s in enumerate(guild_state.queue[start:end], start=start + 1):
            dur = s.format_duration() if s.duration else "?:??"
            t = s.title[:55] + "…" if len(s.title) > 55 else s.title
            lines.append(f"`{i}.` {t}  `{dur}`")

        total = len(guild_state.queue)
        total_pages = max(1, (total - 1) // per_page + 1)
        footer_extra = f"  •  page {page + 1}/{total_pages}" if total_pages > 1 else ""

        embed.add_field(
            name=f"📋 Up Next ({total} songs{footer_extra})",
            value="\n".join(lines),
            inline=False
        )

        if total > end:
            embed.set_footer(text=f"…and {total - end} more  •  use ◀️▶️ to browse")
    else:
        if guild_state.current_song:
            embed.set_footer(text="Queue is empty")

    return embed


# ──────────────────────────────────────────────
# Legacy helpers (keep bot.py working unchanged)
# ──────────────────────────────────────────────

def create_now_playing_embed(song, guild_state):
    return create_panel_embed(guild_state)


def create_queue_embed(guild_state, page=0, per_page=10):
    return create_panel_embed(guild_state, page, per_page=per_page)


def create_added_embed(song, position=None):
    embed = discord.Embed(title="✅ Added to Queue", color=Colors.MINT)
    song_title = song.title[:150] + "..." if len(song.title) > 150 else song.title
    embed.description = f"**{song_title}**"
    info_parts = []
    if song.uploader:
        info_parts.append(f"🎤 {song.uploader}")
    if song.duration:
        info_parts.append(f"⏱️ {song.format_duration()}")
    if position:
        info_parts.append(f"📍 Position #{position}")
    if info_parts:
        embed.add_field(name="Info", value=" • ".join(info_parts), inline=False)
    if song.thumbnail:
        embed.set_thumbnail(url=song.thumbnail)
    return embed


def create_error_embed(title, message):
    return discord.Embed(title=f"❌ {title}", description=message, color=Colors.ACCENT_RED)


def create_success_embed(title, message):
    return discord.Embed(title=f"✅ {title}", description=message, color=Colors.ACCENT_GREEN)


def create_info_embed(title, message):
    return discord.Embed(title=f"ℹ️ {title}", description=message, color=Colors.ACCENT_BLUE)