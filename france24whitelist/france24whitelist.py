"""France24Whitelist - keep only regular France 24 news articles in your channels."""
import logging
import re
from collections import deque
from typing import List, Optional, Union

import discord
from redbot.core import Config, commands
from redbot.core.bot import Red
from redbot.core.utils.chat_formatting import humanize_list, inline

from .matching import (
    ALLOW,
    BLOCK,
    DEFAULT_PATTERN,
    IGNORE,
    classify,
    compile_pattern,
    find_urls,
    france24_path,
)

log = logging.getLogger("red.france24whitelist")

WatchableChannel = Union[discord.TextChannel, discord.ForumChannel]


def collect_urls(message: discord.Message) -> List[str]:
    """Every URL in the message text and in its embeds (RSS bots usually use embeds)."""
    urls: List[str] = []
    texts = [message.content]
    for embed in message.embeds:
        if embed.url:
            urls.append(embed.url)
        author_url = getattr(embed.author, "url", None)
        if author_url:
            urls.append(author_url)
        texts.append(embed.description)
        texts.extend(field.value for field in embed.fields)
    for text in texts:
        urls.extend(find_urls(text))
    return list(dict.fromkeys(urls))  # de-duplicate, keep order


class France24Whitelist(commands.Cog):
    """Delete France 24 links that are not regular news articles.

    Only messages that contain a France 24 link are ever looked at. Links to any
    other website, and ordinary messages, are never touched.
    """

    __version__ = "1.0.0"
    __author__ = "YOUR_GITHUB_USERNAME"

    def __init__(self, bot: Red) -> None:
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=2406202601, force_registration=True
        )
        self.config.register_guild(
            enabled=False,
            channels=[],  # empty = every channel
            pattern=DEFAULT_PATTERN,
            dryrun=False,
            exempt_mods=True,
            log_channel=None,
        )
        self._recent = deque(maxlen=500)  # message IDs already handled

    def format_help_for_context(self, ctx: commands.Context) -> str:
        pre_processed = super().format_help_for_context(ctx)
        return f"{pre_processed}\n\nCog version: {self.__version__}"

    async def red_delete_data_for_user(self, **kwargs) -> None:
        """This cog stores no user data."""
        return

    # ------------------------------------------------------------------ #
    # Listeners
    # ------------------------------------------------------------------ #

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        await self._handle(message)

    @commands.Cog.listener()
    async def on_message_edit(
        self, _before: discord.Message, after: discord.Message
    ) -> None:
        await self._handle(after)

    async def _handle(self, message: discord.Message) -> None:
        guild = message.guild
        if guild is None or self.bot.user is None:
            return
        if message.author.id == self.bot.user.id:
            return

        # Cheap pre-check: ignore everything that has no France 24 link at all.
        urls = collect_urls(message)
        if not any(france24_path(url) is not None for url in urls):
            return

        if await self.bot.cog_disabled_in_guild(self, guild):
            return
        settings = await self.config.guild(guild).all()
        if not settings["enabled"]:
            return
        if not self._in_scope(message, settings["channels"]):
            return
        if settings["exempt_mods"] and await self._is_exempt(message.author):
            return

        try:
            pattern = compile_pattern(settings["pattern"])
        except re.error:
            log.error("Invalid whitelist pattern in guild %s; ignoring message.", guild.id)
            return

        blocked = [url for url in urls if classify(url, pattern) == BLOCK]
        if blocked:
            await self._block(message, blocked, settings)

    @staticmethod
    def _in_scope(message: discord.Message, watched: List[int]) -> bool:
        if not watched:
            return True
        ids = {message.channel.id}
        parent_id = getattr(message.channel, "parent_id", None)  # threads
        if parent_id:
            ids.add(parent_id)
        return bool(ids.intersection(watched))

    async def _is_exempt(self, author: Union[discord.Member, discord.User]) -> bool:
        """Human moderators/admins/owners may post anything. Bots and webhooks never are."""
        if not isinstance(author, discord.Member) or author.bot:
            return False
        return await self.bot.is_owner(author) or await self.bot.is_mod(author)

    async def _block(
        self, message: discord.Message, blocked: List[str], settings: dict
    ) -> None:
        guild = message.guild
        if message.id in self._recent:
            return
        self._recent.append(message.id)

        if settings["dryrun"]:
            status = "dry run - message left in place"
        elif not message.channel.permissions_for(guild.me).manage_messages:
            status = "NOT deleted - I need the Manage Messages permission there"
        else:
            try:
                await message.delete()
                status = "message deleted"
            except discord.NotFound:
                status = "message was already deleted"
            except discord.HTTPException as exc:  # includes Forbidden
                status = f"NOT deleted - Discord returned an error ({exc.status})"

        log.info("France24Whitelist [%s #%s]: %s", guild.id, message.channel.id, status)
        await self._send_log(message, blocked, status, settings["log_channel"])

    async def _send_log(
        self,
        message: discord.Message,
        blocked: List[str],
        status: str,
        log_channel_id: Optional[int],
    ) -> None:
        if not log_channel_id:
            return
        guild = message.guild
        channel = guild.get_channel(log_channel_id)
        if not isinstance(channel, discord.TextChannel):
            return
        if not channel.permissions_for(guild.me).send_messages:
            return
        author = discord.utils.escape_markdown(str(message.author))
        links = "\n".join(f"<{url[:200]}>" for url in blocked[:5])
        text = (
            f"**France 24 whitelist** - {status}\n"
            f"Author: {author} ({message.author.id}) in {message.channel.mention}\n"
            f"{links}"
        )
        try:
            await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------ #
    # Commands
    # ------------------------------------------------------------------ #

    @commands.group(name="france24whitelist", aliases=["f24wl"])
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def f24wl(self, ctx: commands.Context) -> None:
        """Only allow regular France 24 news articles."""

    @f24wl.command(name="enable")
    async def f24wl_enable(self, ctx: commands.Context) -> None:
        """Turn the whitelist on for this server."""
        await self.config.guild(ctx.guild).enabled.set(True)
        msg = "France 24 whitelist enabled."
        if not ctx.guild.me.guild_permissions.manage_messages:
            msg += (
                "\nNote: I don't have Manage Messages server-wide. "
                "I need it in every watched channel to delete anything."
            )
        await ctx.send(msg)

    @f24wl.command(name="disable")
    async def f24wl_disable(self, ctx: commands.Context) -> None:
        """Turn the whitelist off for this server."""
        await self.config.guild(ctx.guild).enabled.set(False)
        await ctx.send("France 24 whitelist disabled.")

    @f24wl.command(name="dryrun")
    async def f24wl_dryrun(self, ctx: commands.Context, on_off: bool) -> None:
        """Log what would be deleted without deleting anything (true/false)."""
        await self.config.guild(ctx.guild).dryrun.set(on_off)
        await ctx.send(f"Dry run is now {'on' if on_off else 'off'}.")

    @f24wl.command(name="exemptmods")
    async def f24wl_exemptmods(self, ctx: commands.Context, on_off: bool) -> None:
        """Let human mods/admins post any France 24 link (default: true).

        Bots and webhooks are never exempt.
        """
        await self.config.guild(ctx.guild).exempt_mods.set(on_off)
        await ctx.send(f"Moderator exemption is now {'on' if on_off else 'off'}.")

    @f24wl.command(name="logchannel")
    async def f24wl_logchannel(
        self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Set the channel where blocked links are logged. Leave empty to turn logging off."""
        await self.config.guild(ctx.guild).log_channel.set(channel.id if channel else None)
        if channel:
            await ctx.send(f"Blocked links will be logged in {channel.mention}.")
        else:
            await ctx.send("Logging turned off.")

    @f24wl.group(name="channels", aliases=["watch"])
    async def f24wl_channels(self, ctx: commands.Context) -> None:
        """Limit which channels are checked. With none set, every channel is checked."""

    @f24wl_channels.command(name="add")
    async def f24wl_channels_add(
        self, ctx: commands.Context, *channels: WatchableChannel
    ) -> None:
        """Check these channels (text or forum channels; threads follow their parent)."""
        if not channels:
            await ctx.send_help()
            return
        async with self.config.guild(ctx.guild).channels() as stored:
            for channel in channels:
                if channel.id not in stored:
                    stored.append(channel.id)
        await ctx.send(f"Now checking: {humanize_list([c.mention for c in channels])}.")

    @f24wl_channels.command(name="remove")
    async def f24wl_channels_remove(
        self, ctx: commands.Context, *channels: WatchableChannel
    ) -> None:
        """Stop checking these channels."""
        if not channels:
            await ctx.send_help()
            return
        async with self.config.guild(ctx.guild).channels() as stored:
            for channel in channels:
                if channel.id in stored:
                    stored.remove(channel.id)
        await ctx.send(f"No longer checking: {humanize_list([c.mention for c in channels])}.")

    @f24wl_channels.command(name="clear")
    async def f24wl_channels_clear(self, ctx: commands.Context) -> None:
        """Check every channel again."""
        await self.config.guild(ctx.guild).channels.set([])
        await ctx.send("Channel list cleared - every channel is checked.")

    @f24wl_channels.command(name="list")
    async def f24wl_channels_list(self, ctx: commands.Context) -> None:
        """Show the checked channels."""
        stored = await self.config.guild(ctx.guild).channels()
        if not stored:
            await ctx.send("Every channel is checked.")
            return
        await ctx.send(
            f"Checked channels: {humanize_list([f'<#{c}>' for c in stored])}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @f24wl.group(name="pattern", invoke_without_command=True)
    async def f24wl_pattern(
        self, ctx: commands.Context, *, regex: Optional[str] = None
    ) -> None:
        """Show or set the regex an allowed France 24 URL path must match.

        The regex is matched (case-insensitively) against the URL *path* only,
        e.g. `/en/europe/20261004-some-headline`. Use `[p]f24wl pattern reset` to restore
        the default.
        """
        if regex is None:
            current = await self.config.guild(ctx.guild).pattern()
            await ctx.send(f"Current pattern: {inline(current)}")
            return
        regex = regex.strip().strip("`")
        try:
            compile_pattern(regex)
        except re.error as exc:
            await ctx.send(f"That is not a valid regex: {inline(str(exc))}")
            return
        await self.config.guild(ctx.guild).pattern.set(regex)
        await ctx.send(f"Pattern set to {inline(regex)}")

    @f24wl_pattern.command(name="reset")
    async def f24wl_pattern_reset(self, ctx: commands.Context) -> None:
        """Restore the default pattern."""
        await self.config.guild(ctx.guild).pattern.set(DEFAULT_PATTERN)
        await ctx.send(f"Pattern reset to {inline(DEFAULT_PATTERN)}")

    @f24wl.command(name="test")
    async def f24wl_test(self, ctx: commands.Context, *, url: str) -> None:
        """Check what the whitelist would do with a link (works even when disabled)."""
        urls = find_urls(url)
        if not urls:
            await ctx.send("I couldn't find a link in that.")
            return
        pattern = compile_pattern(await self.config.guild(ctx.guild).pattern())
        result = classify(urls[0], pattern)
        text = {
            IGNORE: "Not a France 24 link - it would be left alone.",
            ALLOW: "Allowed - matches the whitelist.",
            BLOCK: "Blocked - the message would be deleted.",
        }[result]
        await ctx.send(text)

    @f24wl.command(name="settings")
    async def f24wl_settings(self, ctx: commands.Context) -> None:
        """Show the current settings."""
        s = await self.config.guild(ctx.guild).all()
        channels = (
            humanize_list([f"<#{c}>" for c in s["channels"]]) if s["channels"] else "all channels"
        )
        log_channel = f"<#{s['log_channel']}>" if s["log_channel"] else "off"
        lines = [
            f"Enabled: {s['enabled']}",
            f"Dry run: {s['dryrun']}",
            f"Exempt moderators: {s['exempt_mods']}",
            f"Checked channels: {channels}",
            f"Log channel: {log_channel}",
            f"Pattern: {inline(s['pattern'])}",
        ]
        await ctx.send("\n".join(lines), allowed_mentions=discord.AllowedMentions.none())
