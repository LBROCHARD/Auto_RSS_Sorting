from pathlib import Path

import pytest

from auto_rss_sorting.inputs import (
    Config,
    InputError,
    load_config,
    load_feeds,
    load_inputs,
    load_keywords,
    load_profile,
)

VALID_CONFIG = """\
top_n: 10
max_age_days: 7
llm_max_articles: 50
max_description_chars: 2000
provider: some-provider
model: some-model
price_input_per_mtok: 0.25
price_output_per_mtok: 1.25
"""


def write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def config_with(line: str) -> str:
    """Return VALID_CONFIG with the line of the same key replaced by `line`."""
    key = line.split(":")[0]
    lines = [
        line if row.startswith(f"{key}:") else row for row in VALID_CONFIG.splitlines()
    ]
    return "\n".join(lines) + "\n"


def test_valid_config_loads(tmp_path: Path) -> None:
    config = load_config(write(tmp_path, "config.yaml", VALID_CONFIG))

    assert config == Config(
        top_n=10,
        max_age_days=7,
        llm_max_articles=50,
        max_description_chars=2000,
        provider="some-provider",
        model="some-model",
        price_input_per_mtok=0.25,
        price_output_per_mtok=1.25,
    )


def test_missing_config_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"config\.yaml.*not found"):
        load_config(tmp_path / "config.yaml")


def test_config_yaml_syntax_error(tmp_path: Path) -> None:
    path = write(tmp_path, "config.yaml", "top_n: [10\n")

    with pytest.raises(InputError, match=r"config\.yaml.*invalid YAML"):
        load_config(path)


def test_config_root_not_a_mapping(tmp_path: Path) -> None:
    path = write(tmp_path, "config.yaml", "- top_n\n- 10\n")

    with pytest.raises(InputError, match=r"config\.yaml.*mapping"):
        load_config(path)


def test_empty_config_file(tmp_path: Path) -> None:
    path = write(tmp_path, "config.yaml", "")

    with pytest.raises(InputError, match=r"config\.yaml.*mapping"):
        load_config(path)


def test_config_missing_field(tmp_path: Path) -> None:
    content = VALID_CONFIG.replace("top_n: 10\n", "")
    path = write(tmp_path, "config.yaml", content)

    with pytest.raises(InputError, match=r"config\.yaml: top_n: Field required"):
        load_config(path)


def test_config_unknown_field(tmp_path: Path) -> None:
    path = write(tmp_path, "config.yaml", VALID_CONFIG + "top-n: 10\n")

    with pytest.raises(
        InputError, match=r"config\.yaml: top-n: Extra inputs are not permitted"
    ):
        load_config(path)


@pytest.mark.parametrize(
    "line",
    ["top_n: 0", "max_age_days: -1", "llm_max_articles: 0", "max_description_chars: 0"],
)
def test_config_non_positive_int(tmp_path: Path, line: str) -> None:
    key = line.split(":")[0]
    path = write(tmp_path, "config.yaml", config_with(line))

    with pytest.raises(
        InputError, match=rf"config\.yaml: {key}: Input should be greater than 0"
    ):
        load_config(path)


def test_config_non_integer_value(tmp_path: Path) -> None:
    path = write(tmp_path, "config.yaml", config_with("top_n: ten"))

    with pytest.raises(
        InputError, match=r"config\.yaml: top_n: Input should be a valid integer"
    ):
        load_config(path)


@pytest.mark.parametrize(
    "line", ["price_input_per_mtok: -1", "price_output_per_mtok: -0.5"]
)
def test_config_negative_price(tmp_path: Path, line: str) -> None:
    key = line.split(":")[0]
    path = write(tmp_path, "config.yaml", config_with(line))

    with pytest.raises(
        InputError,
        match=rf"config\.yaml: {key}: Input should be greater than or equal to 0",
    ):
        load_config(path)


@pytest.mark.parametrize("line", ['provider: ""', 'model: "  "'])
def test_config_empty_provider_or_model(tmp_path: Path, line: str) -> None:
    key = line.split(":")[0]
    path = write(tmp_path, "config.yaml", config_with(line))

    with pytest.raises(InputError, match=rf"config\.yaml: {key}: "):
        load_config(path)


def test_config_reports_every_error(tmp_path: Path) -> None:
    content = config_with("top_n: 0").replace("model: some-model\n", "")
    path = write(tmp_path, "config.yaml", content)

    with pytest.raises(InputError) as error:
        load_config(path)

    assert "top_n" in str(error.value)
    assert "model" in str(error.value)


VALID_FEEDS = """\
feeds:
  - name: First Blog
    url: https://first.example/feed.xml
  - name: Second Blog
    url: http://second.example/rss
"""


def test_valid_feeds_load(tmp_path: Path) -> None:
    feeds = load_feeds(write(tmp_path, "feeds.yaml", VALID_FEEDS))

    assert [(feed.name, str(feed.url)) for feed in feeds] == [
        ("First Blog", "https://first.example/feed.xml"),
        ("Second Blog", "http://second.example/rss"),
    ]


def test_missing_feeds_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"feeds\.yaml.*not found"):
        load_feeds(tmp_path / "feeds.yaml")


def test_feeds_key_missing(tmp_path: Path) -> None:
    path = write(tmp_path, "feeds.yaml", "sources: []\n")

    with pytest.raises(InputError, match=r"feeds\.yaml: feeds: Field required"):
        load_feeds(path)


def test_empty_feed_list(tmp_path: Path) -> None:
    path = write(tmp_path, "feeds.yaml", "feeds: []\n")

    with pytest.raises(InputError, match=r"feeds\.yaml: feeds: .*at least 1 item"):
        load_feeds(path)


def test_feed_missing_name(tmp_path: Path) -> None:
    content = "feeds:\n  - url: https://first.example/feed.xml\n"
    path = write(tmp_path, "feeds.yaml", content)

    with pytest.raises(
        InputError, match=r"feeds\.yaml: feeds\.0\.name: Field required"
    ):
        load_feeds(path)


def test_feed_empty_name(tmp_path: Path) -> None:
    content = 'feeds:\n  - name: "  "\n    url: https://first.example/feed.xml\n'
    path = write(tmp_path, "feeds.yaml", content)

    with pytest.raises(InputError, match=r"feeds\.yaml: feeds\.0\.name: "):
        load_feeds(path)


@pytest.mark.parametrize("url", ["not a url", "ftp://first.example/feed.xml"])
def test_feed_invalid_url(tmp_path: Path, url: str) -> None:
    content = f"feeds:\n  - name: First Blog\n    url: {url}\n"
    path = write(tmp_path, "feeds.yaml", content)

    with pytest.raises(InputError, match=r"feeds\.yaml: feeds\.0\.url: "):
        load_feeds(path)


def test_duplicate_feed_name(tmp_path: Path) -> None:
    content = VALID_FEEDS.replace("Second Blog", "First Blog")
    path = write(tmp_path, "feeds.yaml", content)

    with pytest.raises(
        InputError, match=r"feeds\.yaml: feeds: .*duplicate feed name.*First Blog"
    ):
        load_feeds(path)


def test_duplicate_feed_url(tmp_path: Path) -> None:
    content = VALID_FEEDS.replace(
        "http://second.example/rss", "https://first.example/feed.xml"
    )
    path = write(tmp_path, "feeds.yaml", content)

    with pytest.raises(
        InputError,
        match=r"feeds\.yaml: feeds: .*duplicate feed URL.*https://first\.example/feed\.xml",
    ):
        load_feeds(path)


VALID_KEYWORDS = """\
keywords:
  rust: 3
  machine learning: 2
  crypto: -5
"""


def test_valid_keywords_load(tmp_path: Path) -> None:
    keywords = load_keywords(write(tmp_path, "keywords.yaml", VALID_KEYWORDS))

    assert keywords == {"rust": 3, "machine learning": 2, "crypto": -5}


def test_missing_keywords_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"keywords\.yaml.*not found"):
        load_keywords(tmp_path / "keywords.yaml")


def test_keywords_key_missing(tmp_path: Path) -> None:
    path = write(tmp_path, "keywords.yaml", "rust: 3\n")

    with pytest.raises(InputError, match=r"keywords\.yaml: keywords: Field required"):
        load_keywords(path)


def test_empty_keyword_mapping(tmp_path: Path) -> None:
    path = write(tmp_path, "keywords.yaml", "keywords: {}\n")

    with pytest.raises(
        InputError, match=r"keywords\.yaml: keywords: .*at least 1 item"
    ):
        load_keywords(path)


@pytest.mark.parametrize("weight", ["2.5", "high", "true"])
def test_keyword_weight_not_an_integer(tmp_path: Path, weight: str) -> None:
    path = write(tmp_path, "keywords.yaml", f"keywords:\n  rust: {weight}\n")

    with pytest.raises(InputError, match=r"keywords\.yaml: keywords\.rust: .*integer"):
        load_keywords(path)


def test_empty_keyword(tmp_path: Path) -> None:
    path = write(tmp_path, "keywords.yaml", 'keywords:\n  "  ": 3\n')

    with pytest.raises(
        InputError, match=r"keywords\.yaml: keywords\..*at least 1 character"
    ):
        load_keywords(path)


def test_duplicate_keyword_ignoring_case(tmp_path: Path) -> None:
    path = write(tmp_path, "keywords.yaml", "keywords:\n  Rust: 3\n  rust: 2\n")

    with pytest.raises(
        InputError, match=r"keywords\.yaml: keywords: .*duplicate keyword.*rust"
    ):
        load_keywords(path)


REPO_ROOT = Path(__file__).parent.parent


def test_valid_profile_loads(tmp_path: Path) -> None:
    path = write(tmp_path, "profile.md", "# Reader profile\n\nLikes Rust.\n")

    assert load_profile(path) == "# Reader profile\n\nLikes Rust.\n"


def test_missing_profile(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"profile\.md.*not found"):
        load_profile(tmp_path / "profile.md")


@pytest.mark.parametrize("content", ["", "  \n\n"])
def test_empty_profile(tmp_path: Path, content: str) -> None:
    path = write(tmp_path, "profile.md", content)

    with pytest.raises(InputError, match=r"profile\.md.*empty"):
        load_profile(path)


def write_all_inputs(tmp_path: Path) -> None:
    write(tmp_path, "config.yaml", VALID_CONFIG)
    write(tmp_path, "feeds.yaml", VALID_FEEDS)
    write(tmp_path, "keywords.yaml", VALID_KEYWORDS)
    write(tmp_path, "profile.md", "Likes Rust.\n")


def test_load_inputs_returns_every_input(tmp_path: Path) -> None:
    write_all_inputs(tmp_path)

    inputs = load_inputs(tmp_path)

    assert inputs.config.top_n == 10
    assert [feed.name for feed in inputs.feeds] == ["First Blog", "Second Blog"]
    assert inputs.keywords == {"rust": 3, "machine learning": 2, "crypto": -5}
    assert inputs.profile == "Likes Rust.\n"


@pytest.mark.parametrize(
    "name", ["config.yaml", "feeds.yaml", "keywords.yaml", "profile.md"]
)
def test_load_inputs_fails_on_missing_file(tmp_path: Path, name: str) -> None:
    write_all_inputs(tmp_path)
    (tmp_path / name).unlink()

    with pytest.raises(InputError, match=rf"{name.replace('.', r'\.')}.*not found"):
        load_inputs(tmp_path)


def test_committed_inputs_are_valid() -> None:
    load_inputs(REPO_ROOT)
