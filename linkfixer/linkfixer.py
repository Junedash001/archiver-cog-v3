import asyncio
import time
import aiohttp
import regex
import logging
import discord
from typing import Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass
from redbot.core import commands, app_commands, Config
from redbot.core.bot import Red

log = logging.getLogger("red.crab-cogs.linkfixer")

Span = Tuple[int, int]


@dataclass(frozen=True)
class Link:
    name: str
    pattern: regex.Pattern
    sub: str
    translatable: bool = False

    def fix(self, url: str) -> str:
        return self.pattern.sub(self.sub, url.split("?")[0].rstrip("/"))


GENERIC_LINK = regex.compile(r"(?<!<)(https?://[^\s|)>\]]+)")
BLOCK_OR_DELIMITER = regex.compile(r"```.*?```|`[^`]*?`|\\.|\|\|", regex.DOTALL)
TAIL = r"[^\s|)>\]]*[^\s|)>\].,;:!?]" + ")"
NOT = r"(?<![<=])"
FLAGS = regex.IGNORECASE
 
TWITTER_RE = regex.compile(NOT + r"https?://(?:www\.|m\.|mobile\.)?(?:x|twitter)\.com/(?P<tail>(?:[^\s/]+/)+status/" + TAIL, FLAGS)
INSTAGRAM_RE = regex.compile(NOT + r"https?://(?:www\.)?instagram\.com/(?P<tail>[^\s/]+/" + TAIL, FLAGS)
REDDIT_RE = regex.compile(NOT + r"https?://(?:www\.|old\.|np\.)?reddit\.com/(?P<tail>r/[^\s/]+/" + TAIL, FLAGS)
PIXIV_RE = regex.compile(NOT + r"https?://(?:www\.)?pixiv\.net/(?P<tail>" + TAIL, FLAGS)
THREADS_RE = regex.compile(NOT + r"https?://(?:www\.)?threads\.(?:net|com)/(?P<tail>@[^\s/]+/" + TAIL, FLAGS)
BILIBILI_RE = regex.compile(NOT + r"https?://(?P<pre>\w+\.)?bilibili\.com/(?P<tail>" + TAIL, FLAGS)
B23_RE = regex.compile(NOT + r"https?://(?P<pre>\w+\.)?b23\.tv/(?P<tail>" + TAIL, FLAGS)
TIKTOK_RE = regex.compile("".join([
    NOT, r"https?://(?:",
    r"(?P<pre>www\.)?tiktok\.com/(?P<tail>(?:[^\s/]+/[^\s/]+|t)/", TAIL,
    r"|(?P<pre>v[mt]\.)tiktok\.com/(?P<tail>", TAIL,
    r")"
]), FLAGS)
FIXEMBED_RE = regex.compile("".join([
    NOT, r"https?://(?:[\w-]+\.)?(?:",
    r"twitter\.com|x\.com|instagram\.com|reddit\.com|redd\.it",
    r"|threads\.(?:net|com)|pixiv\.net|bilibili\.com|b23\.tv|youtube\.com/post",
    r"|pinterest\.com/pin|pin\.it|tiktok\.com|sta\.sh",
    r")/(?P<tail>", TAIL
]), FLAGS)
 
ALL_LINKS = [
    Link("fxtwitter",   TWITTER_RE,   r"https://fxtwitter.com/\g<tail>", translatable=True),
    Link("vxtwitter",   TWITTER_RE,   r"https://vxtwitter.com/\g<tail>", translatable=True),
    Link("oginstagram", INSTAGRAM_RE, r"https://oginstagram.com/\g<tail>"),
    Link("vxinstagram", INSTAGRAM_RE, r"https://vxinstagram.com/\g<tail>"),
    Link("kkinstagram", INSTAGRAM_RE, r"https://kkinstagram.com/\g<tail>"),
    Link("vxreddit",    REDDIT_RE,    r"https://vxreddit.com/\g<tail>"),
    Link("redditez",    REDDIT_RE,    r"https://redditez.com/\g<tail>"),
    Link("phixiv",      PIXIV_RE,     r"https://phixiv.net/\g<tail>"),
    Link("ppxiv",       PIXIV_RE,     r"https://ppxiv.net/\g<tail>"),
    Link("viewthreads", THREADS_RE,   r"https://viewthreads.com/\g<tail>"),
    Link("tnktok",      TIKTOK_RE,    r"https://\g<pre>tnktok.com/\g<tail>"),
    Link("tiktokez",    TIKTOK_RE,    r"https://\g<pre>tiktokez.com/\g<tail>"),
    Link("vxbilibili",  BILIBILI_RE,  r"https://\g<pre>vxbilibili.com/\g<tail>", translatable=True),
    Link("vxb23",       B23_RE,       r"https://\g<pre>vxb23.tv/\g<tail>", translatable=True),
    Link("fixembed",    FIXEMBED_RE,  r"https://fixembed.app/embed?url=\g<0>"),
]

DEFAULT_DISABLED_LINKS = ["vxtwitter", "kkinstagram", "vxinstagram", "redditez", "tiktokez", "ppxiv"]


# --- Video-only mode, quote tweets and translation of non-English tweets --------
# These features ask vxtwitter's API about a tweet before its link is fixed:
#  * video-only: a tweet link is only fixed if the tweet has a video or GIF
#  * quote tweets: a quote tweet is always fixed (video or not) using the QUOTE_WITH fixer
#  * translate-foreign: a tweet whose language is not English is always fixed (video or not)
#    using the TRANSLATE_WITH fixer with /en appended, so Discord shows the English translation
# Priority: translation, then quote tweets, then the video-only rule.
VXTWITTER_API = "https://api.vxtwitter.com/{user}/status/{id}"
STATUS_RE = regex.compile(r"(?P<user>[^/\s]+)/status/(?P<id>\d+)")
VIDEO_MEDIA_TYPES = {"video", "gif", "animated_gif"}  # vxtwitter reports GIFs as "video"
# Twitter "lang" values that are not real languages (undetermined, only mentions/hashtags/media, ...)
NOT_A_LANGUAGE = {"", "und", "qme", "qam", "qht", "qct", "qst", "zxx"}
TRANSLATE_WITH = "vxtwitter"  # name of the fixer in ALL_LINKS that builds translated links
TRANSLATE_TO = "en"
QUOTE_WITH = "vxtwitter"  # name of the fixer in ALL_LINKS used for quote tweets
MAX_TWEET_LOOKUPS = 5  # per message; further tweet links are treated as having no video
LOOKUP_TIMEOUT = 8  # seconds
CACHE_TTL = 600  # seconds
CACHE_MAX = 500
REPLACE_ON_LOOKUP_FAILURE = False  # if the API errors out, leave the link alone

TRANSLATION_LINK = next(link for link in ALL_LINKS if link.name == TRANSLATE_WITH)
QUOTE_LINK = next(link for link in ALL_LINKS if link.name == QUOTE_WITH)


@dataclass(frozen=True)
class TweetInfo:
    has_video: bool
    lang: Optional[str] = None
    is_quote: bool = False


def tweet_has_video(data: dict) -> bool:
    """True if a vxtwitter API response lists a video or GIF among the tweet's media."""
    media = data.get("media_extended") or []
    return any(isinstance(m, dict) and m.get("type") in VIDEO_MEDIA_TYPES for m in media)


def tweet_info(data: dict) -> TweetInfo:
    lang = data.get("lang")
    return TweetInfo(
        tweet_has_video(data),
        lang if isinstance(lang, str) else None,
        bool(data.get("qrtURL")),  # vxtwitter sets qrtURL on quote tweets, and null otherwise
    )


def is_foreign_language(lang: Optional[str]) -> bool:
    """True if a Twitter `lang` value is a real language other than English."""
    if not isinstance(lang, str):
        return False
    code = lang.strip().lower()
    if code in NOT_A_LANGUAGE:
        return False
    return code.replace("_", "-").split("-")[0] != "en"


def tweet_api_url(url: str) -> Optional[str]:
    """The vxtwitter API URL for a tweet link, or None if it is not a tweet link."""
    m = TWITTER_RE.match(url)
    if not m:
        return None
    s = STATUS_RE.search(m.group("tail"))
    if not s:
        return None
    return VXTWITTER_API.format(user=s.group("user"), id=s.group("id"))


# {tweet url: TweetInfo, or None if the lookup failed}
Tweets = Dict[str, Optional[TweetInfo]]


def twitter_video_filter(tweets: Tweets) -> Callable[["Link", str], bool]:
    """Builds the `allow` callback for fix_links: tweet links need a video to be fixed."""
    def allow(fixer: Link, url: str) -> bool:
        if not TWITTER_RE.match(url):
            return True
        if url not in tweets:  # never looked up (over the per-message cap)
            return False
        info = tweets[url]
        if info is None:
            return REPLACE_ON_LOOKUP_FAILURE
        return info.has_video
    return allow


def twitter_translate_filter(tweets: Tweets) -> Callable[[str], bool]:
    """Builds the `translate` callback for fix_links: True for tweets not written in English."""
    def translate(url: str) -> bool:
        info = tweets.get(url)
        return info is not None and is_foreign_language(info.lang)
    return translate


def twitter_quote_filter(tweets: Tweets) -> Callable[[str], bool]:
    """Builds the `quote` callback for fix_links: True for quote tweets."""
    def quote(url: str) -> bool:
        info = tweets.get(url)
        return info is not None and info.is_quote
    return quote


def is_in_span(spans: List[Span], pos: int) -> bool:
    return any(start <= pos < end for start, end in spans)

def get_code_and_spoiler_spans(content: str) -> Tuple[List[Span], List[Span]]:
    """Returns lists of ```code blocks```/`code blocks` and ||spoiler blocks||"""
    code_spans = []
    spoiler_spans = []
    spoiler_start = None
    for m in BLOCK_OR_DELIMITER.finditer(content):
        token = m.group(0)
        if token == "||":
            if spoiler_start is None:
                spoiler_start = m.end()
            else:
                spoiler_spans.append((spoiler_start, m.start()))
                spoiler_start = None
        elif token.startswith("`"):
            code_spans.append((m.start(), m.end()))
    return code_spans, spoiler_spans

def extract_urls(content: str) -> Dict[str, bool]:
    """Returns every link outside of code blocks, mapped to whether it is inside a ||spoiler||."""
    code_spans, spoiler_spans = get_code_and_spoiler_spans(content)
    # stupid edge case
    # as of july 2026 in discord for android, an unclosed "||" can get closed by a codeblocked "||" even though a codeblocked "||" normally does not constitute a spoiler delimiter
    # but this whole thing is kinda pointless, as any spoilered url makes all embeds get spoilered
    spoiler_edge_case = any("||" in content[start:end] for start, end in code_spans)

    urls: Dict[str, bool] = {}
    for m in GENERIC_LINK.finditer(content):
        if is_in_span(code_spans, m.start()):
            continue
        spoiler = is_in_span(spoiler_spans, m.start()) or spoiler_edge_case
        urls[m.group(0)] = urls.get(m.group(0), False) or spoiler
    return urls

def fix_links(
    content: str,
    link_types: list[Link],
    language: str,
    allow: Optional[Callable[[Link, str], bool]] = None,
    translate: Optional[Callable[[str], bool]] = None,
    quote: Optional[Callable[[str], bool]] = None,
) -> str | None:
    """`allow(fixer, url)` may veto a fix: a vetoed link is left exactly as it was sent.

    `translate(url)` may force a link to be fixed with TRANSLATION_LINK and /en appended.
    `quote(url)` may force a link to be fixed with QUOTE_LINK.
    Both take priority over `allow` (translate first), and only apply to links that some
    enabled fixer matches.
    """
    urls = extract_urls(content)
    if not urls:
        return None
    
    out = []
    any_fixed = False
    for url, spoiler in urls.items():
        for fixer in link_types:
            if fixer.pattern.match(url):
                if translate is not None and translate(url):
                    url = f"{TRANSLATION_LINK.fix(url)}/{TRANSLATE_TO}"
                    any_fixed = True
                    break
                if quote is not None and quote(url):
                    url = QUOTE_LINK.fix(url)
                    if language and QUOTE_LINK.translatable:
                        url = f"{url}/{language}"
                    any_fixed = True
                    break
                if allow is not None and not allow(fixer, url):
                    break  # matched, but vetoed: do not try the remaining fixers either
                url = fixer.fix(url)
                if language and fixer.translatable:
                    url = f"{url}/{language}"
                any_fixed = True
                break
        spoiled_url = f"|| {url} ||"
        if spoiled_url in out and not spoiler:
            continue
        if url in out and spoiler:
            out.remove(url)
        if url not in out and spoiled_url not in out:
            out.append(spoiled_url if spoiler else url)

    return "\n".join(out) if any_fixed else None


class LinkFixer(commands.Cog):
    """Sends modified links to embed content from popular social media sites."""

    def __init__(self, bot: Red, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bot = bot
        self.config = Config.get_conf(self, identifier=44141349)
        self.config.register_guild(**{
            "enabled": False,
            "disabled_links": list(DEFAULT_DISABLED_LINKS),
            "language": None,
            "twitter_video_only": True,
            "translate_foreign": True,
            "fix_quote_tweets": True,
            "delete_original": False,
        })
        self.enabled_guilds: List[int] = []
        self.disabled_links: Dict[int, List[str]] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self._tweet_cache: Dict[str, Tuple[float, TweetInfo]] = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Red-DiscordBot LinkFixer cog"})
        all_guilds = await self.config.all_guilds()
        for gid, config in all_guilds.items():
            if config.get("enabled", False):
                self.enabled_guilds.append(gid)
                self.disabled_links[gid] = config.get("disabled_links", DEFAULT_DISABLED_LINKS)

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def red_delete_data_for_user(self, *args, **kwargs):
        """Nothing to delete"""
        pass

    async def fetch_tweet_info(self, url: str) -> Optional[TweetInfo]:
        """Asks vxtwitter's API about a tweet (video? language?). None means the lookup failed."""
        api_url = tweet_api_url(url)
        if not api_url or self.session is None:
            return None
        cached = self._tweet_cache.get(api_url)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            return cached[1]
        try:
            timeout = aiohttp.ClientTimeout(total=LOOKUP_TIMEOUT)
            async with self.session.get(api_url, timeout=timeout) as resp:
                if resp.status != 200:
                    log.warning("vxtwitter API returned %s for %s", resp.status, api_url)
                    return None
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as e:
            log.warning("vxtwitter API lookup failed for %s: %s", api_url, e)
            return None
        if not isinstance(data, dict):
            return None
        info = tweet_info(data)
        if len(self._tweet_cache) >= CACHE_MAX:
            oldest = min(self._tweet_cache, key=lambda k: self._tweet_cache[k][0])
            del self._tweet_cache[oldest]
        self._tweet_cache[api_url] = (time.monotonic(), info)
        return info

    async def lookup_tweets(self, content: str) -> Tweets:
        """Looks up every tweet link in the message ({url: TweetInfo, or None on failure})."""
        tweets = [u for u in extract_urls(content) if TWITTER_RE.match(u)][:MAX_TWEET_LOOKUPS]
        results = await asyncio.gather(*(self.fetch_tweet_info(u) for u in tweets))
        return dict(zip(tweets, results))

    @commands.Cog.listener()
    async def on_message_without_command(self, message: discord.Message):
        if not message.guild or message.guild.id not in self.enabled_guilds or message.author == message.guild.me:
            return
        perms = message.channel.permissions_for(message.guild.me)
        if not perms.send_messages or not perms.embed_links:
            return
        if not await self.is_valid_red_message(message):
            return

        link_types = [link for link in ALL_LINKS if link.name not in self.disabled_links.get(message.guild.id, [])]
        settings = await self.config.guild(message.guild).all()
        allow = translate = quote = None
        if settings["twitter_video_only"] or settings["translate_foreign"] or settings["fix_quote_tweets"]:
            tweets = await self.lookup_tweets(message.content)
            if settings["twitter_video_only"]:
                allow = twitter_video_filter(tweets)
            if settings["translate_foreign"]:
                translate = twitter_translate_filter(tweets)
            if settings["fix_quote_tweets"]:
                quote = twitter_quote_filter(tweets)
        fixed = fix_links(message.content, link_types, settings["language"], allow, translate, quote)
        if not fixed:
            return

        fixed = f"-# {message.author.mention} I fixed the links so the content embeds better.\n" + fixed
        await message.channel.send(fixed, allowed_mentions=discord.AllowedMentions.none())
        if message.channel.permissions_for(message.guild.me).manage_messages:
            try:
                if settings["delete_original"]:
                    await message.delete()
                else:
                    await message.edit(suppress=True)
            except (discord.NotFound, discord.Forbidden):
                pass

    @app_commands.command(name="fixlink", description="Send a fixed social media link with better embeds.")
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.choices(language=[app_commands.Choice(name="Unchanged", value=""),
                                    app_commands.Choice(name="English", value="en")])
    @app_commands.describe(link="One or more links to send as fixed embeds.",
                           language="If the provider supports it, translate the contents of the embed.")
    async def fix_links_command(self, inter: discord.Interaction, link: str, language: str = ""):
        disallowed_links = self.disabled_links.get(inter.guild.id, []) if inter.guild else DEFAULT_DISABLED_LINKS
        link_types = [link for link in ALL_LINKS if link.name not in disallowed_links]
        fixed = fix_links(link, link_types, language)
        if fixed:
            await inter.response.send_message(fixed, allowed_mentions=discord.AllowedMentions.none())
        elif GENERIC_LINK.search(link):
            await inter.response.send_message("The link(s) you provided are not supported, sorry!", ephemeral=True)
        else:
            await inter.response.send_message("You didn't provide a valid link!", ephemeral=True)

    async def is_valid_red_message(self, message: discord.Message) -> bool:
        return (
            isinstance(message.author, discord.Member)
            and await self.bot.allowed_by_whitelist_blacklist(message.author)
            and await self.bot.ignored_channel_or_guild(message)
            and not await self.bot.cog_disabled_in_guild(self, message.guild)
        )

    
    @commands.group(name="linkfixer", aliases=["linkfix"], invoke_without_command=True)  # type: ignore
    @commands.guild_only()
    @commands.admin_or_permissions(manage_guild=True)
    async def command_linkfixer(self, ctx: commands.Context):
        """Configure the LinkFixer cog."""
        await ctx.send_help()

    @command_linkfixer.command(name="enable")
    async def command_linkfixer_enable(self, ctx: commands.Context):
        """Enable LinkFixer in this server."""
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(True)
        if ctx.guild.id not in self.enabled_guilds:
            self.enabled_guilds.append(ctx.guild.id)
            self.disabled_links[ctx.guild.id] = await self.config.guild(ctx.guild).disabled_links()
        await ctx.reply(f"✅ LinkFixer enabled in {ctx.guild.name}")

    @command_linkfixer.command(name="disable")
    async def command_linkfixer_disable(self, ctx: commands.Context):
        """Disable LinkFixer in this server."""
        assert ctx.guild
        await self.config.guild(ctx.guild).enabled.set(False)
        if ctx.guild.id in self.enabled_guilds:
            self.enabled_guilds.remove(ctx.guild.id)
        await ctx.reply(f"⛔ LinkFixer disabled in {ctx.guild.name}")

    @command_linkfixer.command(name="videoonly", aliases=["twittervideo"])
    async def command_linkfixer_videoonly(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Only fix Twitter/X links when the tweet has a video or GIF.

        Tweets with only text or photos are left alone. Other sites are not affected.
        Run without an argument to see the current setting.
        """
        assert ctx.guild
        if enabled is None:
            current = await self.config.guild(ctx.guild).twitter_video_only()
            return await ctx.reply(f"Video-only mode for Twitter/X links is **{'on' if current else 'off'}**.")
        await self.config.guild(ctx.guild).twitter_video_only.set(enabled)
        if enabled:
            await ctx.reply("✅ Twitter/X links will only be fixed when the tweet has a video or GIF.")
        else:
            await ctx.reply("⛔ All Twitter/X links will be fixed, with or without video.")

    @command_linkfixer.command(name="translateforeign", aliases=["autotranslate"])
    async def command_linkfixer_translateforeign(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Translate tweets that are not in English.

        Tweets in another language are always fixed (with or without video) and get /en added
        so the embed shows an English translation. Run without an argument to see the setting.
        """
        assert ctx.guild
        if enabled is None:
            current = await self.config.guild(ctx.guild).translate_foreign()
            return await ctx.reply(f"Translating non-English tweets is **{'on' if current else 'off'}**.")
        await self.config.guild(ctx.guild).translate_foreign.set(enabled)
        if enabled:
            await ctx.reply("✅ Non-English tweets will be fixed and translated to English.")
        else:
            await ctx.reply("⛔ Non-English tweets are no longer translated automatically.")

    @command_linkfixer.command(name="quotetweets", aliases=["quote"])
    async def command_linkfixer_quotetweets(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Always fix quote tweets with vxtwitter, with or without video.

        This matters when video-only mode is on: a tweet quoting a video tweet has no video of
        its own and would otherwise be skipped. Run without an argument to see the setting.
        """
        assert ctx.guild
        if enabled is None:
            current = await self.config.guild(ctx.guild).fix_quote_tweets()
            return await ctx.reply(f"Fixing quote tweets is **{'on' if current else 'off'}**.")
        await self.config.guild(ctx.guild).fix_quote_tweets.set(enabled)
        if enabled:
            await ctx.reply("✅ Quote tweets will always be fixed with vxtwitter.")
        else:
            await ctx.reply("⛔ Quote tweets follow the normal rules again (video-only applies).")

    @command_linkfixer.command(name="deleteoriginal", aliases=["delete"])
    async def command_linkfixer_deleteoriginal(self, ctx: commands.Context, enabled: Optional[bool] = None):
        """Delete the original message after posting the fixed links.

        Anything else in the original message besides links is lost. Needs the Manage Messages
        permission. Without this, the original message just has its embeds hidden.
        Run without an argument to see the current setting.
        """
        assert ctx.guild
        if enabled is None:
            current = await self.config.guild(ctx.guild).delete_original()
            return await ctx.reply(f"Deleting original messages is **{'on' if current else 'off'}**.")
        await self.config.guild(ctx.guild).delete_original.set(enabled)
        if enabled:
            msg = "✅ Original messages will be deleted after the fixed links are posted."
            if not ctx.guild.me.guild_permissions.manage_messages:
                msg += "\n⚠️ I don't have the Manage Messages permission, so nothing will be deleted yet."
            await ctx.reply(msg)
        else:
            await ctx.reply("⛔ Original messages will be kept (their embeds are hidden instead).")

    
    @command_linkfixer.group(name="translate", aliases=["language", "english"], invoke_without_command=True)
    async def command_linkfixer_translate(self, ctx: commands.Context):
        """Controls automatic embed translations."""
        await ctx.send_help()
    
    @command_linkfixer_translate.command(name="enable", aliases=["english", "on", "yes", "true"])
    async def command_linkfixer_translate_enable(self, ctx: commands.Context):
        """Enables compatible links to be translated to English."""
        assert ctx.guild
        await self.config.guild(ctx.guild).language.set("en")
        await ctx.reply(f"✅ Compatible links will be translated to English (such as fxtwitter).")

    @command_linkfixer_translate.command(name="disable", aliases=["off", "no", "false"])
    async def command_linkfixer_translate_disable(self, ctx: commands.Context):
        """Disables compatible links from being translated to English."""
        assert ctx.guild
        await self.config.guild(ctx.guild).language.set(None)
        await ctx.reply(f"⛔ Embeds will not be translated.")

    
    @command_linkfixer.group(name="links", aliases=["link", "fix"], invoke_without_command=True)
    async def command_linkfixer_links(self, ctx: commands.Context):
        """List or toggle available links for the fixer."""
        await ctx.send_help()

    @command_linkfixer_links.command(name="list")
    async def command_linkfixer_links_list(self, ctx: commands.Context):
        """List all available links for the fixer."""
        assert ctx.guild
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        links = []
        for link in ALL_LINKS:
            links.append(f" `{'⛔' if link.name in disabled_links else '✅'} {link.name}`")
        await ctx.send("-# (Links will be fixed with the first matching fixer in the list)\n>>> " + "\n".join(links))

    @command_linkfixer_links.command(name="enable", aliases=["add"])
    async def command_linkfixer_links_enable(self, ctx: commands.Context, *link_names: str):
        """Enables one or more link fixes."""
        assert ctx.guild
        if ctx.guild.id not in self.enabled_guilds:
            return await ctx.reply(f"⚠️ LinkFixer is not enabled in {ctx.guild.name}")
        if not link_names:
            return await ctx.send_help()
        link_names = tuple(name.casefold() for name in link_names)
        all_links = set(link.name for link in ALL_LINKS)
        if len(link_names) == 1 and link_names[0] == "all":
            link_names = tuple(all_links)
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        disabled_links = list(set(disabled_links) - set(link_names))
        await self.config.guild(ctx.guild).disabled_links.set(disabled_links)
        self.disabled_links[ctx.guild.id] = disabled_links
        invalid_links = list(set(link_names) - all_links)
        if invalid_links:
            await ctx.send("⚠️ Invalid options: " + ", ".join([f"`{link}`" for link in invalid_links]))
        else:
            await ctx.tick(message="Done")
        await self.command_linkfixer_links_list(ctx)

    @command_linkfixer_links.command(name="disable", aliases=["remove"])
    async def command_linkfixer_links_disable(self, ctx: commands.Context, *link_names: str):
        """Disables one or more link fixes."""
        assert ctx.guild
        if ctx.guild.id not in self.enabled_guilds:
            return await ctx.reply(f"⚠️ LinkFixer is not enabled in {ctx.guild.name}")
        if not link_names:
            return await ctx.send_help()
        link_names = tuple(name.casefold() for name in link_names)
        all_links = set(link.name for link in ALL_LINKS)
        if len(link_names) == 1 and link_names[0] == "all":
            link_names = tuple(all_links)
        disabled_links = await self.config.guild(ctx.guild).disabled_links()
        disabled_links = list(all_links & (set(disabled_links) | set(link_names)))
        await self.config.guild(ctx.guild).disabled_links.set(disabled_links)
        self.disabled_links[ctx.guild.id] = disabled_links
        invalid_links = list(set(link_names) - all_links)
        if invalid_links:
            await ctx.send("⚠️ Invalid options: " + ", ".join([f"`{link}`" for link in invalid_links]))
        else:
            await ctx.tick(message="Done")
        await self.command_linkfixer_links_list(ctx)
