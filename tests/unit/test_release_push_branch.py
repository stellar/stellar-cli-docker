import subprocess
from unittest.mock import MagicMock

import pytest

import release_push_branch


def _completed(returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout="")


def test_fresh_push_when_remote_branch_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = MagicMock(return_value=_completed())
    monkeypatch.setattr(release_push_branch.runner, "run", captured)
    monkeypatch.setattr(release_push_branch, "remote_branch_exists", lambda _: False)
    monkeypatch.setattr(
        release_push_branch.gh_cli, "open_pr_for_branch", lambda *_: pytest.fail("not called")
    )

    assert release_push_branch.commit_and_push("v26.0.0", "foo/bar") == 0
    # Last call should be the plain push (no --force).
    last = captured.call_args_list[-1][0][0]
    assert last == ["git", "push", "origin", "release/v26.0.0"]


def test_orphan_branch_force_pushes(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = MagicMock(return_value=_completed())
    monkeypatch.setattr(release_push_branch.runner, "run", captured)
    monkeypatch.setattr(release_push_branch, "remote_branch_exists", lambda _: True)
    monkeypatch.setattr(release_push_branch.gh_cli, "open_pr_for_branch", lambda *_: None)

    assert release_push_branch.commit_and_push("v26.0.0", "foo/bar") == 0
    last = captured.call_args_list[-1][0][0]
    assert last == ["git", "push", "--force", "origin", "release/v26.0.0"]


def test_branch_with_open_pr_aborts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = MagicMock(return_value=_completed())
    monkeypatch.setattr(release_push_branch.runner, "run", captured)
    monkeypatch.setattr(release_push_branch, "remote_branch_exists", lambda _: True)
    monkeypatch.setattr(release_push_branch.gh_cli, "open_pr_for_branch", lambda *_: 42)

    assert release_push_branch.commit_and_push("v26.0.0", "foo/bar") == 1
    # Push must not have been called.
    pushed = any(call[0][0][:2] == ["git", "push"] for call in captured.call_args_list)
    assert not pushed
    assert "open PR (#42)" in capsys.readouterr().err


def test_gh_failure_aborts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured = MagicMock(return_value=_completed())
    monkeypatch.setattr(release_push_branch.runner, "run", captured)
    monkeypatch.setattr(release_push_branch, "remote_branch_exists", lambda _: True)

    def fail(*_):
        raise RuntimeError("gh exploded")

    monkeypatch.setattr(release_push_branch.gh_cli, "open_pr_for_branch", fail)

    assert release_push_branch.commit_and_push("v26.0.0", "foo/bar") == 1
    assert "refusing to push" in capsys.readouterr().err
