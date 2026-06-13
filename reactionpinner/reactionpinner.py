import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
import logging
from typing import List, Optional, Dict

log = logging.getLogger("red.reactionpinner")

class ReactionPinner(commands.Cog):
    """Automatically pins messages based on reaction count (per-channel)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)

        self.config.register_guild(
            enabled=True,
            channels={}  # channel_id (str): {"enabled": bool, "threshold": int, "emojis": list[str]}
        )

    async def _get_channel_config(self, channel) -> Dict:
        """Get config for a channel, with proper defaults."""
        guild_config = await self.config.guild(channel.guild).all()
        if not guild_config["enabled"]:
            return {"enabled": False}

        ch_id = str(channel.id)
        ch_config = guild_config["channels"].get(ch_id, {})
        
        return {
            "enabled": ch_config.get("enabled", False),
            "threshold": ch_config.get("threshold", 5),
            "emojis": ch_config.get("emojis", [])
        }

    def _emoji_matches(self, reaction_emoji, config_emojis: List[str]) -> bool:
        if not config_emojis:
            return True  # Count all
        return str(reaction_emoji) in config_emojis

    # ====================== COMMANDS ======================
    @commands.group(name="pinreact", aliases=["reactionpin", "rpin"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_messages=True)
    async def pinreact(self, ctx: commands.Context):
        """Manage ReactionPinner settings."""
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @pinreact.command(name="toggle")
    async def toggle_cog(self, ctx: commands.Context):
        """Toggle the entire cog on/off."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not enabled)
        status = "enabled" if not enabled else "disabled"
        await ctx.send(f"✅ ReactionPinner is now **{status}**.")

    # --- Channel group ---
    @pinreact.group(name="channel")
    async def channel_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @channel_group.command(name="threshold")
    async def ch_threshold(self, ctx: commands.Context, channel: discord.TextChannel, threshold: int):
        """Set threshold for a channel."""
        if threshold < 1:
            return await ctx.send("❌ Threshold must be at least 1.")
        
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_id = str(channel.id)
            channels.setdefault(ch_id, {})["threshold"] = threshold
            channels[ch_id].setdefault("enabled", True)
            channels[ch_id].setdefault("emojis", [])
        
        await ctx.send(f"✅ Threshold for {channel.mention} set to **{threshold}**.")

    @channel_group.command(name="emojis")
    async def ch_emojis(self, ctx: commands.Context, channel: discord.TextChannel, action: str = None, *, emoji: str = None):
        """Manage emojis: `add <emoji>`, `remove <emoji>`, `clear`, or nothing to view."""
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_conf = channels.setdefault(ch_id, {"enabled": True, "threshold": 5, "emojis": []})

            if not action:
                emojis = ch_conf.get("emojis", [])
                text = f"**Emojis for {channel.mention}**\n"
                text += "\n".join(f"• {e}" for e in emojis) if emojis else "• All reactions count"
                return await ctx.send(text)

            action = action.lower()
            if action == "clear":
                ch_conf["emojis"] = []
                await ctx.send(f"✅ Cleared emoji filter for {channel.mention}.")
                return

            if not emoji:
                return await ctx.send("❌ Provide an emoji.")

            # Convert emoji if custom
            try:
                converted = await commands.EmojiConverter().convert(ctx, emoji)
                emoji_str = str(converted)
            except commands.BadArgument:
                emoji_str = emoji.strip()

            if action == "add":
                if emoji_str not in ch_conf["emojis"]:
                    ch_conf["emojis"].append(emoji_str)
                    await ctx.send(f"✅ Added {emoji_str}")
                else:
                    await ctx.send("Already in list.")
            elif action == "remove":
                if emoji_str in ch_conf["emojis"]:
                    ch_conf["emojis"].remove(emoji_str)
                    await ctx.send(f"✅ Removed {emoji_str}")
                else:
                    await ctx.send("Not in list.")
            else:
                await ctx.send("Usage: `add <emoji> | remove <emoji> | clear`")

    @channel_group.command(name="toggle")
    async def ch_toggle(self, ctx: commands.Context, channel: discord.TextChannel):
        """Toggle a specific channel."""
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_conf = channels.setdefault(ch_id, {"enabled": True, "threshold": 5, "emojis": []})
            ch_conf["enabled"] = not ch_conf.get("enabled", True)
            status = "enabled" if ch_conf["enabled"] else "disabled"
        await ctx.send(f"✅ {channel.mention} is now **{status}**.")

    @channel_group.command(name="settings")
    async def ch_settings(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        """Show settings."""
        guild_conf = await self.config.guild(ctx.guild).all()
        channels = guild_conf["channels"]

        if not channels:
            return await ctx.send("No channels configured.")

        if channel:
            ch_id = str(channel.id)
            conf = channels.get(ch_id)
            if not conf:
                return await ctx.send(f"{channel.mention} has no custom settings (disabled by default).")
            emojis = conf.get("emojis", [])
            msg = f"**{channel.mention}**\nEnabled: {conf.get('enabled', False)}\nThreshold: {conf.get('threshold', 5)}\nEmojis: {', '.join(emojis) if emojis else 'All'}"
            await ctx.send(box(msg))
        else:
            out = []
            for ch_id, conf in channels.items():
                ch = ctx.guild.get_channel(int(ch_id))
                name = ch.mention if ch else ch_id
                emojis = conf.get("emojis", [])
                out.append(f"{name} | Enabled: {conf.get('enabled')} | Thresh: {conf.get('threshold')} | Emojis: {emojis or 'All'}")
            for page in pagify("\n".join(out), page_length=1900):
                await ctx.send(box(page))

    # ====================== LISTENERS ======================
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        await self._process_reaction(payload)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        await self._process_reaction(payload)

    async def _process_reaction(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        channel = guild.get_channel_or_thread(payload.channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            return

        config = await self._get_channel_config(channel)
        if not config.get("enabled"):
            return

        try:
            # Small delay to let Discord update reaction count
            await discord.utils.sleep_until(discord.utils.utcnow() + discord.timedelta(milliseconds=800))
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        except Exception as e:
            log.debug(f"Fetch error: {e}")
            return

        if message.pinned or message.author.bot:
            return

        threshold = config["threshold"]
        config_emojis = config["emojis"]

        # Count matching reactions
        if config_emojis:
            count = sum(r.count for r in message.reactions if self._emoji_matches(r.emoji, config_emojis))
        else:
            count = sum(r.count for r in message.reactions)

        if count >= threshold:
            try:
                await message.pin(reason=f"Auto-pinned • {count} reactions")
                log.info(f"Pinned {message.id} in {guild} #{channel.name} ({count} reactions)")
            except discord.Forbidden:
                log.warning(f"Can't pin in {guild} #{channel.name} (missing perms)")
            except Exception as e:
                log.error(f"Pin error: {e}")
