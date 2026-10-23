import pytest

from auto_rss_sorting.candidates import normalize_url


def test_lowercases_scheme_and_host_but_not_path() -> None:
    assert (
        normalize_url("HTTPS://Example.COM/Blog/Post")
        == "https://example.com/Blog/Post"
    )


@pytest.mark.parametrize(
    "param", ["utm_source=rss", "utm_medium=feed", "fbclid=abc", "gclid=xyz"]
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
