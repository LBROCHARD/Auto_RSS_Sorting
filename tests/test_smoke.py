import pytest

from auto_rss_sorting import main


def test_main_runs(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    assert capsys.readouterr().out == "Hello from auto-rss-sorting!\n"
