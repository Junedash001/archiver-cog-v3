from redbot.core.bot import Red

from .france24whitelist import France24Whitelist


async def setup(bot: Red) -> None:
    await bot.add_cog(France24Whitelist(bot))
