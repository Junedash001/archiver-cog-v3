import re

from discord import Embed, Message, channel

from .constants import INSTA_REGEX_PATTERN, SocialMedia

from .constants import INSTA_REGEX_PATTERN, TWITTER_REGEX_PATTERN, SocialMedia


def convert_to_ddinsta_url(embeds: list[Embed]):
    """
    Parameters
    ----------
    embeds: list of Discord embeds

    Returns
    -------
        filtered list of Instagram URLs that have been converted to ddinstagram
    """

    # pulls only video embeds from list of embeds
    urls = [entry.url for entry in embeds]

    ddinsta_urls = [
        re.sub(INSTA_REGEX_PATTERN, r"https://vx\1", result)
        for result in urls
        if re.match(INSTA_REGEX_PATTERN, result)
    ]

    return ddinsta_urls


def convert_to_vx_twitter_url(embeds: list[Embed]):
    """
    Parameters
    ----------
    embeds: list of Discord embeds
    Returns
    -------
        filtered list of twitter URLs that have been converted to fxtwitter
    """
    urls = [entry.url for entry in embeds if entry.video]
    fxtwitter_urls = []
    for result in urls:
        if re.match(TWITTER_REGEX_PATTERN, result):
            # Replace both twitter.com and x.com with fxtwitter.com
            url = re.sub(r"https://(?:www\.)?(twitter\.com|x\.com)", "https://fxtwitter.com", result)
            fxtwitter_urls.append(url)
    return fxtwitter_urls
    

def urls_to_string(links: list[str], socialMedia: SocialMedia):
    """
    Parameters
    ----------
    links: list[str]
        A list of urls
    socialMedia: SocialMedia
        The social media to replace.
    author_mention: str
        The mention string for the original poster
    Returns
    -------
        Formatted output
    """
    return "\n".join(
        [
            f"{socialMedia.value} link replaced for better embeds",
            *links,
        ]
    )


def valid(message: Message):
    """
    Parameters
    ----------
    message: Discord input message object

    Returns
    -------
        True if the message is from a human in a guild and contains embeds
        False otherwise
    """

    # skips if the message is sent by any bot
    if message.author.bot:
        return False

    # skips if message is in dm
    if isinstance(message.channel, channel.DMChannel):
        return False

    # skips if the message has no embeds
    if not message.embeds:
        return False

    return True
