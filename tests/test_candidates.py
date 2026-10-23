from datetime import UTC, datetime, timedelta

import pytest

from auto_rss_sorting.candidates import collect_candidates, normalize_url
from auto_rss_sorting.feeds import Article


def test_lowercases_scheme_and_host_but_not_path() -> None:
    assert (
        normalize_url("HTTPS://Example.COM/Blog/Post")
        == "https://example.com/Blog/Post"
    )


@pytest.mark.parametrize(
    "param",
    [
        "utm_source=rss",
        "utm_medium=feed",
        "fbclid=abc",
        "gclid=xyz",
        "UTM_Source=rss",
        "FBCLID=abc",
    ],
)
def test_removes_tracking_parameter(param: str) -> None:
    assert normalize_url(f"https://example.com/post?{param}") == (
        "https://example.com/post"
    )


def test_keeps_other_parameters_in_order() -> None:
    url = "https://example.com/post?b=2&utm_campaign=x&a=1&empty="
    assert normalize_url(url) == "https://example.com/post?b=2&a=1&empty="


def test_removes_fragment() -> None:
    assert normalize_url("https://example.com/post#comments") == (
        "https://example.com/post"
    )


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://example.com/", "https://example.com"),
        ("https://example.com/blog/post/", "https://example.com/blog/post"),
        ("https://example.com/post/?a=1", "https://example.com/post?a=1"),
    ],
)
def test_removes_trailing_slash(url: str, expected: str) -> None:
    assert normalize_url(url) == expected


def test_normalized_url_is_unchanged() -> None:
    url = "https://example.com/blog/post?id=3"
    assert normalize_url(url) == url


def test_variants_of_one_url_give_the_same_id() -> None:
    variants = [
        "https://example.com/post",
        "HTTPS://EXAMPLE.com/post/",
        "https://example.com/post?utm_source=rss&fbclid=abc",
        "https://example.com/post/#top",
    ]
    assert {normalize_url(url) for url in variants} == {"https://example.com/post"}


NOW = datetime(2026, 10, 20, 6, 0, tzinfo=UTC)
MAX_AGE_DAYS = 7


def article(
    url: str, published_at: datetime = NOW - timedelta(days=1), source: str = "feed"
) -> Article:
    return Article(
        id=normalize_url(url),
        url=url,
        title="Title",
        description="Description",
        published_at=published_at,
        source=source,
    )


def candidate_ids(articles: list[Article]) -> list[str]:
    return [a.id for a in collect_candidates(articles, NOW, MAX_AGE_DAYS)]


def test_excludes_articles_older_than_max_age() -> None:
    old = article("https://example.com/old", NOW - timedelta(days=MAX_AGE_DAYS + 1))
    recent = article("https://example.com/recent")

    assert candidate_ids([old, recent]) == ["https://example.com/recent"]


def test_keeps_article_exactly_on_the_age_boundary() -> None:
    boundary = article("https://example.com/b", NOW - timedelta(days=MAX_AGE_DAYS))
    just_older = article(
        "https://example.com/o", NOW - timedelta(days=MAX_AGE_DAYS, seconds=1)
    )

    assert candidate_ids([boundary, just_older]) == ["https://example.com/b"]


def test_keeps_article_dated_in_the_future() -> None:
    future = article("https://example.com/future", NOW + timedelta(hours=2))

    assert candidate_ids([future]) == ["https://example.com/future"]


def test_duplicate_across_feeds_keeps_the_first_feed() -> None:
    first = article("https://example.com/post", source="first")
    second = article("https://example.com/post", source="second")

    candidates = collect_candidates([first, second], NOW, MAX_AGE_DAYS)

    assert [a.source for a in candidates] == ["first"]


def test_url_variants_are_deduplicated() -> None:
    articles = [
        article("https://example.com/post"),
        article("https://Example.com/post/?utm_source=rss"),
        article("https://example.com/post#comments"),
    ]

    assert candidate_ids(articles) == ["https://example.com/post"]


def test_keeps_input_order() -> None:
    articles = [
        article("https://example.com/c", NOW - timedelta(days=3)),
        article("https://example.com/a", NOW - timedelta(days=1)),
        article("https://example.com/b", NOW - timedelta(days=2)),
    ]

    assert candidate_ids(articles) == [
        "https://example.com/c",
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_no_articles_gives_no_candidates() -> None:
    assert candidate_ids([]) == []
