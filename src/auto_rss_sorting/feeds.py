"""Fetch the feeds and parse them into articles."""

from html.parser import HTMLParser

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
