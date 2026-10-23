"""Turn fetched articles into candidates: normalized ids, age filter, dedup."""

from urllib.parse import urlsplit, urlunsplit

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
