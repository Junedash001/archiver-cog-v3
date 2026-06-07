import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box
import logging

log = logging.getLogger("red.reactionpinner")

class ReactionPinner(commands.Cog):
    """Automatically pins messages that reach a set number of reactions."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)
        defaults = {
            "enabled": True,
            "threshold": 5,  # Total reaction count across all emojis
        }
        self.config.register_guild(**defaults)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            await interaction.response.send_message("You need Manage Messages permissions to use this.", ephemeral=True)

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
        """Set the reaction threshold for auto-pinning (minimum 1)."""
        if threshold < 1:
            await ctx.send("Threshold must be at least 1.")
            return
        await self.config.guild(ctx.guild).threshold.set(threshold)
        await ctx.send(f"✅ Reaction threshold set to **{threshold}**.")

    @pinreact.command(name="toggle")
    async def toggle(self, ctx: commands.Context):
        """Toggle the cog on/off for this server."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not enabled)
        status = "enabled" if not enabled else "disabled"
        await ctx.send(f"✅ ReactionPinner is now **{status}**.")

    @pinreact.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        """Show current settings."""
        settings = await self.config.guild(ctx.guild).all()
        msg = (
            f"**ReactionPinner Settings**\n"
            f"Enabled: {settings['enabled']}\n"
            f"Threshold: {settings['threshold']} reactions"
        )
        await ctx.send(box(msg))

    # Slash version
    pinreact_group = app_commands.Group(name="pinreact", description="Manage auto-pinning via reactions")

    @pinreact_group.command(name="threshold")
    @app_commands.describe(threshold="Number of reactions needed to pin (min 1)")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def slash_threshold(self, interaction: discord.Interaction, threshold: app_commands.Range[int, 1, None]):
        """Set the reaction threshold."""
        await self.config.guild(interaction.guild).threshold.set(threshold)
        await interaction.response.send_message(f"✅ Threshold set to **{threshold}**.", ephemeral=True)

    @pinreact_group.command(name="toggle")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def slash_toggle(self, interaction: discord.Interaction):
        """Toggle the cog."""
        enabled = await self.config.guild(interaction.guild).enabled()
        new_state = not enabled
        await self.config.guild(interaction.guild).enabled.set(new_state)
        status = "enabled" if new_state else "disabled"
        await interaction.response.send_message(f"✅ ReactionPinner is now **{status}**.", ephemeral=True)

    # ====================== LISTENERS ======================

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, added=True)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._handle_reaction(payload, added=False)

    async def _handle_reaction(self, payload: discord.RawReactionActionEvent, added: bool):
        if not payload.guild_id:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        settings = await self.config.guild(guild).all()
        if not settings["enabled"]:
            return

        channel = guild.get_channel_or_thread(payload.channel_id)
        if not channel:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        # Skip if already pinned or bot message (optional tweak)
        if message.pinned or message.author.bot:
            return

        # Calculate total reactions (sum of counts)
        total_reactions = sum(r.count for r in message.reactions)

        threshold = settings["threshold"]
        if total_reactions >= threshold:
            try:
                await message.pin(reason=f"Reached {total_reactions} reactions (threshold: {threshold})")
                log.info(f"Pinned message {message.id} in {guild.name} ({total_reactions} reactions)")
            except discord.Forbidden:
                log.warning(f"Missing permissions to pin in {guild.name}")
            except Exception as e:
                log.error(f"Failed to pin message: {e}")
