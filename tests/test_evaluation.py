from pathlib import Path

import pytest

from auto_rss_sorting.evaluation import Label, load_labels
from auto_rss_sorting.inputs import InputError

HEADER = "url,title,description,score\n"


def write_labels(tmp_path: Path, content: str) -> Path:
    path = tmp_path / "labels.csv"
    path.write_text(content, encoding="utf-8")
    return path


def test_valid_labels_load_in_file_order(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path,
        HEADER
        + 'https://example.com/rust,Rust 2.0,"New release, with async",9\n'
        + "https://example.com/vide,Article sans description,,0\n",
    )

    labels = load_labels(path)

    assert [str(label.url) for label in labels] == [
        "https://example.com/rust",
        "https://example.com/vide",
    ]
    assert labels[0] == Label(
        url="https://example.com/rust",
        title="Rust 2.0",
        description="New release, with async",
        score=9,
    )
    assert labels[1].description == ""
    assert labels[1].score == 0


def test_byte_order_mark_is_ignored(tmp_path: Path) -> None:
    # Excel writes a BOM at the start of UTF-8 CSV files.
    path = write_labels(tmp_path, "﻿" + HEADER + "https://example.com/a,A,,5\n")

    assert len(load_labels(path)) == 1


def test_missing_labels_file(tmp_path: Path) -> None:
    with pytest.raises(InputError, match=r"labels\.csv.*not found"):
        load_labels(tmp_path / "labels.csv")


@pytest.mark.parametrize(
    "header",
    ["", "url,title,score\n", "url,title,description,score,extra\n"],
)
def test_wrong_header(tmp_path: Path, header: str) -> None:
    path = write_labels(tmp_path, header)

    with pytest.raises(
        InputError, match=r"labels\.csv: .*header.*url,title,description,score"
    ):
        load_labels(path)


def test_header_only(tmp_path: Path) -> None:
    path = write_labels(tmp_path, HEADER)

    with pytest.raises(InputError, match=r"labels\.csv: .*no label"):
        load_labels(path)


@pytest.mark.parametrize("score", ["11", "-1", "7.5", "abc", ""])
def test_invalid_score(tmp_path: Path, score: str) -> None:
    path = write_labels(tmp_path, HEADER + f"https://example.com/a,A title,,{score}\n")

    with pytest.raises(InputError, match=r"labels\.csv: line 2: score: "):
        load_labels(path)


def test_empty_title(tmp_path: Path) -> None:
    path = write_labels(tmp_path, HEADER + "https://example.com/a,  ,,5\n")

    with pytest.raises(InputError, match=r"labels\.csv: line 2: title: "):
        load_labels(path)


@pytest.mark.parametrize("url", ["not a url", "ftp://example.com/a"])
def test_invalid_url(tmp_path: Path, url: str) -> None:
    path = write_labels(tmp_path, HEADER + f"{url},A title,,5\n")

    with pytest.raises(InputError, match=r"labels\.csv: line 2: url: "):
        load_labels(path)


def test_row_with_missing_fields(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path, HEADER + "https://example.com/a,A title,,5\nhttps://example.com/b\n"
    )

    with pytest.raises(InputError, match=r"labels\.csv: line 3: .*4 fields"):
        load_labels(path)


def test_duplicate_url_after_normalization(tmp_path: Path) -> None:
    path = write_labels(
        tmp_path,
        HEADER
        + "https://example.com/a,First,,5\n"
        + "HTTPS://Example.com/a/?utm_source=rss,Same article,,6\n",
    )

    with pytest.raises(
        InputError, match=r"labels\.csv: line 3: duplicate URL.*example\.com/a"
    ):
        load_labels(path)
