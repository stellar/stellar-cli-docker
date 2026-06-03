import pytest

import newest_pair


def test_newest_cli_returns_highest_semver(multi_cli_builds: dict) -> None:
    assert newest_pair.newest_cli(multi_cli_builds) == "26.0.0"


def test_newest_cli_ignores_array_order() -> None:
    data = {
        "stellar_cli_versions": [
            {"version": "26.1.0", "ref": "a" * 40, "rust_versions": ["1.94.0-slim-trixie"]},
            {"version": "25.1.0", "ref": "b" * 40, "rust_versions": ["1.94.0-slim-trixie"]},
            {"version": "26.0.0", "ref": "c" * 40, "rust_versions": ["1.94.0-slim-trixie"]},
        ]
    }
    assert newest_pair.newest_cli(data) == "26.1.0"


def test_newest_cli_handles_two_digit_minor() -> None:
    data = {
        "stellar_cli_versions": [
            {"version": "1.100.0", "ref": "a" * 40, "rust_versions": ["1.94.0-slim-trixie"]},
            {"version": "1.99.0", "ref": "b" * 40, "rust_versions": ["1.94.0-slim-trixie"]},
        ]
    }
    assert newest_pair.newest_cli(data) == "1.100.0"


def test_newest_cli_empty_versions_raises() -> None:
    with pytest.raises(ValueError, match="no stellar_cli_versions"):
        newest_pair.newest_cli({"stellar_cli_versions": []})


def test_main_cli_mode(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(newest_pair.builds, "load", lambda: multi_cli_builds)
    assert newest_pair.main(["--stellar-cli-version"]) == 0
    assert capsys.readouterr().out == "26.0.0\n"


def test_main_rust_mode(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(newest_pair.builds, "load", lambda: multi_cli_builds)
    assert newest_pair.main(["--rust-version"]) == 0
    assert capsys.readouterr().out == "1.94.0-slim-trixie\n"


def test_main_requires_one_mode() -> None:
    with pytest.raises(SystemExit):
        newest_pair.main([])


def test_main_rejects_both_modes() -> None:
    with pytest.raises(SystemExit):
        newest_pair.main(["--stellar-cli-version", "--rust-version"])
