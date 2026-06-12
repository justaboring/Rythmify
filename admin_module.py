import discord
from config import Config
from music_player import get_guild_state


def is_dj(user: discord.Member):
    """Check if user has DJ role"""
    dj_role = discord.utils.get(user.guild.roles, name=Config.DJ_ROLE_NAME)
    if dj_role and dj_role in user.roles:
        return True

    if user.guild_permissions.administrator:
        return True

    return False


def can_skip(user: discord.Member, guild_state):
    """Check if user can skip (DJ or voted enough)"""
    if is_dj(user):
        return True, "DJ skip"

    if user.id in guild_state.skip_votes:
        return False, "You already voted"

    voice_channel = user.voice.channel if user.voice else None
    if not voice_channel:
        return False, "You must be in a voice channel"

    member_count = len([m for m in voice_channel.members if not m.bot])
    threshold = max(1, int(member_count * Config.SKIP_VOTE_THRESHOLD / 100))
    current_votes = len(guild_state.skip_votes) + 1

    if current_votes >= threshold:
        return True, f"Vote passed ({current_votes}/{threshold})"

    return False, f"Vote counted ({current_votes}/{threshold} needed)"


class SkipVoteManager:
    @staticmethod
    def add_vote(user_id, guild_state):
        if user_id in guild_state.skip_votes:
            return False, "You already voted to skip"
        guild_state.skip_votes.add(user_id)
        return True, "Vote added"

    @staticmethod
    def clear_votes(guild_state):
        guild_state.skip_votes.clear()

    @staticmethod
    def get_vote_count(guild_state):
        return len(guild_state.skip_votes)

    @staticmethod
    def get_threshold(voice_channel):
        if not voice_channel:
            return 1
        member_count = len([m for m in voice_channel.members if not m.bot])
        return max(1, int(member_count * Config.SKIP_VOTE_THRESHOLD / 100))


def remove_from_queue(guild_state, index):
    return guild_state.remove_from_queue(index)


def move_in_queue(guild_state, from_idx, to_idx):
    return guild_state.move_in_queue(from_idx, to_idx)


def shuffle_queue(guild_state):
    guild_state.shuffle()


def clear_queue(guild_state):
    guild_state.clear()
