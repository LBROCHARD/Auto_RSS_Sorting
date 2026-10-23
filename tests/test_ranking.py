from datetime import UTC, datetime

import pytest

from auto_rss_sorting.feeds import Article
from auto_rss_sorting.ranking import compile_keywords, keyword_score

DATE = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def make_article(
    title: str = "",
    description: str = "",
    id: str = "https://example.com/a",
    published_at: datetime = DATE,
) -> Article:
    return Article(
        id=id,
        url=id,
        title=title,
        description=description,
        published_at=published_at,
        source="Example",
    )


def score(keywords: dict[str, int], title: str = "", description: str = "") -> int:
    return keyword_score(make_article(title, description), compile_keywords(keywords))


@pytest.mark.parametrize("text", ["Rust 2.0 is out", "Why RUST?", "rust."])
def test_matches_whole_word_case_insensitive(text: str) -> None:
    assert score({"rust": 3}, title=text) == 3


@pytest.mark.parametrize("text", ["We trust you", "rusty nails", "Rust_lang"])
def test_does_not_match_inside_a_word(text: str) -> None:
    assert score({"rust": 3}, title=text) == 0


@pytest.mark.parametrize("text", ["New data center", "a data\ncenter", "DATA  Center"])
def test_matches_phrase_across_whitespace(text: str) -> None:
    assert score({"data center": 2}, description=text) == 2


@pytest.mark.parametrize(
    ("text", "expected"), [("C++", 1), ("C++20 modules", 1), ("abc++", 0)]
)
def test_matches_keyword_ending_with_symbol(text: str, expected: int) -> None:
    assert score({"c++": 1}, title=text) == expected


@pytest.mark.parametrize(
    ("text", "expected"), [("A Post-Mortem", 2), ("post-mortems", 0)]
)
def test_matches_hyphenated_keyword(text: str, expected: int) -> None:
    assert score({"post-mortem": 2}, title=text) == expected


def test_matches_accented_keyword_in_decomposed_form() -> None:
    decomposed = "L'énergie des serveurs"
    assert score({"énergie": 2}, title="Énergie") == 2
    assert score({"énergie": 2}, title=decomposed) == 2


def test_matches_typographic_apostrophe() -> None:
    assert score({"retour d'expérience": 2}, title="Un retour d’expérience") == 2


def test_matches_in_title_and_description() -> None:
    keywords = {"rust": 3, "wasm": 3}
    assert score(keywords, title="Rust", description="and wasm") == 6


def test_title_and_description_are_separate_words() -> None:
    assert score({"rust": 3}, title="Learn", description="Rust today") == 3


def test_repeated_keyword_counts_once() -> None:
    assert score({"rust": 3}, title="Rust", description="rust rust rust") == 3


def test_overlapping_keywords_both_count() -> None:
    assert score({"coding agent": 3, "agent": 2}, title="A coding agent") == 5


def test_negative_weights_are_summed() -> None:
    keywords = {"rust": 3, "crypto": -5, "nft": -5}
    assert score(keywords, title="Rust crypto NFT") == -7


def test_no_keyword_found_scores_zero() -> None:
    assert score({"rust": 3}, title="Nothing here", description="") == 0
