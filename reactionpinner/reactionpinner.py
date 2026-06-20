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
            default_threshold=5,
            default_emojis=[],  
            channels={}         
        )

    async def _get_channel_config(self, channel) -> Dict:
        guild_config = await self.config.guild(channel.guild).all()
        if not guild_config.get("enabled", True):
            return {"enabled": False}

        ch_id = str(channel.id)
        ch_config = guild_config["channels"].get(ch_id, {})

        return {
            "enabled": ch_config.get("enabled", True),
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

    # Global Defaults
    @pinreact.group(name="default")
    async def default_group(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send_help()

    @default_group.command(name="threshold")
    async def default_threshold(self, ctx: commands.Context, threshold: int):
        if threshold < 1:
            return await ctx.send("❌ Threshold must be at least 1.")
        await self.config.guild(ctx.guild).default_threshold.set(threshold)
        await ctx.send(f"✅ Global default threshold set to **{threshold}**.")

    @default_group.command(name="emojis")
    async def default_emojis_cmd(self, ctx: commands.Context, action: str = None, *, emoji: str = None):
        async with self.config.guild(ctx.guild).all() as guild_conf:
            emojis = guild_conf.setdefault("default_emojis", [])

            if not action:
                text = "**Global Default Emojis**\n"
                text += "\n".join(f"• {e}" for e in emojis) if emojis else "• (All reactions counted)"
                return await ctx.send(text)

            action = action.lower()
            if action == "clear":
                guild_conf["default_emojis"] = []
                return await ctx.send("✅ Global emoji filter cleared.")

            if not emoji:
                return await ctx.send("❌ Provide an emoji.")

            try:
                converted = await commands.EmojiConverter().convert(ctx, emoji)
                emoji_str = str(converted)
            except commands.BadArgument:
                emoji_str = emoji.strip()

            if action == "add":
                if emoji_str not in emojis:
                    emojis.append(emoji_str)
                    await ctx.send(f"✅ Added **{emoji_str}** to global defaults.")
                else:
                    await ctx.send("Already added.")
            elif action == "remove":
                if emoji_str in emojis:
                    emojis.remove(emoji_str)
                    await ctx.send(f"✅ Removed **{emoji_str}**.")
                else:
                    await ctx.send("Not in list.")
            else:
                await ctx.send("Usage: `add <emoji> | remove <emoji> | clear`")

    # Per-channel
    @pinreact.group(name="channel", invoke_without_command=True)
    async def channel_group(self, ctx: commands.Context):
        await ctx.send_help()

    @channel_group.command(name="threshold")
    async def ch_threshold(self, ctx: commands.Context, channel: discord.TextChannel, threshold: int):
        if threshold < 1:
            return await ctx.send("❌ Threshold must be at least 1.")
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_id = str(channel.id)
            channels.setdefault(ch_id, {})["threshold"] = threshold
        await ctx.send(f"✅ Threshold for {channel.mention} set to **{threshold}** (override).")

    @channel_group.command(name="emojis")
    async def ch_emojis(self, ctx: commands.Context, channel: discord.TextChannel, action: str = None, *, emoji: str = None):
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_conf = channels.setdefault(ch_id, {"enabled": True})

            if not action:
                emojis = ch_conf.get("emojis")
                if emojis is None:
                    return await ctx.send(f"**{channel.mention}** uses global emoji settings.")
                text = f"**Emojis for {channel.mention}**\n"
                text += "\n".join(f"• {e}" for e in emojis) if emojis else "• (All reactions)"
                return await ctx.send(text)

            action = action.lower()
            if action == "clear":
                ch_conf["emojis"] = []
                return await ctx.send(f"✅ Emoji filter cleared for {channel.mention} (now uses global).")

            if not emoji:
                return await ctx.send("❌ Provide an emoji.")

            try:
                converted = await commands.EmojiConverter().convert(ctx, emoji)
                emoji_str = str(converted)
            except commands.BadArgument:
                emoji_str = emoji.strip()

            if "emojis" not in ch_conf or ch_conf["emojis"] is None:
                ch_conf["emojis"] = []
            if action == "add":
                if emoji_str not in ch_conf["emojis"]:
                    ch_conf["emojis"].append(emoji_str)
                    await ctx.send(f"✅ Added **{emoji_str}**")
                else:
                    await ctx.send("Already added.")
            elif action == "remove":
                if emoji_str in ch_conf["emojis"]:
                    ch_conf["emojis"].remove(emoji_str)
                    await ctx.send(f"✅ Removed **{emoji_str}**")
                else:
                    await ctx.send("Not in list.")
            else:
                await ctx.send("Usage: `add <emoji> | remove <emoji> | clear`")

    @channel_group.command(name="toggle")
    async def ch_toggle(self, ctx: commands.Context, channel: discord.TextChannel):
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_conf = channels.setdefault(ch_id, {})
            ch_conf["enabled"] = not ch_conf.get("enabled", True)
            status = "enabled" if ch_conf["enabled"] else "disabled"
        await ctx.send(f"✅ {channel.mention} is now **{status}**.")

    @channel_group.command(name="remove")
    async def ch_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            if ch_id in channels:
                del channels[ch_id]
                await ctx.send(f"✅ Removed override for {channel.mention} (uses global defaults).")
            else:
                await ctx.send(f"{channel.mention} has no override.")

    @channel_group.command(name="reset")
    async def ch_reset(self, ctx: commands.Context, channel: discord.TextChannel):
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            if ch_id in channels:
                del channels[ch_id]
        await ctx.send(f"✅ {channel.mention} reset to global defaults.")

    @pinreact.command(name="reset")
    async def global_reset(self, ctx: commands.Context):
        await self.config.guild(ctx.guild).clear()
        await ctx.send("✅ All ReactionPinner settings have been reset.")

    @pinreact.command(name="settings")
    async def show_settings(self, ctx: commands.Context):
        guild_conf = await self.config.guild(ctx.guild).all()
        lines = [
            f"**Cog Enabled**: {guild_conf.get('enabled', True)}",
            f"**Pin Bot Messages**: {guild_conf.get('pin_bot_messages', True)}",
            f"**Global Threshold**: {guild_conf.get('default_threshold', 5)}",
            f"**Global Emojis**: {guild_conf.get('default_emojis', []) or 'All reactions'}",
            "\n**Per-channel overrides:**"
        ]
        for ch_id, conf in guild_conf.get("channels", {}).items():
            ch = ctx.guild.get_channel(int(ch_id))
            name = f"#{ch.name}" if ch else f"Unknown ({ch_id})"
            emojis = conf.get("emojis")
            lines.append(f"{name} | En: {conf.get('enabled', True)} | Th: {conf.get('threshold')} | Em: {emojis or 'Global'}")
        for page in pagify("\n".join(lines), page_length=1900):
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
            await discord.utils.sleep_until(discord.utils.utcnow() + timedelta(milliseconds=600))
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        if message.pinned:
            return

        pin_bot = await self.config.guild(guild).pin_bot_messages()
        if message.author.bot and not pin_bot:
            return

        threshold = config["threshold"]
        config_emojis = config["emojis"]

        count = sum(
            r.count for r in message.reactions
            if self._emoji_matches(r.emoji, config_emojis)
        )

        if count >= threshold:
            try:
                await message.pin(reason=f"Auto-pin • {count} reactions")
                log.info(f"Pinned message {message.id} in #{channel.name} ({count} reactions)")
            except discord.Forbidden:
                log.warning(f"Missing pin permissions in #{channel.name}")
            except Exception as e:
                log.error(f"Pin failed: {e}")
