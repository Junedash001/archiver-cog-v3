from redbot.core.bot import Red
from .reactionpinner import ReactionPinner

async def setup(bot: Red):
    cog = ReactionPinner(bot)
    await bot.add_cog(cog)
