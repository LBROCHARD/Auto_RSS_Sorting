"""Keyword pre-filter and the deterministic ranking rule."""

import re
import unicodedata
from dataclasses import dataclass

from auto_rss_sorting.feeds import Article

WORD_CHAR = re.compile(r"\w")


@dataclass(frozen=True)
class KeywordPattern:
    keyword: str
    weight: int
    pattern: re.Pattern[str]


def normalize_text(text: str) -> str:
    """Normalize both keywords and article text so they compare the same way:
    precomposed accents (NFC) and plain apostrophes."""
    return unicodedata.normalize("NFC", text).replace("’", "'")


def compile_keywords(keywords: dict[str, int]) -> list[KeywordPattern]:
    """Compile one case-insensitive, whole-word pattern per keyword, in file order."""
    return [
        KeywordPattern(keyword, weight, _keyword_pattern(normalize_text(keyword)))
        for keyword, weight in keywords.items()
    ]


def _keyword_pattern(keyword: str) -> re.Pattern[str]:
    # Any run of whitespace inside a phrase matches, since descriptions come from HTML.
    body = r"\s+".join(re.escape(part) for part in keyword.split())
    # A word boundary only makes sense on an edge that is a word character:
    # "c++" must match "C++20", where a plain \b after "+" would fail.
    if WORD_CHAR.match(keyword[0]):
        body = r"(?<!\w)" + body
    if WORD_CHAR.match(keyword[-1]):
        body += r"(?!\w)"
    return re.compile(body, re.IGNORECASE)


def keyword_score(article: Article, patterns: list[KeywordPattern]) -> int:
    """Sum of the weights of the keywords found in the title and description,
    each keyword counted once."""
    # The space keeps the last word of the title apart from the first word of
    # the description.
    text = normalize_text(f"{article.title} {article.description}")
    return sum(p.weight for p in patterns if p.pattern.search(text))
