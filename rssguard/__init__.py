from .rssguard import RSSGuard

async def setup(bot):
    await bot.add_cog(RSSGuard(bot))
