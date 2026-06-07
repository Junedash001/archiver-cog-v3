import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, inline
import logging
from typing import Optional

log = logging.getLogger("red.reactionpinner")

class ReactionPinner(commands.Cog):
    """Automatically pins messages when they reach a set number of a specific emoji's reactions."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        defaults_guild = {
            "threshold": 5,
            "emoji": None,  # Stored as str (unicode or custom emoji string)
        }
        defaults_channel = {
            "enabled": False,
        }

        self.config.register_guild(**defaults_guild)
        self.config.register_channel(**defaults_channel)

    # ====================== COMMANDS ======================

    @commands.group(name="pinreact", aliases=["reactionpin"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def pinreact(self, ctx: commands.Context):
        """Manage ReactionPinner settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @pinreact.command(name="threshold")
    async def set_threshold(self, ctx: commands.Context, threshold: int):
        """Set the required number of reactions (guild-wide)."""
        if threshold < 1:
            await ctx.send("Threshold must be at least 1.")
            return
        await self.config.guild(ctx.guild).threshold.set(threshold)
        await ctx.send(f"✅ Reaction threshold set to **{threshold}**.")

    @pinreact.command(name="emoji")
    async def set_emoji(self, ctx: commands.Context, emoji: str):
        """Set the emoji to watch for (guild-wide)."""
        # Basic validation
        if not emoji:
            await ctx.send("Please provide an emoji.")
            return
        await self.config.guild(ctx.guild).emoji.set(emoji)
        await ctx.send(f"✅ Now watching for reactions with {emoji}.")

    @pinreact.command(name="toggle")
    async def toggle_channel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Toggle the cog for the current (or specified) channel."""
        channel = channel or ctx.channel
        if not isinstance(channel, discord.TextChannel):
            await ctx.send("Only text channels are supported.")
            return

        enabled = await self.config.channel(channel).enabled()
        await self.config.channel(channel).enabled.set(not enabled)
        status = "enabled" if not enabled else "disabled"
        await ctx.send(f"✅ ReactionPinner is now **{status}** in {channel.mention}.")

    @pinreact.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Show current settings for this guild and channel."""
        guild_settings = await self.config.guild(ctx.guild).all()
        channel_enabled = await self.config.channel(ctx.channel).enabled()

        emoji = guild_settings["emoji"] or "Not set"
        msg = (
            f"**ReactionPinner Settings**\n"
            f"Channel Enabled: {channel_enabled}\n"
            f"Threshold: {guild_settings['threshold']} reactions\n"
            f"Emoji: {emoji}"
        )
        await ctx.send(box(msg))

    # ====================== SLASH COMMANDS ======================

    pinreact_group = app_commands.Group(name="pinreact", description="Manage auto-pinning via reactions")

    @pinreact_group.command(name="threshold")
    @app_commands.describe(threshold="Number of reactions needed")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def slash_threshold(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 1, None]):
        await self.config.guild(interaction.guild).threshold.set(threshold)
        await interaction.response.send_message(f"✅ Threshold set to **{threshold}**.", ephemeral=True)

    @pinreact_group.command(name="emoji")
    @app_commands.describe(emoji="The emoji to count (Unicode or custom)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def slash_emoji(self, interaction: discord.Interaction, emoji: str):
        await self.config.guild(interaction.guild).emoji.set(emoji)
        await interaction.response.send_message(f"✅ Now watching for {emoji}.", ephemeral=True)

    @pinreact_group.command(name="toggle")
    @app_commands.describe(channel="Channel to toggle (current if omitted)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def slash_toggle(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        channel = channel or interaction.channel
        enabled = await self.config.channel(channel).enabled()
        new_state = not enabled
        await self.config.channel(channel).enabled.set(new_state)
        status = "enabled" if new_state else "disabled"
        await interaction.response.send_message(
            f"✅ ReactionPinner is now **{status}** in {channel.mention}.", ephemeral=True
        )

    # ====================== LISTENERS ======================

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel_or_thread(payload.channel_id)
        if not channel or not isinstance(channel, discord.TextChannel):
            return

        # Per-channel check
        if not await self.config.channel(channel).enabled():
            return

        guild_settings = await self.config.guild(guild).all()
        watch_emoji = guild_settings["emoji"]
        if not watch_emoji:
            return  # Not configured

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        if message.pinned or message.author.bot:
            return

        # Count only the watched emoji
        count = 0
        for reaction in message.reactions:
            # Compare emoji (handles unicode and custom emojis)
            if str(reaction.emoji) == watch_emoji:
                count = reaction.count
                break

        threshold = guild_settings["threshold"]
        if count >= threshold:
            try:
                await message.pin(reason=f"Reached {count} {watch_emoji} reactions (threshold: {threshold})")
                log.info(f"Pinned message {message.id} in #{channel.name} ({count} {watch_emoji})")
            except discord.Forbidden:
                log.warning(f"Missing pin permissions in {guild.name}")
            except Exception as e:
                log.error(f"Pin failed: {e}")
