"""Turn fetched articles into candidates: normalized ids, age filter, dedup."""

from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

# Type hints only: feeds.py imports normalize_url from this module.
if TYPE_CHECKING:
    from auto_rss_sorting.feeds import Article

TRACKING_PARAMETERS = {"fbclid", "gclid"}
TRACKING_PREFIX = "utm_"


def normalize_url(url: str) -> str:
    """Return the article id: lowercase scheme and host, no tracking parameters,
    no fragment, no trailing slash."""
    parts = urlsplit(url)
    # Filter the raw query instead of parsing and re-encoding it, so the
    # remaining parameters keep their exact original spelling.
    query = "&".join(
        pair for pair in parts.query.split("&") if pair and not _is_tracking(pair)
    )
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            query,
            "",
        )
    )


def _is_tracking(pair: str) -> bool:
    name = pair.split("=", 1)[0]
    return name in TRACKING_PARAMETERS or name.startswith(TRACKING_PREFIX)


def collect_candidates(
    articles: list[Article], now: datetime, max_age_days: int
) -> list[Article]:
    """Keep articles published within `max_age_days` of `now`, first occurrence
    of each id only (feeds are in feeds.yaml order), in input order."""
    oldest = now - timedelta(days=max_age_days)
    seen: set[str] = set()
    candidates: list[Article] = []
    for article in articles:
        if article.published_at < oldest or article.id in seen:
            continue
        seen.add(article.id)
        candidates.append(article)
    return candidates
