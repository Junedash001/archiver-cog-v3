import re
import discord
from redbot.core import Config, commands

URL_RE = re.compile(r"https?://\S+", re.I)


class RSSGuard(commands.Cog):
    """Delete the bot's own posts whose links contain a blocked word."""

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=7421905531, force_registration=True)
        self.config.register_guild(words=[], channels=[])

    # ---------- commands ----------
    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def rssguard(self, ctx):
        """Manage blocked words in the bot's own link posts."""

    @rssguard.command(name="add")
    async def rssguard_add(self, ctx, *words: str):
        """Add words to block. Example: [p]rssguard add tv-shows"""
        if not words:
            return await ctx.send_help()
        async with self.config.guild(ctx.guild).words() as w:
            for word in words:
                if word.lower() not in w:
                    w.append(word.lower())
        await ctx.send(f"Added: {', '.join(words)}")

    @rssguard.command(name="remove", aliases=["del"])
    async def rssguard_remove(self, ctx, *words: str):
        """Remove blocked words."""
        async with self.config.guild(ctx.guild).words() as w:
            for word in words:
                if word.lower() in w:
                    w.remove(word.lower())
        await ctx.send(f"Removed: {', '.join(words)}")

    @rssguard.command(name="list")
    async def rssguard_list(self, ctx):
        """Show blocked words and the channels being watched."""
        data = await self.config.guild(ctx.guild).all()
        words = ", ".join(data["words"]) or "none"
        chans = ", ".join(f"<#{c}>" for c in data["channels"]) or "all channels"
        await ctx.send(f"Blocked words: {words}\nWatching: {chans}")

    @rssguard.command(name="clear")
    async def rssguard_clear(self, ctx):
        """Remove all blocked words."""
        await self.config.guild(ctx.guild).words.set([])
        await ctx.send("Cleared.")

    @rssguard.group(name="channel")
    async def rssguard_channel(self, ctx):
        """Limit the filter to specific channels (default: all)."""

    @rssguard_channel.command(name="add")
    async def channel_add(self, ctx, channel: discord.TextChannel):
        async with self.config.guild(ctx.guild).channels() as c:
            if channel.id not in c:
                c.append(channel.id)
        await ctx.send(f"Now watching {channel.mention}")

    @rssguard_channel.command(name="remove", aliases=["del"])
    async def channel_remove(self, ctx, channel: discord.TextChannel):
        async with self.config.guild(ctx.guild).channels() as c:
            if channel.id in c:
                c.remove(channel.id)
        await ctx.send(f"Stopped watching {channel.mention}")

    # ---------- filtering ----------
    def _urls(self, m: discord.Message):
        urls = URL_RE.findall(m.content or "")
        for e in m.embeds:
            urls.append(e.url)
            urls += URL_RE.findall(e.description or "")
            for f in e.fields:
                urls += URL_RE.findall(f.value or "")
        return [u.lower() for u in urls if u]

    async def _check(self, m: discord.Message):
        if not m.guild or m.author.id != self.bot.user.id:
            return
        data = await self.config.guild(m.guild).all()
        if not data["words"]:
            return
        if data["channels"] and m.channel.id not in data["channels"]:
            return
        if any(w in u for u in self._urls(m) for w in data["words"]):
            try:
                await m.delete()
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._check(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._check(after)
