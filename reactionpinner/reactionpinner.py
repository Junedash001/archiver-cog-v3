import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
import logging
from typing import Optional, List, Dict
from datetime import timedelta

log = logging.getLogger("red.reactionpinner")

class ReactionPinner(commands.Cog):
    """Auto-pins messages based on reaction count with global + per-channel config."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(
            enabled=True,
            pin_bot_messages=True,
            # Global defaults
            default_threshold=5,
            default_emojis=[],          # Empty = count all reactions
            channels={}                 # Per-channel overrides
        )

    async def _get_channel_config(self, channel) -> Dict:
        guild_config = await self.config.guild(channel.guild).all()
        if not guild_config.get("enabled", True):
            return {"enabled": False}

        ch_id = str(channel.id)
        ch_config = guild_config["channels"].get(ch_id, {})

        # Use per-channel if exists, otherwise global defaults
        return {
            "enabled": ch_config.get("enabled", True),  # default True when using global
            "threshold": ch_config.get("threshold", guild_config["default_threshold"]),
            "emojis": ch_config.get("emojis", guild_config["default_emojis"])
        }

    def _emoji_matches(self, reaction_emoji, config_emojis: List[str]) -> bool:
        return not config_emojis or str(reaction_emoji) in config_emojis

    # ====================== COMMANDS ======================
    @commands.group(name="pinreact", aliases=["reactionpin", "rpin"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def pinreact(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @pinreact.command(name="toggle")
    async def toggle_cog(self, ctx: commands.Context):
        enabled = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not enabled)
        status = "enabled" if not enabled else "disabled"
        await ctx.send(f"✅ ReactionPinner is now **{status}**.")

    @pinreact.command(name="botmessages")
    async def toggle_bot_messages(self, ctx: commands.Context):
        current = await self.config.guild(ctx.guild).pin_bot_messages()
        await self.config.guild(ctx.guild).pin_bot_messages.set(not current)
        status = "enabled" if not current else "disabled"
        await ctx.send(f"✅ Bot message pinning is now **{status}**.")

    # === Global Defaults ===
    @pinreact.group(name="default")
    async def default_group(self, ctx: commands.Context):
        """Manage global default settings (apply to all channels without overrides)."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @default_group.command(name="threshold")
    async def default_threshold(self, ctx: commands.Context, threshold: int):
        """Set default threshold for all channels."""
        if threshold < 1:
            return await ctx.send("❌ Threshold must be at least 1.")
        await self.config.guild(ctx.guild).default_threshold.set(threshold)
        await ctx.send(f"✅ Global default threshold set to **{threshold}**.")

    @default_group.command(name="emojis")
    async def default_emojis
