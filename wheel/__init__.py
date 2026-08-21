from redbot.core.bot import Red
from .wheel import Wheel

async def setup(bot: Red):
    await bot.add_cog(Wheel(bot))
