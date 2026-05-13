"""
Unified data schemas for the social media sentiment time series dataset.

All raw data from Twitter/Reddit/Threads (across 4 JSON format variants)
is normalized into these dataclasses before any downstream processing.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib


@dataclass
class UnifiedPost:
    """A single social media post (main post or reply/retweet), normalized."""

    post_id: str                        # unique identifier
    platform: str                       # "twitter" | "reddit" | "threads"
    event: str                          # standardized event name
    text: str                           # post body text
    post_time: Optional[datetime]       # parsed datetime (tz-naive)
    user_id: str                        # author identifier
    like_count: int = 0
    reply_count: int = 0                # API-reported reply count
    retweet_count: int = 0              # API-reported retweet count
    post_url: str = ""
    title: str = ""                     # Reddit post title (empty for other platforms)
    source_file: str = ""               # traceability: raw JSON filename
    source_dir: str = ""                # which data directory (data1..data12)
    is_main_post: bool = True           # True for main posts, False for replies/retweets

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "post_id": self.post_id,
            "platform": self.platform,
            "event": self.event,
            "text": self.text,
            "post_time": self.post_time.isoformat() if self.post_time else "",
            "user_id": self.user_id,
            "like_count": self.like_count,
            "reply_count": self.reply_count,
            "retweet_count": self.retweet_count,
            "post_url": self.post_url,
            "title": self.title,
            "source_file": self.source_file,
            "source_dir": self.source_dir,
            "is_main_post": self.is_main_post,
        }


@dataclass
class UnifiedInteraction:
    """An edge in the interaction graph (reply or retweet relationship)."""

    source_post_id: str                 # the reply/retweet post
    target_post_id: str                 # the post being replied to / retweeted
    interaction_type: str               # "reply" | "retweet" | "quote" | "comment"
    source_time: Optional[datetime]     # when the reply/retweet was made
    target_time: Optional[datetime]     # when the original post was made
    source_user_id: str = ""
    target_user_id: str = ""

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "source_post_id": self.source_post_id,
            "target_post_id": self.target_post_id,
            "interaction_type": self.interaction_type,
            "source_time": self.source_time.isoformat() if self.source_time else "",
            "target_time": self.target_time.isoformat() if self.target_time else "",
            "source_user_id": self.source_user_id,
            "target_user_id": self.target_user_id,
        }


@dataclass
class SentimentRecord:
    """Post-level sentiment annotation from LLM."""

    post_id: str
    text: str
    post_time: Optional[datetime]
    user_id: str
    event: str
    platform: str
    sentiment: str                      # "positive" | "neutral" | "negative"
    sentiment_score: float = 0.0        # +1, 0, -1

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        return {
            "post_id": self.post_id,
            "text": self.text,
            "post_time": self.post_time.isoformat() if self.post_time else "",
            "user_id": self.user_id,
            "event": self.event,
            "platform": self.platform,
            "sentiment": self.sentiment,
            "sentiment_score": self.sentiment_score,
        }


def generate_post_id(post_url: str = "", platform: str = "",
                     user_id: str = "", post_time: str = "",
                     text: str = "") -> str:
    """Generate a deterministic unique post ID.

    Uses post_url if available (most reliable), otherwise falls back
    to a hash of (platform, user_id, post_time, text[:200]).

    Args:
        post_url: Direct URL to the post (preferred).
        platform: Platform name.
        user_id: Author identifier.
        post_time: Timestamp string.
        text: Post text content.

    Returns:
        A deterministic string ID.
    """
    if post_url:
        return hashlib.md5(post_url.encode("utf-8")).hexdigest()

    key = f"{platform}|{user_id}|{post_time}|{text[:200]}"
    return hashlib.md5(key.encode("utf-8")).hexdigest()
