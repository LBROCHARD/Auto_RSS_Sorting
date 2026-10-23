"""Fetch the feeds and parse them into articles."""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from time import struct_time
from typing import Any

import feedparser
import httpx

from auto_rss_sorting.candidates import normalize_url
from auto_rss_sorting.inputs import Feed

logger = logging.getLogger(__name__)

FEED_TIMEOUT_SECONDS = 10
USER_AGENT = "auto-rss-sorting (+https://github.com/LBROCHARD/auto-rss-sorting)"

# Tags that separate blocks of text: a space is inserted around them so that
# "<p>a</p><p>b</p>" gives "a b". Inline tags (<b>, <a>...) add nothing.
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt",
    "figcaption", "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6",
    "header", "hr", "li", "ol", "p", "pre", "section", "table", "td", "th",
    "tr", "ul",
}  # fmt: skip
SKIPPED_TAGS = {"script", "style"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIPPED_TAGS:
            self.skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.chunks.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIPPED_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in BLOCK_TAGS:
            self.chunks.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.chunks.append(data)


def html_to_text(html: str) -> str:
    """Return the text of an HTML fragment, entities unescaped, whitespace collapsed."""
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    return " ".join("".join(extractor.chunks).split())


class FeedError(Exception):
    """One feed could not be fetched or parsed. The message names the feed."""


@dataclass(frozen=True)
class Article:
    id: str
    url: str
    title: str
    description: str
    published_at: datetime
    source: str


@dataclass(frozen=True)
class ParsedFeed:
    articles: list[Article]
    undated_count: int


def parse_feed(feed: Feed, content: bytes) -> ParsedFeed:
    """Parse a feed document into articles. Entries without any date are counted,
    entries without a link are skipped."""
    parsed = feedparser.parse(content)
    if parsed.bozo:
        if not parsed.entries:
            raise FeedError(f"{feed.name}: invalid feed: {parsed.bozo_exception}")
        logger.warning(
            "%s: malformed feed, keeping its %d readable entries: %s",
            feed.name,
            len(parsed.entries),
            parsed.bozo_exception,
        )

    articles: list[Article] = []
    undated_count = 0
    for entry in parsed.entries:
        title = " ".join(entry.get("title", "").split())
        link = entry.get("link")
        if not link:
            logger.warning("%s: skipping entry without link: %r", feed.name, title)
            continue
        published_at = _entry_date(entry)
        if published_at is None:
            undated_count += 1
            continue
        articles.append(
            Article(
                id=normalize_url(link),
                url=link,
                title=title,
                description=html_to_text(entry.get("summary", "")),
                published_at=published_at,
                source=feed.name,
            )
        )
    return ParsedFeed(articles=articles, undated_count=undated_count)


def _entry_date(entry: Any) -> datetime | None:
    """Return the publication date, else the update date, in UTC."""
    # feedparser gives these dates as struct_time already converted to UTC.
    parsed: struct_time | None = entry.get("published_parsed") or entry.get(
        "updated_parsed"
    )
    if parsed is None:
        return None
    return datetime(*parsed[:6], tzinfo=UTC)


@dataclass(frozen=True)
class FetchResult:
    articles: list[Article]
    failed_feeds: list[str]
    undated_count: int


def make_http_client() -> httpx.Client:
    """The client used to fetch every feed. httpx does not follow redirects by default."""
    return httpx.Client(
        timeout=FEED_TIMEOUT_SECONDS,
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def fetch_feed(client: httpx.Client, feed: Feed) -> bytes:
    """Download a feed. Raw bytes are returned so feedparser handles the encoding."""
    try:
        response = client.get(str(feed.url))
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise FeedError(f"{feed.name}: cannot fetch {feed.url}: {error}") from error
    return response.content


def fetch_all(client: httpx.Client, feeds: list[Feed]) -> FetchResult:
    """Fetch and parse every feed in order. A failing feed is logged and skipped."""
    articles: list[Article] = []
    failed_feeds: list[str] = []
    undated_count = 0
    for feed in feeds:
        try:
            parsed = parse_feed(feed, fetch_feed(client, feed))
        except FeedError as error:
            logger.warning("skipping feed: %s", error)
            failed_feeds.append(feed.name)
            continue
        articles.extend(parsed.articles)
        undated_count += parsed.undated_count
    return FetchResult(
        articles=articles, failed_feeds=failed_feeds, undated_count=undated_count
    )
