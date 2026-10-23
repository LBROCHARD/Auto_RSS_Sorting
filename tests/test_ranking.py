from datetime import UTC, datetime, timedelta

import pytest

from auto_rss_sorting.feeds import Article
from auto_rss_sorting.llm import LLMScore
from auto_rss_sorting.ranking import (
    compile_keywords,
    keyword_score,
    prefilter,
    ranking_key,
    top_articles,
)

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


def ids(articles: list[Article]) -> list[str]:
    return [article.id for article in articles]


def test_ranking_key_sorts_by_score_then_date_then_id() -> None:
    older = DATE - timedelta(days=1)
    articles = [
        make_article(id="https://b.com", published_at=older),  # score 5
        make_article(id="https://z.com", published_at=DATE),  # score 5
        make_article(id="https://a.com", published_at=older),  # score 5
        make_article(id="https://c.com", published_at=older),  # score 9
    ]
    scores = {
        "https://a.com": 5,
        "https://b.com": 5,
        "https://c.com": 9,
        "https://z.com": 5,
    }

    ranked = sorted(articles, key=lambda a: ranking_key(scores[a.id], a))

    assert ids(ranked) == [
        "https://c.com",  # highest score
        "https://z.com",  # same score, most recent
        "https://a.com",  # same score and date: alphabetical id
        "https://b.com",
    ]


PATTERNS = compile_keywords({"rust": 3, "wasm": 2, "crypto": -5})

# f.com comes before e.com in input order but ties with it: the id decides.
ARTICLES = [
    make_article("Rust and wasm", id="https://a.com"),  # 5
    make_article("Crypto news", id="https://b.com"),  # -5
    make_article("Rust too", id="https://f.com"),  # 3
    make_article("Wasm", id="https://c.com"),  # 2
    make_article("Nothing", id="https://d.com"),  # 0
    make_article("Rust", id="https://e.com"),  # 3
]


def test_prefilter_keeps_the_best_up_to_limit() -> None:
    kept = prefilter(ARTICLES, PATTERNS, limit=3)
    assert ids(kept) == ["https://a.com", "https://e.com", "https://f.com"]


def test_prefilter_keeps_all_when_fewer_than_limit() -> None:
    kept = prefilter(ARTICLES, PATTERNS, limit=50)
    assert ids(kept) == [
        "https://a.com",
        "https://e.com",
        "https://f.com",
        "https://c.com",
        "https://d.com",
        "https://b.com",  # negative score: ranked last, but not excluded
    ]


def test_prefilter_does_not_depend_on_input_order() -> None:
    forward = prefilter(ARTICLES, PATTERNS, limit=50)
    backward = prefilter(list(reversed(ARTICLES)), PATTERNS, limit=50)
    assert ids(forward) == ids(backward)


def test_prefilter_with_no_candidates_returns_empty() -> None:
    assert prefilter([], PATTERNS, limit=50) == []


def llm_score(value: int) -> LLMScore:
    return LLMScore(score=value, summary="A summary.", reason="A reason.")


OLDER = DATE - timedelta(days=1)

# Ties on the LLM score are broken by date (desc), then by id.
SCORED = [
    (make_article(id="https://b.com", published_at=OLDER), llm_score(7)),
    (make_article(id="https://a.com", published_at=OLDER), llm_score(7)),
    (make_article(id="https://c.com", published_at=OLDER), llm_score(9)),
    (make_article(id="https://d.com", published_at=DATE), llm_score(7)),
    (make_article(id="https://e.com", published_at=DATE), llm_score(2)),
]


def top_ids(ranked: list[tuple[Article, LLMScore]]) -> list[str]:
    return [article.id for article, _ in ranked]


def test_top_articles_sorts_by_llm_score_with_tie_breaks() -> None:
    ranked = top_articles(SCORED, top_n=10)
    assert top_ids(ranked) == [
        "https://c.com",  # highest score
        "https://d.com",  # score 7, most recent
        "https://a.com",  # score 7, same date: alphabetical id
        "https://b.com",
        "https://e.com",  # fewer than top_n: all kept
    ]


def test_top_articles_keeps_top_n() -> None:
    ranked = top_articles(SCORED, top_n=2)
    assert top_ids(ranked) == ["https://c.com", "https://d.com"]


def test_top_articles_does_not_depend_on_input_order() -> None:
    forward = top_articles(SCORED, top_n=10)
    backward = top_articles(list(reversed(SCORED)), top_n=10)
    assert top_ids(forward) == top_ids(backward)


def test_top_articles_with_no_scored_article_returns_empty() -> None:
    assert top_articles([], top_n=10) == []
