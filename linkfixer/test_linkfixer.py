import asyncio
import time
import types
from dataclasses import dataclass

from .linkfixer import (
    ALL_LINKS,
    DEFAULT_DISABLED_LINKS,
    LinkFixer,
    TweetInfo,
    extract_urls,
    fix_links,
    is_foreign_language,
    tweet_api_url,
    tweet_has_video,
    tweet_info,
    twitter_translate_filter,
    twitter_video_filter,
)

NAMES = [l.name for l in ALL_LINKS]
DEFAULT_NAMES = [n for n in NAMES if n not in DEFAULT_DISABLED_LINKS]


@dataclass(frozen=True)
class Case:
    src: str
    want: str | None
    only: tuple[str, ...] | None
    lang: str | None
    loose: bool  # ignore trailing punctuation left over from the message


def case(src, want, only: str | tuple[str, ...] | None = None, lang: str | None = None, loose=False):
    if isinstance(only, str):
        new_only = (only,)
    elif only is not None:
        new_only = tuple(only)
    else:
        new_only = None
    return Case(src, want, new_only, lang, loose)


def run_fix_links(src, only=None, lang="", allow=None, translate=None):
    names = DEFAULT_NAMES if only is None else only
    link_types = [l for l in ALL_LINKS if l.name in names]
    result = fix_links(src, link_types, lang, allow, translate)
    return result


LINK_TESTS = [
    # twitter
    case("https://x.com/foo/status/123", "https://fxtwitter.com/foo/status/123", "fxtwitter"),
    case("https://www.twitter.com/foo/status/123?s=20", "https://fxtwitter.com/foo/status/123", "fxtwitter"),
    case("https://mobile.twitter.com/foo/status/1", "https://fxtwitter.com/foo/status/1", "fxtwitter"),
    case("https://m.twitter.com/foo/status/1", "https://fxtwitter.com/foo/status/1", "fxtwitter"),
    case("https://x.com/i/web/status/5", "https://fxtwitter.com/i/web/status/5", "fxtwitter"),
    case("https://x.com/foo/status/123/photo/1", "https://fxtwitter.com/foo/status/123/photo/1", "fxtwitter"),
    case("https://X.com/Foo/status/1", "https://fxtwitter.com/Foo/status/1", "fxtwitter"),
    case("https://x.com/foo/status/123", "https://vxtwitter.com/foo/status/123", "vxtwitter"),
    case("https://x.com/foo/likes", None, "fxtwitter"),
    case("https://x.com/foo", None, "fxtwitter"),
    case("https://fxtwitter.com/foo/status/1", None, "fxtwitter"),
    # instagram
    case("https://www.instagram.com/p/ABC/", "https://oginstagram.com/p/ABC", "oginstagram"),
    case("https://www.instagram.com/p/ABC/", "https://vxinstagram.com/p/ABC", "vxinstagram"),
    case("https://www.instagram.com/p/ABC/", "https://kkinstagram.com/p/ABC", "kkinstagram"),
    case("https://instagram.com/reel/XYZ/?igsh=1", "https://kkinstagram.com/reel/XYZ", "kkinstagram"),
    case("https://instagram.com/someuser/", None, "kkinstagram"),
    case("https://instagram.com/reels/ABC/", "https://kkinstagram.com/reels/ABC", "kkinstagram"),
    case("https://instagram.com/tv/ABC/", "https://kkinstagram.com/tv/ABC", "kkinstagram"),
    case("https://instagram.com/someuser/p/ABC/", "https://kkinstagram.com/someuser/p/ABC", "kkinstagram"),
      #case("https://instagram.com/someuser/reels/", None, "kkinstagram"),
      #case("https://instagram.com/someuser/tagged/", None, "kkinstagram"),
      #case("https://instagram.com/stories/someuser/123/", None, "kkinstagram"),
      #case("https://instagram.com/explore/tags/cats/", None, "kkinstagram"),
      #case("https://instagram.com/p/", None, "kkinstagram"),
    # reddit
    case("https://www.reddit.com/r/foo/comments/abc/title/", "https://vxreddit.com/r/foo/comments/abc/title", "vxreddit"),
    case("https://old.reddit.com/r/foo/comments/abc", "https://vxreddit.com/r/foo/comments/abc", "vxreddit"),
    case("https://reddit.com/r/foo/s/abc", "https://vxreddit.com/r/foo/s/abc", "vxreddit"),
    case("https://www.reddit.com/r/foo/comments/abc/title/", "https://redditez.com/r/foo/comments/abc/title", "redditez"),
    # pixiv
    case("https://www.pixiv.net/en/artworks/123", "https://phixiv.net/en/artworks/123", "phixiv"),
    case("https://www.pixiv.net/en/artworks/123", "https://ppxiv.net/en/artworks/123", "ppxiv"),
    case("https://www.pixiv.net/", None, "phixiv"),
    # threads
    case("https://www.threads.com/@u/post/ABC", "https://viewthreads.com/@u/post/ABC", "viewthreads"),
    case("https://www.threads.net/@u/post/ABC", "https://viewthreads.com/@u/post/ABC", "viewthreads"),
    case("https://www.threads.com/@u", None, "viewthreads"),
    # tiktok
    case("https://www.tiktok.com/@u/video/123", "https://www.tnktok.com/@u/video/123", "tnktok"),
    case("https://tiktok.com/@u/video/123", "https://tnktok.com/@u/video/123", "tnktok"),
    case("https://vm.tiktok.com/ZM123/", "https://vm.tnktok.com/ZM123", "tnktok"),
    case("https://vt.tiktok.com/ZS9/", "https://vt.tnktok.com/ZS9", "tnktok"),
    case("https://www.tiktok.com/t/ZT123/", "https://www.tnktok.com/t/ZT123", "tnktok"),
    case("https://www.tiktok.com/@u/video/123?is_from_webapp=1", "https://www.tnktok.com/@u/video/123", "tnktok"),
    case("https://tiktok.com/@u/ look at this/ok", None, "tnktok"),  # whitespace must not be glued into a link
    case("https://www.tiktok.com/@u/video/123", "https://www.tiktokez.com/@u/video/123", "tiktokez"),
    # bilibili
    case("https://www.bilibili.com/video/BV1x", "https://www.vxbilibili.com/video/BV1x", "vxbilibili"),
    case("https://bilibili.com/video/BV1x", "https://vxbilibili.com/video/BV1x", "vxbilibili"),
    case("https://b23.tv/abc", "https://vxb23.tv/abc", "vxb23"),
    # fixembed (the query is stripped *before* it is embedded, so there is no unencoded & or ?)
    case("https://x.com/foo/status/123", "https://fixembed.app/embed?url=https://x.com/foo/status/123", "fixembed"),
    case("https://x.com/foo/status/123?s=20&a=1", "https://fixembed.app/embed?url=https://x.com/foo/status/123", "fixembed"),
    case("https://old.reddit.com/r/a/comments/1", "https://fixembed.app/embed?url=https://old.reddit.com/r/a/comments/1", "fixembed"),
    case("https://youtube.com/post/abc", "https://fixembed.app/embed?url=https://youtube.com/post/abc", "fixembed"),
    case("https://pin.it/abc", "https://fixembed.app/embed?url=https://pin.it/abc", "fixembed"),
    case("https://redd.it/abc", "https://fixembed.app/embed?url=https://redd.it/abc", "fixembed"),
    case("https://youtube.com/watch?v=abc", None, "fixembed"),
    case("https://fixembed.app/embed?url=https://x.com/a/status/1", None, "fixembed"),
]


DEFAULTS_TESTS = [
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1"),
    case("https://www.instagram.com/p/ABC/", "https://oginstagram.com/p/ABC"),
    case("https://www.reddit.com/r/foo/comments/abc/t/", "https://vxreddit.com/r/foo/comments/abc/t"),
    case("https://www.pixiv.net/en/artworks/123", "https://phixiv.net/en/artworks/123"),
    case("https://www.threads.com/@u/post/ABC", "https://viewthreads.com/@u/post/ABC"),
    case("https://www.tiktok.com/@u/video/123", "https://www.tnktok.com/@u/video/123"),
    case("https://www.bilibili.com/video/BV1x", "https://www.vxbilibili.com/video/BV1x"),
    case("https://b23.tv/abc", "https://vxb23.tv/abc"),
    case("https://www.pinterest.com/pin/123/", "https://fixembed.app/embed?url=https://www.pinterest.com/pin/123"),
    case("https://fixembed.app/embed?url=https://x.com/a/status/1", None),   # never wrap twice
    case("<https://x.com/foo/status/1>", None),                              # <link> = embed suppressed on purpose
    case("https://x.com/a/status/1 https://www.instagram.com/p/ABC https://www.reddit.com/r/foo/comments/abc/t/",
      "https://fxtwitter.com/a/status/1\nhttps://oginstagram.com/p/ABC\nhttps://vxreddit.com/r/foo/comments/abc/t"),
]


SPOILERS_TESTS = [
    case("||https://x.com/foo/status/1||", "|| https://fxtwitter.com/foo/status/1 ||"),
    case("||https://x.com/foo/status/1?s=20||", "|| https://fxtwitter.com/foo/status/1 ||"),
    case("|| https://x.com/foo/status/1 ||", "|| https://fxtwitter.com/foo/status/1 ||"),
    case("||https://x.com/foo/status/1||", "|| https://fxtwitter.com/foo/status/1/en ||", lang="en"),
    case("https://x.com/a/status/1 ||https://x.com/b/status/2||",
      "https://fxtwitter.com/a/status/1\n|| https://fxtwitter.com/b/status/2 ||"),
    case("||https://x.com/b/status/2|| https://x.com/a/status/1",
      "|| https://fxtwitter.com/b/status/2 ||\nhttps://fxtwitter.com/a/status/1"),
    case("https://x.com/a/status/1 ||https://x.com/a/status/1||", "|| https://fxtwitter.com/a/status/1 ||"),  # spoiler wins on dupes
    case("||https://x.com/a/status/1", "https://fxtwitter.com/a/status/1"),   # unclosed || is not a spoiler
    case("`||` https://x.com/a/status/1", "|| https://fxtwitter.com/a/status/1 ||"),  # the Android quirk in fix_links
]


CODEBLOCK_TESTS = [
    case("`https://x.com/a/status/1`", None),
    case("```https://x.com/a/status/1```", None),
    case("```\nhttps://x.com/a/status/1\n```", None),
    case("`https://x.com/a/status/1` https://x.com/b/status/2", "https://fxtwitter.com/b/status/2"),
    case("`https://x.com/a/status/1", "https://fxtwitter.com/a/status/1"),   # unclosed backtick is literal text
]


MULTILINK_TESTS = [
    case("https://x.com/a/status/1 https://x.com/b/status/2", "https://fxtwitter.com/a/status/1\nhttps://fxtwitter.com/b/status/2"),
    case("https://x.com/a/status/1\nhttps://x.com/b/status/2", "https://fxtwitter.com/a/status/1\nhttps://fxtwitter.com/b/status/2"),
    case("look: https://x.com/a/status/1\nand https://x.com/b/status/2", "https://fxtwitter.com/a/status/1\nhttps://fxtwitter.com/b/status/2"),
    case("https://x.com/a/status/1 https://x.com/a/status/1", "https://fxtwitter.com/a/status/1"),
    case("https://x.com/a/status/1 https://example.com/page", "https://fxtwitter.com/a/status/1\nhttps://example.com/page"),
    case("https://example.com/page", None),
    case("just some text", None),
    case("", None),
]


TRANSLATION_TESTS = [
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1/en", lang="en"),
    case("https://x.com/foo/status/1/", "https://fxtwitter.com/foo/status/1/en", lang="en"),
    case("https://x.com/foo/status/1?s=20", "https://fxtwitter.com/foo/status/1/en", lang="en"),
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1", lang=""),
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1", lang=None),  # config default is None
    case("https://www.reddit.com/r/foo/comments/abc/t/", "https://vxreddit.com/r/foo/comments/abc/t", lang="en"),
    case("https://www.instagram.com/p/ABC/", "https://oginstagram.com/p/ABC", lang="en"),
    case("https://x.com/a/status/1 https://www.reddit.com/r/foo/comments/abc/t/",
      "https://fxtwitter.com/a/status/1/en\nhttps://vxreddit.com/r/foo/comments/abc/t", lang="en"),
]


SELECTION_TESTS = [
    case("https://x.com/foo/status/1", "https://fxtwitter.com/foo/status/1", only=("vxtwitter", "fxtwitter")),
    case("https://www.instagram.com/p/ABC/", "https://vxinstagram.com/p/ABC", only=("kkinstagram", "vxinstagram")),
    case("https://x.com/foo/status/1", "https://fixembed.app/embed?url=https://x.com/foo/status/1", only=("fixembed",)),
    case("https://x.com/foo/status/1", None, only=()),
]


ROBUSTNESS_TESTS = [
    case("https://x.com.evil.com/foo/status/1", None),
    case("https://evil.com/x.com/foo/status/1", None),
    case("https://nottwitter.com/foo/status/1", None),
    case("https://example.com/r/https://x.com/a/status/1", None),     # url embedded in another url's path
    case("https://example.com/?u=https://x.com/a/status/1", None),    # ...or its query
    case("(https://x.com/a/status/1)", "https://fxtwitter.com/a/status/1"),
    case("[t](https://x.com/foo/status/1)", "https://fxtwitter.com/foo/status/1"),
    case("https://X.COM/Foo/Status/1", "https://fxtwitter.com/Foo/Status/1"),
]


PUNCTUATION_TESTS = [
    case("see https://x.com/foo/status/1.", "https://fxtwitter.com/foo/status/1", loose=True),
    case("wow https://x.com/a/status/1, nice", "https://fxtwitter.com/a/status/1", loose=True),
    case("is it https://x.com/a/status/1?", "https://fxtwitter.com/a/status/1", loose=True),
    case("https://x.com/a/status/1!!", "https://fxtwitter.com/a/status/1", loose=True),
]


TEST_SUITES = {
    "per-link": LINK_TESTS,
    "default set": DEFAULTS_TESTS,
    "spoilers": SPOILERS_TESTS,
    "code blocks": CODEBLOCK_TESTS,
    "multiple links": MULTILINK_TESTS,
    "language": TRANSLATION_TESTS,
    "selection": SELECTION_TESTS,
    "robustness": ROBUSTNESS_TESTS,
    "punctuation": PUNCTUATION_TESTS,
}


KNOWN_BUGS = [
    ("bilibili part number (?p=2) is dropped", "https://www.bilibili.com/video/BV1x?p=2"),
    ("instagram carousel index (?img_index=2) is dropped", "https://www.instagram.com/p/ABC/?img_index=2"),
    ("legacy pixiv url loses the query it depends on", "https://www.pixiv.net/member_illust.php?mode=medium&illust_id=123"),
    ("some instagram urls are matched when they are not posts", "https://www.instagram.com/someuser/reels"),
]


def run_suite(name: str, cases: list[Case]):
    failed = 0
    for case in cases:
        try:
            got = run_fix_links(case.src, case.only, case.lang or "")
        except Exception as e:  # bad group names, wrong signature, etc.
            got = f"ERROR {type(e).__name__}: {e}"
        cmp = got.rstrip(".,;:!?") if (case.loose and isinstance(got, str)) else got
        if cmp != case.want:
            failed += 1
            print(f"FAIL [{name}]")
            print(f"   in:    {case.src!r}")
            if case.only is not None:
                print(f"   only:  {case.only}")
            if case.lang:
                print(f"   lang:  {case.lang!r}")
            print(f"   want:  {case.want!r}")
            print(f"   got:   {got!r}")
    return failed


# --- Twitter video-only mode and translation of non-English tweets ---------------

VIDEO = "https://x.com/a/status/1"
PHOTO = "https://x.com/b/status/2"
TEXT = "https://x.com/c/status/3"


def tw(video: bool, lang: str | None = "en") -> TweetInfo:
    return TweetInfo(video, lang)


def with_filters(src, tweets, only=None, lang="", video_only=True, translate_foreign=True):
    """Runs fix_links the way the cog does, with the two features switched on or off."""
    allow = twitter_video_filter(tweets) if video_only else None
    translate = twitter_translate_filter(tweets) if translate_foreign else None
    return run_fix_links(src, only, lang, allow, translate)


# (message, {tweet url: TweetInfo or None}, expected result, only)
TWITTER_FILTER_TESTS = [
    # --- video-only ---
    ("https://x.com/a/status/1", {VIDEO: tw(True)}, "https://fxtwitter.com/a/status/1", None),
    ("https://x.com/b/status/2", {PHOTO: tw(False)}, None, None),
    ("https://x.com/a/status/1?s=20", {"https://x.com/a/status/1?s=20": tw(True)}, "https://fxtwitter.com/a/status/1", None),
    ("https://x.com/a/status/1", {VIDEO: tw(True)}, "https://vxtwitter.com/a/status/1", ("vxtwitter",)),
    ("https://x.com/b/status/2", {PHOTO: tw(False)}, None, ("vxtwitter",)),
    # a link that was never looked up counts as "no video"; so does a failed lookup
    ("https://x.com/a/status/1", {}, None, None),
    ("https://x.com/a/status/1", {VIDEO: None}, None, None),
    # the veto must not fall through to the next fixer (fixembed also matches tweets)
    ("https://x.com/b/status/2", {PHOTO: tw(False)}, None, ("fxtwitter", "fixembed")),
    ("https://x.com/b/status/2", {PHOTO: tw(False)}, None, ("fixembed",)),
    ("https://x.com/a/status/1", {VIDEO: tw(True)}, "https://fixembed.app/embed?url=https://x.com/a/status/1", ("fixembed",)),
    # mixed tweets: only the video one is fixed; the other is passed through as sent
    ("https://x.com/a/status/1 https://x.com/b/status/2", {VIDEO: tw(True), PHOTO: tw(False)},
     "https://fxtwitter.com/a/status/1\nhttps://x.com/b/status/2", None),
    # other sites are not affected
    ("https://www.instagram.com/p/ABC/", {}, "https://oginstagram.com/p/ABC", None),
    ("https://www.reddit.com/r/foo/comments/abc/t/", {}, "https://vxreddit.com/r/foo/comments/abc/t", None),
    ("https://x.com/b/status/2 https://www.instagram.com/p/ABC/", {PHOTO: tw(False)},
     "https://x.com/b/status/2\nhttps://oginstagram.com/p/ABC", None),
    # spoilers keep working
    ("||https://x.com/a/status/1||", {VIDEO: tw(True)}, "|| https://fxtwitter.com/a/status/1 ||", None),
    ("||https://x.com/b/status/2||", {PHOTO: tw(False)}, None, None),
    # --- non-English tweets are translated, video or not ---
    ("https://x.com/b/status/2", {PHOTO: tw(False, "ja")}, "https://vxtwitter.com/b/status/2/en", None),
    ("https://x.com/a/status/1", {VIDEO: tw(True, "ja")}, "https://vxtwitter.com/a/status/1/en", None),
    ("https://x.com/b/status/2?s=20", {"https://x.com/b/status/2?s=20": tw(False, "fr")}, "https://vxtwitter.com/b/status/2/en", None),
    ("||https://x.com/b/status/2||", {PHOTO: tw(False, "ko")}, "|| https://vxtwitter.com/b/status/2/en ||", None),
    ("https://x.com/b/status/2", {PHOTO: tw(False, "zh-cn")}, "https://vxtwitter.com/b/status/2/en", None),
    # always vxtwitter + /en, whichever twitter fixer the server has enabled
    ("https://x.com/b/status/2", {PHOTO: tw(False, "ja")}, "https://vxtwitter.com/b/status/2/en", ("fxtwitter",)),
    ("https://x.com/b/status/2", {PHOTO: tw(False, "ja")}, "https://vxtwitter.com/b/status/2/en", ("vxtwitter",)),
    ("https://x.com/b/status/2", {PHOTO: tw(False, "ja")}, "https://vxtwitter.com/b/status/2/en", ("fixembed",)),
    # ...but not when the server has no fixer for the link at all
    ("https://x.com/b/status/2", {PHOTO: tw(False, "ja")}, None, ("oginstagram",)),
    # English / undetermined / unknown languages follow the normal video-only rules
    ("https://x.com/b/status/2", {PHOTO: tw(False, "en")}, None, None),
    ("https://x.com/b/status/2", {PHOTO: tw(False, "EN")}, None, None),
    ("https://x.com/b/status/2", {PHOTO: tw(False, "en-GB")}, None, None),
    ("https://x.com/b/status/2", {PHOTO: tw(False, "und")}, None, None),
    ("https://x.com/b/status/2", {PHOTO: tw(False, "qme")}, None, None),
    ("https://x.com/b/status/2", {PHOTO: tw(False, None)}, None, None),
    ("https://x.com/b/status/2", {PHOTO: None}, None, None),
    ("https://x.com/a/status/1", {VIDEO: tw(True, "en")}, "https://fxtwitter.com/a/status/1", None),
    ("https://x.com/a/status/1", {VIDEO: tw(True, "und")}, "https://fxtwitter.com/a/status/1", None),
    # a mix of all of the above
    ("https://x.com/a/status/1 https://x.com/b/status/2 https://x.com/c/status/3",
     {VIDEO: tw(True, "en"), PHOTO: tw(False, "de"), TEXT: tw(False, "en")},
     "https://fxtwitter.com/a/status/1\nhttps://vxtwitter.com/b/status/2/en\nhttps://x.com/c/status/3", None),
]


# vxtwitter API responses, trimmed to the fields that matter
API_VIDEO = {"media_extended": [{"type": "video", "url": "https://video.twimg.com/a.mp4"}]}
API_GIF_AS_VIDEO = {"media_extended": [{"type": "video", "duration_millis": 0, "url": "https://video.twimg.com/tweet_video/a.mp4"}]}
API_GIF = {"media_extended": [{"type": "gif", "url": "https://video.twimg.com/tweet_video/a.mp4"}]}
API_PHOTO = {"media_extended": [{"type": "image", "url": "https://pbs.twimg.com/media/a.jpg"}]}
API_PHOTO_JA = {"media_extended": [{"type": "image", "url": "https://pbs.twimg.com/media/a.jpg"}], "lang": "ja"}
API_VIDEO_JA = {"media_extended": [{"type": "video", "url": "y"}], "lang": "ja"}
API_MIXED = {"media_extended": [{"type": "image", "url": "x"}, {"type": "video", "url": "y"}]}
API_TEXT_ONLY = {"media_extended": [], "text": "hello"}
API_NO_FIELD = {"text": "hello"}
API_NULL_FIELD = {"media_extended": None}
API_GARBAGE = {"media_extended": ["video", 5, None]}


class FakeResponse:
    def __init__(self, status, data):
        self.status = status
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


class FakeSession:
    def __init__(self, responses: dict[str, tuple[int, object]]):
        self.responses = responses
        self.calls: list[str] = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url not in self.responses:
            return FakeResponse(404, {})
        status, data = self.responses[url]
        if isinstance(data, BaseException) and not isinstance(data, ValueError):
            raise data
        return FakeResponse(status, data)


def make_cog(responses):
    cog = LinkFixer.__new__(LinkFixer)  # skip __init__: no bot or config needed for these checks
    cog.session = FakeSession(responses)
    cog._tweet_cache = {}
    return cog


# --- fakes for the message listener ------------------------------------------------

class FakeGuildConfig:
    def __init__(self, settings):
        self._settings = settings

    async def all(self):
        return dict(self._settings)


class FakeConfig:
    def __init__(self, settings):
        self._settings = settings

    def guild(self, guild):
        return FakeGuildConfig(self._settings)


class FakeChannel:
    def __init__(self, can_manage=True):
        self.can_manage = can_manage
        self.sent: list[str] = []

    def permissions_for(self, member):
        return types.SimpleNamespace(send_messages=True, embed_links=True, manage_messages=self.can_manage)

    async def send(self, content, **kwargs):
        self.sent.append(content)


class FakeMessage:
    def __init__(self, content, channel, guild):
        self.content = content
        self.channel = channel
        self.guild = guild
        self.author = types.SimpleNamespace(mention="@user")
        self.deleted = False
        self.suppressed = False

    async def delete(self):
        self.deleted = True

    async def edit(self, suppress=False):
        self.suppressed = suppress


def listener_settings(**overrides):
    base = {"language": None, "twitter_video_only": True, "translate_foreign": True, "delete_original": False}
    base.update(overrides)
    return base


def run_listener(content, responses, can_manage=True, **settings):
    cog = make_cog(responses)
    cog.enabled_guilds = [1]
    cog.disabled_links = {1: list(DEFAULT_DISABLED_LINKS)}
    cog.config = FakeConfig(listener_settings(**settings))

    async def valid(message):
        return True
    cog.is_valid_red_message = valid

    guild = types.SimpleNamespace(id=1, me=object())
    channel = FakeChannel(can_manage)
    message = FakeMessage(content, channel, guild)
    asyncio.run(cog.on_message_without_command(message))
    return message, channel, cog


def expect(failed, label, ok, detail=""):
    if not ok:
        print(f"FAIL [twitter] {label} {detail}")
        return failed + 1
    return failed


def run_twitter_suite():
    failed = 0
    for src, tweets, want, only in TWITTER_FILTER_TESTS:
        got = with_filters(src, tweets, only)
        if got != want:
            failed += 1
            print("FAIL [twitter filters]")
            print(f"   in:    {src!r}  tweets={tweets}")
            if only:
                print(f"   only:  {only}")
            print(f"   want:  {want!r}")
            print(f"   got:   {got!r}")

    # the two features can be switched off independently
    flag_cases = [
        # (message, tweets, video_only, translate_foreign, lang, want)
        (PHOTO, {PHOTO: tw(False, "en")}, False, True, "", "https://fxtwitter.com/b/status/2"),
        (PHOTO, {PHOTO: tw(False, "ja")}, False, True, "", "https://vxtwitter.com/b/status/2/en"),
        (PHOTO, {PHOTO: tw(False, "ja")}, True, False, "", None),
        (VIDEO, {VIDEO: tw(True, "ja")}, True, False, "", "https://fxtwitter.com/a/status/1"),
        (PHOTO, {PHOTO: tw(False, "ja")}, False, False, "", "https://fxtwitter.com/b/status/2"),
        # the existing server-wide translate option still adds /en to English tweets too
        (VIDEO, {VIDEO: tw(True, "en")}, True, True, "en", "https://fxtwitter.com/a/status/1/en"),
        # ...and a translated tweet never ends up with /en/en
        (PHOTO, {PHOTO: tw(False, "ja")}, True, True, "en", "https://vxtwitter.com/b/status/2/en"),
    ]
    for src, tweets, vo, tf, lang, want in flag_cases:
        got = with_filters(src, tweets, None, lang, vo, tf)
        failed = expect(failed, f"flags video_only={vo} translate={tf} lang={lang!r}: {src}", got == want,
                        f"want {want!r}, got {got!r}")

    # no filter at all: behaves exactly like the original cog
    failed = expect(failed, "no filters should fix every tweet",
                    run_fix_links("https://x.com/b/status/2") == "https://fxtwitter.com/b/status/2")

    # language detection
    foreign = ["ja", "ko", "fr", "de", "es", "zh", "zh-cn", "zh-TW", "ar", "ru", " ja "]
    not_foreign = ["en", "EN", "en-GB", "en_US", "und", "qme", "qam", "qht", "qct", "qst", "zxx", "", None, 5]
    for lang in foreign:
        failed = expect(failed, f"is_foreign_language({lang!r}) should be True", is_foreign_language(lang))
    for lang in not_foreign:
        failed = expect(failed, f"is_foreign_language({lang!r}) should be False", not is_foreign_language(lang))

    # response parsing
    parse_cases = [
        (API_VIDEO, True), (API_GIF_AS_VIDEO, True), (API_GIF, True), (API_MIXED, True),
        (API_PHOTO, False), (API_TEXT_ONLY, False), (API_NO_FIELD, False),
        (API_NULL_FIELD, False), (API_GARBAGE, False), ({}, False),
    ]
    for data, want in parse_cases:
        failed = expect(failed, f"tweet_has_video({data!r}) should be {want}", tweet_has_video(data) == want)
    info_cases = [
        (API_PHOTO_JA, TweetInfo(False, "ja")),
        (API_VIDEO_JA, TweetInfo(True, "ja")),
        (API_VIDEO, TweetInfo(True, None)),
        ({"media_extended": [], "lang": None}, TweetInfo(False, None)),
        ({"media_extended": [], "lang": 5}, TweetInfo(False, None)),
        ({"media_extended": [], "lang": "und"}, TweetInfo(False, "und")),
    ]
    for data, want in info_cases:
        failed = expect(failed, f"tweet_info({data!r})", tweet_info(data) == want, f"got {tweet_info(data)!r}")

    # API url building
    url_cases = [
        ("https://x.com/foo/status/123", "https://api.vxtwitter.com/foo/status/123"),
        ("https://twitter.com/foo/status/123?s=20", "https://api.vxtwitter.com/foo/status/123"),
        ("https://x.com/foo/status/123/photo/1", "https://api.vxtwitter.com/foo/status/123"),
        ("https://mobile.twitter.com/Foo/status/9", "https://api.vxtwitter.com/Foo/status/9"),
        ("https://x.com/foo", None),
        ("https://example.com/foo/status/1", None),
    ]
    for url, want in url_cases:
        got = tweet_api_url(url)
        failed = expect(failed, f"tweet_api_url({url!r})", got == want, f"want {want!r}, got {got!r}")

    # extract_urls is the shared extraction used by fix_links and the lookups
    failed = expect(failed, "extract_urls should skip code blocks",
                    list(extract_urls("`https://x.com/a/status/1` https://x.com/b/status/2")) == ["https://x.com/b/status/2"])

    # the remote lookup: caching, errors, non-200, bad JSON
    api = "https://api.vxtwitter.com/a/status/1"
    cog = make_cog({api: (200, API_VIDEO_JA)})
    r1 = asyncio.run(cog.fetch_tweet_info("https://x.com/a/status/1"))
    r2 = asyncio.run(cog.fetch_tweet_info("https://x.com/a/status/1?s=20"))
    failed = expect(failed, "lookup should return the video flag and language, and be cached",
                    r1 == TweetInfo(True, "ja") and r2 == r1 and len(cog.session.calls) == 1,
                    f"{r1}, {r2}, calls={cog.session.calls}")

    cog = make_cog({"https://api.vxtwitter.com/b/status/2": (200, API_PHOTO)})
    failed = expect(failed, "photo tweet should report no video",
                    asyncio.run(cog.fetch_tweet_info("https://x.com/b/status/2")) == TweetInfo(False, None))

    failure_cases = {
        "500": (500, {}),
        "bad json": (200, ValueError("not json")),
        "not an object": (200, ["a", "list"]),
    }
    for label, resp in failure_cases.items():
        cog = make_cog({api: resp})
        got = asyncio.run(cog.fetch_tweet_info("https://x.com/a/status/1"))
        failed = expect(failed, f"lookup failure ({label}) should return None and not be cached",
                        got is None and not cog._tweet_cache, f"got {got!r}")

    cog = make_cog({})
    failed = expect(failed, "unknown tweet (404) should return None",
                    asyncio.run(cog.fetch_tweet_info("https://x.com/a/status/1")) is None)
    failed = expect(failed, "non-tweet url should return None",
                    asyncio.run(cog.fetch_tweet_info("https://example.com/")) is None)

    # lookup_tweets: every tweet link in a message
    cog = make_cog({
        "https://api.vxtwitter.com/a/status/1": (200, API_VIDEO),
        "https://api.vxtwitter.com/b/status/2": (200, API_PHOTO_JA),
    })
    got = asyncio.run(cog.lookup_tweets(
        "https://x.com/a/status/1 https://x.com/b/status/2 https://x.com/c/status/3 https://example.com/"))
    want = {"https://x.com/a/status/1": TweetInfo(True, None),
            "https://x.com/b/status/2": TweetInfo(False, "ja"),
            "https://x.com/c/status/3": None}
    failed = expect(failed, "lookup_tweets", got == want, f"want {want}, got {got}")

    # lookups per message are capped
    cog = make_cog({})
    many = " ".join(f"https://x.com/u/status/{i}" for i in range(1, 21))
    asyncio.run(cog.lookup_tweets(many))
    failed = expect(failed, "expected 5 lookups for a 20-tweet message", len(cog.session.calls) == 5,
                    f"got {len(cog.session.calls)}")

    # --- the message listener: delete vs. hide embeds, translation, no wasted lookups ---
    api_a = {"https://api.vxtwitter.com/a/status/1": (200, API_VIDEO)}
    api_b_en = {"https://api.vxtwitter.com/b/status/2": (200, {**API_PHOTO, "lang": "en"})}
    api_b_ja = {"https://api.vxtwitter.com/b/status/2": (200, API_PHOTO_JA)}

    m, c, _ = run_listener(VIDEO, api_a)
    failed = expect(failed, "video tweet: fixed link posted, original embeds hidden, not deleted",
                    len(c.sent) == 1 and "https://fxtwitter.com/a/status/1" in c.sent[0] and m.suppressed and not m.deleted,
                    f"sent={c.sent} suppressed={m.suppressed} deleted={m.deleted}")

    m, c, _ = run_listener(VIDEO, api_a, delete_original=True)
    failed = expect(failed, "delete_original: original deleted instead of hidden",
                    len(c.sent) == 1 and m.deleted and not m.suppressed,
                    f"sent={c.sent} suppressed={m.suppressed} deleted={m.deleted}")

    m, c, _ = run_listener(VIDEO, api_a, can_manage=False, delete_original=True)
    failed = expect(failed, "delete_original without Manage Messages: link still posted, nothing touched",
                    len(c.sent) == 1 and not m.deleted and not m.suppressed)

    m, c, _ = run_listener(PHOTO, api_b_en, delete_original=True)
    failed = expect(failed, "English photo tweet: nothing posted and the original is NOT deleted",
                    not c.sent and not m.deleted and not m.suppressed, f"sent={c.sent}")

    m, c, _ = run_listener(PHOTO, api_b_ja, delete_original=True)
    failed = expect(failed, "Japanese photo tweet: translated link posted and original deleted",
                    len(c.sent) == 1 and "https://vxtwitter.com/b/status/2/en" in c.sent[0] and m.deleted,
                    f"sent={c.sent} deleted={m.deleted}")

    m, c, _ = run_listener(PHOTO, api_b_ja)
    failed = expect(failed, "Japanese photo tweet without delete: embeds hidden",
                    len(c.sent) == 1 and m.suppressed and not m.deleted)

    m, c, _ = run_listener(PHOTO, api_b_ja, translate_foreign=False)
    failed = expect(failed, "translate_foreign off: Japanese photo tweet is left alone (video-only)",
                    not c.sent and not m.deleted)

    m, c, cog = run_listener(PHOTO, api_b_en, twitter_video_only=False, translate_foreign=False)
    failed = expect(failed, "both features off: every tweet fixed, and no API calls",
                    len(c.sent) == 1 and "https://fxtwitter.com/b/status/2" in c.sent[0] and not cog.session.calls,
                    f"sent={c.sent} calls={cog.session.calls}")

    m, c, _ = run_listener(VIDEO, {})
    failed = expect(failed, "lookup failure: link left alone", not c.sent and not m.deleted and not m.suppressed)

    m, c, cog = run_listener("https://www.instagram.com/p/ABC/", {}, delete_original=True)
    failed = expect(failed, "other sites: fixed and deleted as usual, with no tweet lookups",
                    len(c.sent) == 1 and "https://oginstagram.com/p/ABC" in c.sent[0] and m.deleted and not cog.session.calls,
                    f"sent={c.sent} calls={cog.session.calls}")
    return failed


def check_registry():
    problems = []
    if len(set(NAMES)) != len(NAMES):
        problems.append("duplicate link names in ALL_LINKS")
    unknown = set(DEFAULT_DISABLED_LINKS) - set(NAMES)
    if unknown:
        problems.append(f"DEFAULT_DISABLED_LINKS has names that are not links: {sorted(unknown)}")
    tested = {cs.only[0] for cs in TEST_SUITES["per-link"] if cs.only and len(cs.only) == 1}
    untested = [n for n in NAMES if n not in tested]
    if untested:
        problems.append(f"links with no per-link test: {untested}")
    for p in problems:
        print(f"FAIL [registry] {p}")
    return len(problems)


def check_performance():
    """Pathological input must not hang the bot's event loop."""
    failed = 0
    inputs = {
        "very long path, no /status/": "https://x.com/" + "a/" * 20000,
        "very long query string": "https://x.com/u/status/1?" + "a=b&" * 20000,
        "300 links in one message": " ".join(f"https://x.com/u/status/{i}" for i in range(300)),
    }
    for label, src in inputs.items():
        start = time.perf_counter()
        try:
            got = run_fix_links(src)
        except Exception as e:
            print(f"FAIL [performance] {label}: ERROR {type(e).__name__}: {e}")
            failed += 1
            continue
        elapsed = time.perf_counter() - start
        if elapsed > 2.0:
            print(f"FAIL [performance] {label}: took {elapsed:.1f}s")
            failed += 1
        if label.startswith("300") and (got is None or got.count("\n") != 299):
            print(f"FAIL [performance] {label}: expected 300 lines")
            failed += 1
    return failed


def main():
    failed = check_registry()
    total = 0
    for name, cases in TEST_SUITES.items():
        total += len(cases)
        failed += run_suite(name, cases)
    total += len(TWITTER_FILTER_TESTS)
    failed += run_twitter_suite()
    failed += check_performance()
    print(f"\n{total} cases in {len(TEST_SUITES) + 1} suites, plus registry and performance checks: "
          f"{'all passed' if not failed else f'{failed} FAILED'}")

    print("\nTODO fix bugs:")
    for label, src in KNOWN_BUGS:
        print(f"  {label}\n     {src!r} -> {run_fix_links(src)!r}")
    return failed


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
