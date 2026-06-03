import hashlib
from pathlib import Path

import pytest

from lib import common


def test_log_writes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    common.log("hello")
    captured = capsys.readouterr()
    assert captured.err == "hello\n"
    assert captured.out == ""


def test_err_prefixes_with_error(capsys: pytest.CaptureFixture[str]) -> None:
    common.err("boom")
    captured = capsys.readouterr()
    assert captured.err == "error: boom\n"
    assert captured.out == ""


def test_die_exits_with_code_1(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        common.die("fatal")
    assert exc_info.value.code == 1
    assert "error: fatal" in capsys.readouterr().err


def test_repo_root_points_to_repo() -> None:
    assert (common.repo_root() / "builds.json").exists()


def test_require_cmd_passes_for_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common.shutil, "which", lambda c: "/usr/bin/" + c)
    common.require_cmd("ls", "git")  # no exception


def test_require_cmd_dies_for_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(common.shutil, "which", lambda _: None)
    with pytest.raises(SystemExit):
        common.require_cmd("nonexistent")


def test_preflight_sha256_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    # The `sha256` pseudo-token is always satisfied — hashlib is stdlib.
    monkeypatch.setattr(common.shutil, "which", lambda _: None)
    common.preflight_checks(["sha256"])  # no exception


def test_preflight_routes_literal_tokens_to_require_cmd(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(common, "require_cmd", lambda *args: calls.append(args))
    common.preflight_checks(["docker", "git"])
    assert calls == [("docker", "git")]


def test_preflight_routes_buildx_token(monkeypatch: pytest.MonkeyPatch) -> None:
    called = []
    monkeypatch.setattr(common, "require_buildx", lambda: called.append(True))
    common.preflight_checks(["buildx"])
    assert called == [True]


def test_step_summary_appends_when_env_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    common.step_summary("first")
    common.step_summary("second")
    assert summary.read_text() == "first\nsecond\n"


def test_step_summary_noop_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    common.step_summary("ignored")  # no exception, nothing written


def test_sha256_of_matches_hashlib(tmp_path: Path) -> None:
    f = tmp_path / "blob"
    f.write_bytes(b"hello world")
    assert common.sha256_of(f) == hashlib.sha256(b"hello world").hexdigest()


def test_sha256_of_streams_large_files(tmp_path: Path) -> None:
    f = tmp_path / "big"
    payload = b"x" * (256 * 1024)
    f.write_bytes(payload)
    assert common.sha256_of(f) == hashlib.sha256(payload).hexdigest()
