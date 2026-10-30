from redbot.core.bot import Red

from .linkfixer import LinkFixer


async def setup(bot: Red) -> None:
    await bot.add_cog(LinkFixer(bot))
