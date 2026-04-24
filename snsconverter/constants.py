import enum
import re

KEY_ENABLED = "enabled"
DEFAULT_GUILD = {KEY_ENABLED: False}

INSTA_REGEX_PATTERN = re.compile(r"https?://(?:www\.)?instagram\.com")
TWITTER_REGEX_PATTERN = re.compile(r"https://(?:www\.)?(twitter\.com|x\.com)")

class SocialMedia(enum.Enum):
    INSTAGRAM = "Instagram"
    TWITTER = "Twitter"
