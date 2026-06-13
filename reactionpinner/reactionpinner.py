import discord
from redbot.core import commands, Config, app_commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import box, pagify
import logging
from typing import Optional, List, Dict

log = logging.getLogger("red.reactionpinner")

class ReactionPinner(commands.Cog):
    """Auto-pins messages based on reaction count (per-channel)."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9876543210, force_registration=True)
        self.config.register_guild(
            enabled=True,
            channels={}  
        )

    async def _get_channel_config(self, channel) -> Dict:
        guild_config = await self.config.guild(channel.guild).all()
        if not guild_config.get("enabled", True):
            return {"enabled": False}

        ch_id = str(channel.id)
        ch_config = guild_config["channels"].get(ch_id, {})
        
        return {
            "enabled": ch_config.get("enabled", True),   # Default to True once configured
            "threshold": ch_config.get("threshold", 5),
            "emojis": ch_config.get("emojis", [])
        }

    def _emoji_matches(self, reaction_emoji, config_emojis: List[str]) -> bool:
        if not config_emojis:
            return True
        return str(reaction_emoji) in config_emojis

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

    @pinreact.group(name="channel", invoke_without_command=True)
    async def channel_group(self, ctx: commands.Context):
        await ctx.send_help()

    @channel_group.command(name="threshold")
    async def ch_threshold(self, ctx: commands.Context, channel: discord.TextChannel, threshold: int):
        if threshold < 1:
            return await ctx.send("❌ Threshold must be at least 1.")
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_id = str(channel.id)
            ch_conf = channels.setdefault(ch_id, {"enabled": True, "emojis": []})
            ch_conf["threshold"] = threshold
        await ctx.send(f"✅ Threshold for {channel.mention} set to **{threshold}**.")

    @channel_group.command(name="emojis")
    async def ch_emojis(self, ctx: commands.Context, channel: discord.TextChannel, action: str = None, *, emoji: str = None):
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
                await ctx.send(f"✅ Emoji filter cleared for {channel.mention}.")
                return

            if not emoji:
                return await ctx.send("❌ Provide emoji after add/remove.")

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
                    await ctx.send("Already in list.")
            elif action == "remove":
                if emoji_str in ch_conf["emojis"]:
                    ch_conf["emojis"].remove(emoji_str)
                    await ctx.send(f"✅ Removed **{emoji_str}**")
                else:
                    await ctx.send("Not in list.")
            else:
                await ctx.send("Usage: add <emoji> | remove <emoji> | clear")

    @channel_group.command(name="toggle")
    async def ch_toggle(self, ctx: commands.Context, channel: discord.TextChannel):
        ch_id = str(channel.id)
        async with self.config.guild(ctx.guild).channels() as channels:
            ch_conf = channels.setdefault(ch_id, {"enabled": True, "threshold": 5, "emojis": []})
            ch_conf["enabled"] = not ch_conf.get("enabled", True)
            status = "enabled" if ch_conf["enabled"] else "disabled"
        await ctx.send(f"✅ {channel.mention} auto-pinning is now **{status}**.")

    @channel_group.command(name="settings")
    async def ch_settings(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        guild_conf = await self.config.guild(ctx.guild).all()
        channels = guild_conf.get("channels", {})
        if not channels:
            return await ctx.send("No channels configured.")

        if channel:
            conf = channels.get(str(channel.id))
            if not conf:
                return await ctx.send(f"{channel.mention} not configured (uses default: enabled + 5).")
            emojis = conf.get("emojis", [])
            msg = f"**{channel.mention}**\nEnabled: {conf.get('enabled', True)}\nThreshold: {conf.get('threshold', 5)}\nEmojis: {', '.join(emojis) if emojis else 'All'}"
            await ctx.send(box(msg))
        else:
            lines = []
            for ch_id, conf in channels.items():
                ch = ctx.guild.get_channel(int(ch_id))
                name = ch.mention if ch else ch_id
                emojis = conf.get("emojis", [])
                lines.append(f"{name} | En:{conf.get('enabled',True)} | Th:{conf.get('threshold',5)} | Em:{emojis or 'All'}")
            for page in pagify("\n".join(lines)):
                await ctx.send(box(page))

    # ====================== DEBUG COMMAND ======================
    @pinreact.command(name="debug")
    async def debug_message(self, ctx: commands.Context, channel: discord.TextChannel, message_id: int):
        """Test reaction count for a message (debug)."""
        try:
            message = await channel.fetch_message(message_id)
            config = await self._get_channel_config(channel)
            count = sum(r.count for r in message.reactions if self._emoji_matches(r.emoji, config["emojis"]))
            await ctx.send(f"Message {message_id} in {channel.mention}:\n"
                          f"Total relevant reactions: **{count}**\n"
                          f"Threshold: {config['threshold']}\n"
                          f"Would pin: {count >= config['threshold']}")
        except Exception as e:
            await ctx.send(f"Error: {e}")

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
            message = await channel.fetch_message(payload.message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
            log.debug(f"Failed to fetch message {payload.message_id}: {e}")
            return
        except Exception as e:
            log.error(f"Unexpected fetch error: {e}")
            return

        if message.pinned or message.author.bot:
            return

        threshold = config["threshold"]
        config_emojis = config.get("emojis", [])

        count = sum(
            r.count for r in message.reactions
            if self._emoji_matches(r.emoji, config_emojis)
        )

        log.debug(f"Message {message.id} in #{channel.name} - Reactions: {count}/{threshold}")

        if count >= threshold:
            try:
                await message.pin(reason=f"Auto-pinned • {count} reactions")
                log.info(f"✅ SUCCESS: Pinned message {message.id} in #{channel.name} ({count} reactions)")
                # Optional: send confirmation in channel (remove if too spammy)
                # await channel.send(f"📌 Message pinned automatically ({count} reactions)", delete_after=10)
            except discord.Forbidden:
                log.warning(f"❌ Missing 'Manage Messages' permission to pin in #{channel.name}")
            except discord.HTTPException as e:
                log.error(f"Pin HTTP error: {e}")
            except Exception as e:
                log.error(f"Unexpected pin error: {e}")
