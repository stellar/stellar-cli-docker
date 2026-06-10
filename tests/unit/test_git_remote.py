import pytest

from lib import git_remote


def test_ls_remote_pins_end_of_options(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[list[str]] = []
    monkeypatch.setattr(git_remote.runner, "capture", lambda cmd: captured.append(cmd) or "")
    git_remote.ls_remote("https://example.com/repo.git", "refs/tags/v26.0.0")
    cmd = captured[0]
    # --end-of-options must sit before the (untrusted) URL and refspecs so git
    # can't reinterpret them as flags.
    assert "--end-of-options" in cmd
    assert cmd.index("--end-of-options") < cmd.index("https://example.com/repo.git")


def test_ls_remote_rejects_option_like_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_remote.runner, "capture", lambda *_: pytest.fail("ran git"))
    with pytest.raises(ValueError, match="must not begin with '-'"):
        git_remote.ls_remote("--upload-pack=touch /tmp/x", "refs/tags/v1")


def test_ls_remote_rejects_option_like_refspec(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_remote.runner, "capture", lambda *_: pytest.fail("ran git"))
    with pytest.raises(ValueError, match="must not begin with '-'"):
        git_remote.ls_remote("https://example.com/repo.git", "--exec=evil")


def test_resolve_tag_commit_prefers_peeled_annotated(monkeypatch: pytest.MonkeyPatch) -> None:
    output = (
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/tags/v26.0.0\n"
        "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\trefs/tags/v26.0.0^{}\n"
    )
    monkeypatch.setattr(git_remote, "ls_remote", lambda *_: output)
    assert git_remote.resolve_tag_commit("https://example.com/repo.git", "v26.0.0") == "b" * 40


def test_resolve_tag_commit_falls_back_to_lightweight(monkeypatch: pytest.MonkeyPatch) -> None:
    output = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/tags/v26.0.0\n"
    monkeypatch.setattr(git_remote, "ls_remote", lambda *_: output)
    assert git_remote.resolve_tag_commit("https://example.com/repo.git", "v26.0.0") == "a" * 40


def test_resolve_tag_commit_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(git_remote, "ls_remote", lambda *_: "")
    assert git_remote.resolve_tag_commit("https://example.com/repo.git", "v99.99.99") is None


def test_resolve_tag_commit_ignores_unrelated_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    output = (
        "cccccccccccccccccccccccccccccccccccccccc\trefs/heads/main\n"
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\trefs/tags/v26.0.0\n"
    )
    monkeypatch.setattr(git_remote, "ls_remote", lambda *_: output)
    assert git_remote.resolve_tag_commit("https://example.com/repo.git", "v26.0.0") == "a" * 40
