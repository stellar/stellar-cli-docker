import pytest

from lib import git_remote


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
