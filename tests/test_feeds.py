import pytest

from auto_rss_sorting.feeds import html_to_text


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p>Hello <b>world</b></p>", "Hello world"),
        ('<a href="https://example.com">link</a>, then text', "link, then text"),
        ("<p>First</p><p>Second</p>", "First Second"),
        ("one<br>two<br/>three", "one two three"),
        ("<ul><li>a</li><li>b</li></ul>", "a b"),
    ],
)
def test_removes_tags(html: str, expected: str) -> None:
    assert html_to_text(html) == expected


def test_unescapes_entities() -> None:
    assert html_to_text("Tom &amp; Jerry, caf&eacute; &#8217;") == "Tom & Jerry, café ’"


def test_collapses_whitespace() -> None:
    assert html_to_text("  <p>a\n\n  b\t c</p>  ") == "a b c"


def test_drops_script_and_style_content() -> None:
    html = "<style>p { color: red }</style>Text<script>alert(1)</script>"
    assert html_to_text(html) == "Text"


def test_plain_text_is_unchanged() -> None:
    assert html_to_text("Just plain text.") == "Just plain text."


def test_empty_string() -> None:
    assert html_to_text("") == ""
