from redbot.core.bot import Red
from .reactionpinner import ReactionPinner

async def setup(bot: Red):
    await bot.add_cog(ReactionPinner(bot))
