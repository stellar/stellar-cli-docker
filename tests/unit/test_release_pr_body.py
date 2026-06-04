import pytest

import release_pr_body


def _compose(version="26.0.0", release_tag="v26.0.0"):
    return release_pr_body.compose(
        version=version,
        release_tag=release_tag,
        actor="alice",
        repo="stellar/stellar-cli-docker",
        run_url="https://github.com/stellar/stellar-cli-docker/actions/runs/123",
        default_branch="main",
    )


def test_new_release_title_and_body() -> None:
    title, body = _compose()
    assert title == "Release stellar-cli 26.0.0"
    assert "new release" in body
    assert "@alice" in body
    assert "release/v26.0.0" in body


def test_refresh_title_and_body() -> None:
    title, body = _compose(release_tag="v26.0.0-1")
    assert title == "Refresh stellar-cli 26.0.0 (26.0.0-1)"
    assert "refresh" in body
    assert "release/v26.0.0-1" in body


def test_body_describes_mutable_publish_behavior() -> None:
    _, body = _compose()
    # Tags are mutable now — the body must not claim pairs are skipped/immutable.
    assert "skipped" not in body
    assert "immutable" not in body
    assert "mutable" in body


def test_body_carries_release_url_with_correct_target() -> None:
    _, body = _compose()
    assert "https://github.com/stellar/stellar-cli-docker/releases/new" in body
    assert "tag=v26.0.0" in body
    assert "target=main" in body


def test_main_prints_title(capsys: pytest.CaptureFixture[str]) -> None:
    rc = release_pr_body.main(
        [
            "--stellar-cli-version",
            "26.0.0",
            "--release-tag",
            "v26.0.0",
            "--actor",
            "alice",
            "--repo",
            "stellar/stellar-cli-docker",
            "--run-url",
            "https://example.com/run",
            "--default-branch",
            "main",
            "--field",
            "title",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out == "Release stellar-cli 26.0.0"


def test_main_prints_body_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    rc = release_pr_body.main(
        [
            "--stellar-cli-version",
            "26.0.0",
            "--release-tag",
            "v26.0.0",
            "--actor",
            "alice",
            "--repo",
            "stellar/stellar-cli-docker",
            "--run-url",
            "https://example.com/run",
            "--default-branch",
            "main",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("### What")
