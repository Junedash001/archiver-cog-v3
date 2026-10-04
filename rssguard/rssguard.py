import re
import discord
from redbot.core import commands

BLOCKED = ["tv-shows"]   # lowercase
CHANNEL_IDS = []         # e.g. [123456789012345678]; empty = all channels
URL_RE = re.compile(r"https?://\S+", re.I)


class RSSGuard(commands.Cog):
    """Delete the bot's own RSS posts whose links contain a blocked word."""

    def __init__(self, bot):
        self.bot = bot

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
        if CHANNEL_IDS and m.channel.id not in CHANNEL_IDS:
            return
        if any(w in u for u in self._urls(m) for w in BLOCKED):
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
