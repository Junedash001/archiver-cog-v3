import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
import logging
from typing import Optional, List, Dict
from datetime import timedelta

log = logging.getLogger("red.reactionpinner")

class ReactionPinner(commands.Cog):
    """Auto-pins messages based on reaction count (per-channel config)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(
            enabled=True,
            channels={},  
            pin_bot_messages=True   # ← Now enabled by default
        )

    async def _get_channel_config(self, channel) -> Dict:
        guild_config = await self.config.guild(channel.guild).all()
        if not guild_config.get("enabled", True):
            return {"enabled": False}

        ch_config = guild_config["channels"].get(str(channel.id), {})
        return {
            "enabled": ch_config.get("enabled", False),
            "threshold": ch_config.get("threshold", 5),
            "emojis": ch_conf.get("emojis", [])
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
        """Toggle the entire cog on/off."""
        enabled = await self.config.guild(ctx.guild).enabled()
        await self.config.guild(ctx.guild).enabled.set(not enabled)
        status = "enabled" if not enabled else "disabled"
        await ctx.send(f"✅ ReactionPinner is now **{status}**.")

    @pinreact.command(name="botmessages")
    async def toggle_bot_messages(self, ctx: commands.Context):
        """Toggle whether bot messages can be auto-pinned (currently enabled by default)."""
        current = await self.config.guild(ctx.guild).pin_bot_messages()
        await self.config.guild(ctx.guild).pin_bot_messages.set(not current)
        status = "enabled" if not current else "disabled"
        await ctx.send(f"✅ Auto-pinning of **bot messages** is now **{status}**.")

    @pinreact.group(name="channel", invoke_without_command=True)
    async def channel_group(self, ctx: commands.Context):
        """Manage per-channel settings."""
        await ctx.send_help()

    @channel_group.command(name="threshold")
    async def ch_threshold(self, ctx: commands.Context, channel: discord.TextChannel, threshold: int):
        if threshold < 1:
            return await ctx.send("❌ Threshold must be at least 1.")
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_id = str(channel.id)
            channels.setdefault(ch_id, {"enabled": True, "emojis": []})["threshold"] = threshold
        await ctx.send(f"✅ Threshold for {channel.mention} set to **{threshold}**.")

    @channel_group.command(name="emojis")
    async def ch_emojis(self, ctx: commands.Context, channel: discord.TextChannel, action: str = None, *, emoji: str = None):
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_conf = channels.setdefault(ch_id, {"enabled": True, "threshold": 5, "emojis": []})

            if not action:
                emojis = ch_conf.get("emojis", [])
                text = f"**Emojis for {channel.mention}**\n"
                text += "\n".join(f"• {e}" for e in emojis) if emojis else "• (All reactions counted)"
                return await ctx.send(text)

            action = action.lower()
            if action == "clear":
                ch_conf["emojis"] = []
                return await ctx.send(f"✅ Emoji filter cleared for {channel.mention}.")

            if not emoji:
                return await ctx.send("❌ Please provide an emoji.")

            try:
                converted = await commands.EmojiConverter().convert(ctx, emoji)
                emoji_str = str(converted)
            except commands.BadArgument:
                emoji_str = emoji.strip()

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
            ch_conf = channels.setdefault(ch_id, {"enabled": True, "threshold": 5, "emojis": []})
            ch_conf["enabled"] = not ch_conf.get("enabled", True)
            status = "enabled" if ch_conf["enabled"] else "disabled"
        await ctx.send(f"✅ Auto-pinning for {channel.mention} is now **{status}**.")

    @channel_group.command(name="remove")
    async def ch_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            if ch_id in channels:
                del channels[ch_id]
                await ctx.send(f"✅ Removed {channel.mention} from settings.")
            else:
                await ctx.send(f"{channel.mention} was not configured.")

    @channel_group.command(name="settings")
    async def ch_settings(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        guild_conf = await self.config.guild(ctx.guild).all()
        channels = guild_conf.get("channels", {})

        if not channels and not channel:
            bot_pin = await self.config.guild(ctx.guild).pin_bot_messages()
            return await ctx.send(f"No channels configured.\n**Bot messages pinning**: {bot_pin}")

        bot_pin = await self.config.guild(ctx.guild).pin_bot_messages()
        if channel:
            conf = channels.get(str(channel.id))
            if not conf:
                return await ctx.send(f"{channel.mention} uses defaults (disabled).")
            emojis = conf.get("emojis", [])
            msg = (
                f"**{channel.mention}**\n"
                f"Enabled: {conf.get('enabled', False)}\n"
                f"Threshold: {conf.get('threshold', 5)}\n"
                f"Emojis: {', '.join(emojis) if emojis else 'All reactions'}"
            )
            await ctx.send(box(msg))
        else:
            lines = [f"**Bot messages pinning**: {bot_pin}\n"]
            for ch_id, conf in channels.items():
                ch = ctx.guild.get_channel(int(ch_id))
                display_name = f"#{ch.name}" if ch else f"#Unknown ({ch_id})"
                emojis = conf.get("emojis", [])
                lines.append(
                    f"{display_name} | Enabled: {conf.get('enabled', False)} | "
                    f"Threshold: {conf.get('threshold', 5)} | "
                    f"Emojis: {', '.join(emojis) if emojis else 'All'}"
                )
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

        # Bot message support (now enabled by default)
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
