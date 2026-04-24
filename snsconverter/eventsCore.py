from discord import Message

from .constants import KEY_ENABLED, SocialMedia
from .core import Core
from .helpers import convert_to_ddinsta_url, convert_to_vx_twitter_url, urls_to_string, valid


class EventsCore(Core):
    async def _on_message_insta_replacer(self, message: Message):
        if not await self.config.guild(message.guild).get_attr(KEY_ENABLED)():
            self.logger.debug(
                "SNSConverter disabled for guild %s (%s), skipping",
                message.guild.name,
                message.guild.id,
            )
            return
        
        # Skip bot messages
        if message.author.bot:
            return
        
        # Check message content directly for Instagram URLs
        if not re.search(INSTA_REGEX_PATTERN, message.content):
            return
        
        # Extract and convert Instagram URLs from message content
        insta_urls = re.findall(r"https?://(?:www\.)?instagram\.com/\S+", message.content)
        
        if not insta_urls:
            return
        
        # Convert to vxinstagram
        vxinsta_urls = [
            re.sub(r"https://(?:www\.)?instagram\.com", "https://vxinstagram.com", url)
            for url in insta_urls
        ]
        
        # Reply with converted URLs
        ok = await message.reply(urls_to_string(vxinsta_urls, SocialMedia.INSTAGRAM))
        
        # Suppress embeds if successful
        if ok:
            await message.edit(suppress=True)

    async def _on_edit_insta_replacer(self, message_before: Message, message_after: Message):
        if message_after.author.bot:
            return
        
        if not await self.config.guild(message_after.guild).get_attr(KEY_ENABLED)():
            self.logger.debug(
                "SNSConverter disabled for guild %s (%s), skipping",
                message_after.guild.name,
                message_after.guild.id,
            )
            return
        
        # Check if new Instagram URLs were added
        old_urls = set(re.findall(r"https?://(?:www\.)?instagram\.com/\S+", message_before.content))
        new_urls = set(re.findall(r"https?://(?:www\.)?instagram\.com/\S+", message_after.content))
        
        added_urls = new_urls - old_urls
        
        if not added_urls:
            return
        
        # Convert to vxinstagram
        vxinsta_urls = [
            re.sub(r"https://(?:www\.)?instagram\.com", "https://vxinstagram.com", url)
            for url in added_urls
        ]
        
        # Reply with converted URLs
        ok = await message_after.reply(urls_to_string(vxinsta_urls, SocialMedia.INSTAGRAM))
        
        # Suppress embeds if successful
        if ok:
            await message_after.edit(suppress=True)
            
    async def _on_message_twit_replacer(self, message: Message):
        if not valid(message):
            return

        if not await self.config.guild(message.guild).get_attr(KEY_ENABLED)():
            self.logger.debug(
                "SNSConverter disabled for guild %s (%s), skipping",
                message.guild.name,
                message.guild.id,
            )
            return

        # the actual code part
        vx_twtter_urls = convert_to_vx_twitter_url(message.embeds)

        # no changed urls detected
        if not vx_twtter_urls:
            return

        # constructs the message and replies with a mention
        ok = await message.reply(urls_to_string(vx_twtter_urls, SocialMedia.TWITTER))

        # Remove embeds from user message if reply is successful
        if ok:
            await message.edit(suppress=True)

    async def _on_edit_twit_replacer(self, message_before: Message, message_after: Message):
        # skips if the message is sent by any bot
        if not valid(message_after):
            return

        if not await self.config.guild(message_after.guild).get_attr(KEY_ENABLED)():
            self.logger.debug(
                "SNSConverter disabled for guild %s (%s), skipping",
                message_after.guild.name,
                message_after.guild.id,
            )
            return

        video_embed_before = [embed for embed in message_before.embeds if embed.video]
        video_embed_after = [embed for embed in message_after.embeds if embed.video]
        new_video_embeds = [
            embed for embed in video_embed_after if embed not in video_embed_before
        ]

        # skips if the message has no new embeds
        if not new_video_embeds:
            return

        vx_twtter_urls = convert_to_vx_twitter_url(new_video_embeds)

        # no changed urls detected
        if not vx_twtter_urls:
            return

        # constructs the message and replies with a mention
        ok = await message_after.reply(urls_to_string(vx_twtter_urls, SocialMedia.TWITTER))

        # Remove embeds from user message if reply is successful
        if ok:
            await message_after.edit(suppress=True)
