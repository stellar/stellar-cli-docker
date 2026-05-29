import json
from pathlib import Path

import pytest

import refresh_stellar_cli_digests
from lib import builds


@pytest.fixture
def staged_builds(tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "builds.json"
    target.write_text((fixtures_dir / "builds_unpinned_refs.json").read_text())
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    return target


def test_unpinned_versions_finds_blank() -> None:
    data = {
        "stellar_cli_versions": [
            {"version": "1.0.0", "ref": "a" * 40, "rust_versions": []},
            {"version": "1.1.0", "ref": "", "rust_versions": []},
            {"version": "1.2.0", "ref": "not-a-sha", "rust_versions": []},
        ]
    }
    assert refresh_stellar_cli_digests.unpinned_versions(data) == ["1.1.0", "1.2.0"]


def test_main_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch, staged_builds: Path) -> None:
    monkeypatch.setattr(refresh_stellar_cli_digests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(
        refresh_stellar_cli_digests.git_remote,
        "resolve_tag_commit",
        lambda repo, tag: "f" * 40,
    )
    before = staged_builds.read_text()
    assert refresh_stellar_cli_digests.main(["--dry-run"]) == 0
    assert staged_builds.read_text() == before


def test_main_fills_blanks_only(monkeypatch: pytest.MonkeyPatch, staged_builds: Path) -> None:
    monkeypatch.setattr(refresh_stellar_cli_digests.common, "preflight_checks", lambda _: None)
    expected = "f" * 40
    monkeypatch.setattr(
        refresh_stellar_cli_digests.git_remote,
        "resolve_tag_commit",
        lambda repo, tag: expected,
    )
    assert refresh_stellar_cli_digests.main([]) == 0
    data = json.loads(staged_builds.read_text())
    entries = {entry["version"]: entry["ref"] for entry in data["stellar_cli_versions"]}
    assert entries["26.0.0"] == expected
    assert entries["26.1.0"] == "1228cff8022b804659750b94b315932b0e0f3f6a"


def test_main_explicit_version_refreshes_pinned(
    monkeypatch: pytest.MonkeyPatch, staged_builds: Path
) -> None:
    monkeypatch.setattr(refresh_stellar_cli_digests.common, "preflight_checks", lambda _: None)
    new_sha = "9" * 40
    monkeypatch.setattr(
        refresh_stellar_cli_digests.git_remote,
        "resolve_tag_commit",
        lambda repo, tag: new_sha,
    )
    assert refresh_stellar_cli_digests.main(["--stellar-cli-version", "26.1.0"]) == 0
    data = json.loads(staged_builds.read_text())
    entries = {entry["version"]: entry["ref"] for entry in data["stellar_cli_versions"]}
    assert entries["26.1.0"] == new_sha
    # 26.0.0 was blank but we didn't ask for it; leave it.
    assert entries["26.0.0"] == ""


def test_main_unknown_version_dies(monkeypatch: pytest.MonkeyPatch, staged_builds: Path) -> None:
    monkeypatch.setattr(refresh_stellar_cli_digests.common, "preflight_checks", lambda _: None)
    with pytest.raises(SystemExit):
        refresh_stellar_cli_digests.main(["--stellar-cli-version", "99.0.0"])


def test_main_unresolvable_tag_dies(monkeypatch: pytest.MonkeyPatch, staged_builds: Path) -> None:
    monkeypatch.setattr(refresh_stellar_cli_digests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(
        refresh_stellar_cli_digests.git_remote,
        "resolve_tag_commit",
        lambda repo, tag: None,
    )
    with pytest.raises(SystemExit):
        refresh_stellar_cli_digests.main([])


def test_main_all_pinned_is_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fixtures_dir: Path
) -> None:
    target = tmp_path / "builds.json"
    target.write_text((fixtures_dir / "builds_minimal.json").read_text())
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    monkeypatch.setattr(refresh_stellar_cli_digests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(
        refresh_stellar_cli_digests.git_remote,
        "resolve_tag_commit",
        lambda *_: pytest.fail("should not query git when nothing needs refresh"),
    )
    before = target.read_text()
    assert refresh_stellar_cli_digests.main([]) == 0
    assert target.read_text() == before
