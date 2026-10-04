"""URL helpers for the France24Whitelist cog.

Nothing in this module imports Discord or Red, so it can be unit-tested on its own.
"""
from __future__ import annotations

import re
from typing import List, Optional
from urllib.parse import urlsplit

#: Only these hosts count as "France 24 links". Other subdomains
#: (media.france24.com, s.france24.com, ...) serve images/assets and are left alone.
HOSTS = frozenset({"france24.com", "www.france24.com"})

#: An allowed URL *path* must match this. Regular English article URLs look like
#: /en/europe/20261004-some-headline
#: Shows (/en/tv-shows/...), clips (/en/video/...) and newscast items (/en/some-headline)
#: do not match, so they are blocked.
DEFAULT_PATTERN = (
    r"^/en/(?:asia-pacific|europe|africa|middle-east|americas|france)/\d{8}-"
)

IGNORE = "ignore"  # not a France 24 link -> never touched
ALLOW = "allow"  # France 24 link that matches the whitelist
BLOCK = "block"  # France 24 link that does not match the whitelist

_URL_RE = re.compile(r"https?://[^\s<>\"\[\]()]+", re.IGNORECASE)
# Links typed without a scheme, e.g. "france24.com/en/video/..." (Discord auto-links these).
# The lookbehind skips "static.france24.com", "x@france24.com" and "https://france24.com";
# the lookahead skips "france24.company" and "france24.com.evil.io".
_BARE_RE = re.compile(
    r"(?<![\w./@-])((?:www\.)?france24\.com(?!\w|-|\.\w)(?:/[^\s<>\"\[\]()]*)?)",
    re.IGNORECASE,
)
_TRAILING = ".,;:!?'*_~|"


def compile_pattern(pattern: str) -> re.Pattern:
    """Compile an admin-supplied pattern (raises ``re.error`` if invalid)."""
    return re.compile(pattern, re.IGNORECASE)


def find_urls(text: Optional[str]) -> List[str]:
    """Return every URL-looking string in ``text`` (trailing punctuation removed)."""
    if not text:
        return []
    found = [m.rstrip(_TRAILING) for m in _URL_RE.findall(text)]
    found += ["https://" + m.rstrip(_TRAILING) for m in _BARE_RE.findall(text)]
    return found


def france24_path(url: str) -> Optional[str]:
    """Return the URL path if ``url`` points at France 24, otherwise ``None``."""
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
    except ValueError:
        return None
    if host not in HOSTS:
        return None
    return parts.path or "/"


def classify(url: str, pattern: re.Pattern) -> str:
    """Return IGNORE, ALLOW or BLOCK for a single URL."""
    path = france24_path(url)
    if path is None:
        return IGNORE
    return ALLOW if pattern.match(path) else BLOCK
