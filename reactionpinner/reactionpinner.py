import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
import logging
from typing import List, Optional

log = logging.getLogger("red.reactionpinner")

class ReactionPinner(commands.Cog):
    """Automatically pins messages that reach a set number of reactions (per-channel config)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=1234567890, force_registration=True)

        defaults_guild = {
            "enabled": True,
            "channels": {},  # str(channel_id): {"threshold": int, "emojis": list[str], "enabled": bool}
        }
        self.config.register_guild(**defaults_guild)

    # ====================== HELPER ======================
    async def _get_channel_settings(self, channel) -> dict:
        guild_settings = await self.config.guild(channel.guild).all()
        if not guild_settings["enabled"]:
            return {"enabled": False}

        ch_id = str(channel.id)
        channels = guild_settings["channels"]
        if ch_id in channels:
            return channels[ch_id]
        # Default: disabled unless explicitly configured
        return {"enabled": False, "threshold": 5, "emojis": []}

    def _emoji_matches(self, reaction_emoji: discord.PartialEmoji, config_emojis: List[str]) -> bool:
        """Check if reaction matches any configured emoji."""
        react_str = str(reaction_emoji)
        return react_str in config_emojis

    # ====================== COMMANDS ======================
    @commands.group(name="pinreact", aliases=["reactionpin"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def pinreact(self, ctx: commands.Context):
        """Manage ReactionPinner settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @pinreact.command(name="toggle")
    async def toggle(self, ctx: commands.Context):
        """Toggle the entire cog on/off for this server."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not enabled)
        status = "enabled" if not enabled else "disabled"
        await ctx.send(f"✅ ReactionPinner is now **{status}** for the server.")

    # --- Per-channel commands ---
    @pinreact.group(name="channel")
    async def channel_group(self, ctx: commands.Context):
        """Manage per-channel settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @channel_group.command(name="threshold")
    async def ch_threshold(self, ctx: commands.Context, channel: discord.TextChannel, threshold: int):
        """Set reaction threshold for a specific channel."""
        if threshold < 1:
            return await ctx.send("Threshold must be at least 1.")
        
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_id = str(channel.id)
            if ch_id not in channels:
                channels[ch_id] = {"threshold": threshold, "emojis": [], "enabled": True}
            else:
                channels[ch_id]["threshold"] = threshold
                if "enabled" not in channels[ch_id]:
                    channels[ch_id]["enabled"] = True
        await ctx.send(f"✅ Threshold for {channel.mention} set to **{threshold}**.")

    @channel_group.command(name="emojis")
    async def ch_emojis(self, ctx: commands.Context, channel: discord.TextChannel, *, action: str = None):
        """View or manage emojis for a channel. Use: add <emoji>, remove <emoji>, clear, or no arg to view."""
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            settings = channels.setdefault(ch_id, {"threshold": 5, "emojis": [], "enabled": True})
            
            if not action:
                emojis = settings.get("emojis", [])
                msg = f"**Emojis for {channel.mention}**\n"
                if emojis:
                    msg += "\n".join(f"• {e}" for e in emojis)
                else:
                    msg += "All reactions count (no filter)."
                return await ctx.send(msg)

            parts = action.strip().split(maxsplit=1)
            cmd = parts[0].lower()
            emoji_str = parts[1] if len(parts) > 1 else None

            if cmd == "add" and emoji_str:
                # Validate emoji
                try:
                    emoji = await commands.EmojiConverter().convert(ctx, emoji_str)
                    emoji_str = str(emoji)
                except commands.BadArgument:
                    pass  # unicode or raw
                if emoji_str not in settings["emojis"]:
                    settings["emojis"].append(emoji_str)
                    await ctx.send(f"✅ Added {emoji_str} to {channel.mention}")
                else:
                    await ctx.send("Emoji already in list.")
            elif cmd == "remove" and emoji_str:
                try:
                    emoji = await commands.EmojiConverter().convert(ctx, emoji_str)
                    emoji_str = str(emoji)
                except:
                    pass
                if emoji_str in settings["emojis"]:
                    settings["emojis"].remove(emoji_str)
                    await ctx.send(f"✅ Removed {emoji_str}")
                else:
                    await ctx.send("Emoji not in list.")
            elif cmd == "clear":
                settings["emojis"] = []
                await ctx.send(f"✅ Cleared emoji filter for {channel.mention} (now counts all reactions).")
            else:
                await ctx.send("Usage: `add <emoji>`, `remove <emoji>`, or `clear`")

    @channel_group.command(name="toggle")
    async def ch_toggle(self, ctx: commands.Context, channel: discord.TextChannel):
        """Toggle auto-pinning for a specific channel."""
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            settings = channels.setdefault(ch_id, {"threshold": 5, "emojis": [], "enabled": True})
            settings["enabled"] = not settings.get("enabled", True)
            status = "enabled" if settings["enabled"] else "disabled"
        await ctx.send(f"✅ Auto-pinning for {channel.mention} is now **{status}**.")

    @channel_group.command(name="settings")
    async def ch_settings(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Show settings for a channel (or all configured channels)."""
        guild_settings = await self.config.guild(ctx.guild).all()
        channels = guild_settings["channels"]
        
        if not channels:
            return await ctx.send("No channels configured yet.")

        if channel:
            ch_id = str(channel.id)
            if ch_id not in channels:
                return await ctx.send(f"No specific settings for {channel.mention}. Uses global behavior (disabled).")
            settings = channels[ch_id]
            emojis = settings.get("emojis", [])
            msg = (
                f"**{channel.mention}**\n"
                f"Enabled: {settings.get('enabled', False)}\n"
                f"Threshold: {settings.get('threshold', 5)}\n"
                f"Emojis: {', '.join(emojis) if emojis else 'All reactions'}"
            )
            await ctx.send(box(msg))
        else:
            # All channels
            pages = []
            for ch_id, settings in channels.items():
                ch = ctx.guild.get_channel(int(ch_id))
                name = ch.mention if ch else f"Unknown ({ch_id})"
                emojis = settings.get("emojis", [])
                page = (
                    f"{name}\n"
                    f"Enabled: {settings.get('enabled', False)}\n"
                    f"Threshold: {settings.get('threshold', 5)}\n"
                    f"Emojis: {', '.join(emojis) if emojis else 'All'}"
                )
                pages.append(page)
            for page in pagify("\n\n".join(pages), page_length=1800):
                await ctx.send(box(page))

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
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        settings = await self._get_channel_settings(channel)
        if not settings.get("enabled", False):
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return

        if message.pinned or message.author.bot:
            return

        threshold = settings.get("threshold", 5)
        config_emojis = settings.get("emojis", [])

        # Count relevant reactions
        if config_emojis:
            count = sum(
                r.count for r in message.reactions
                if self._emoji_matches(r.emoji, config_emojis)
            )
        else:
            count = sum(r.count for r in message.reactions)

        if count >= threshold:
            try:
                await message.pin(
                    reason=f"Reached {count} reactions (threshold: {threshold}) in #{channel.name}"
                )
                log.info(f"Pinned message {message.id} in {guild.name} #{channel.name}")
            except discord.Forbidden:
                log.warning(f"Missing pin permissions in {guild.name} #{channel.name}")
            except Exception as e:
                log.error(f"Pin failed: {e}")
