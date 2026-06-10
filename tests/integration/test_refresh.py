import json
from pathlib import Path

import pytest

import refresh
from lib import builds

DIGEST_94 = "sha256:f7bf1c266d9e48c8d724733fd97ba60464c44b743eb4f46f935577d3242d81d0"
OLD_94 = f"1.94.0-slim-trixie@{DIGEST_94}"


@pytest.fixture
def staged_minimal(tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "builds.json"
    target.write_text((fixtures_dir / "builds_minimal.json").read_text())
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    return target


@pytest.fixture
def staged_unpinned_refs(
    tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    target = tmp_path / "builds.json"
    target.write_text((fixtures_dir / "builds_unpinned_refs.json").read_text())
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    return target


def _no_git(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(refresh.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(
        refresh.git_remote,
        "resolve_tag_commit",
        lambda *_: pytest.fail("should not query git when ref is already pinned"),
    )


def test_current_rust_base_suffix_uses_default_distro(multi_cli_builds: dict) -> None:
    assert refresh.current_rust_base_suffix(multi_cli_builds) == "slim-trixie"


def test_current_rust_base_suffix_dies_without_default(multi_cli_builds: dict) -> None:
    data = {**multi_cli_builds}
    del data["default_distro"]
    with pytest.raises(ValueError, match="missing default_distro"):
        refresh.current_rust_base_suffix(data)


def test_pick_default_rust_base_keys_keeps_two_minors(
    monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    payload = json.loads((fixtures_dir / "rust_hub_tags.json").read_text())
    monkeypatch.setattr(refresh.runner, "http_get_json", lambda _: payload)
    keys = refresh.pick_default_rust_base_keys("slim-trixie")
    assert keys == ["1.94.1-slim-trixie", "1.95.0-slim-trixie"]


def test_pick_default_rust_base_keys_rejects_wrong_suffix(
    monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    payload = json.loads((fixtures_dir / "rust_hub_tags.json").read_text())
    monkeypatch.setattr(refresh.runner, "http_get_json", lambda _: payload)
    keys = refresh.pick_default_rust_base_keys("slim-bookworm")
    assert keys == ["1.94.0-slim-bookworm"]


def test_appends_new_label_pin(monkeypatch: pytest.MonkeyPatch, staged_minimal: Path) -> None:
    _no_git(monkeypatch)
    new_digest = "sha256:" + "e" * 64
    monkeypatch.setattr(refresh.docker_inspect, "index_digest", lambda ref: new_digest)

    rc = refresh.main(["--stellar-cli-version", "26.0.0", "--rust-versions", "1.95.0-slim-trixie"])
    assert rc == 0
    entry = builds.find_cli(json.loads(staged_minimal.read_text()), "26.0.0")
    assert entry["rust_versions"] == [OLD_94, f"1.95.0-slim-trixie@{new_digest}"]


def test_appends_new_digest_for_same_label(
    monkeypatch: pytest.MonkeyPatch, staged_minimal: Path
) -> None:
    # A rebuilt base: same label, fresh digest → a new pin, old pin retained.
    _no_git(monkeypatch)
    new_digest = "sha256:" + "9" * 64
    monkeypatch.setattr(refresh.docker_inspect, "index_digest", lambda ref: new_digest)

    rc = refresh.main(["--stellar-cli-version", "26.0.0", "--rust-versions", "1.94.0-slim-trixie"])
    assert rc == 0
    entry = builds.find_cli(json.loads(staged_minimal.read_text()), "26.0.0")
    assert entry["rust_versions"] == [OLD_94, f"1.94.0-slim-trixie@{new_digest}"]


def test_existing_pin_is_noop(monkeypatch: pytest.MonkeyPatch, staged_minimal: Path) -> None:
    _no_git(monkeypatch)
    # Upstream still serves the same digest already on file.
    monkeypatch.setattr(refresh.docker_inspect, "index_digest", lambda ref: DIGEST_94)
    before = staged_minimal.read_text()
    assert (
        refresh.main(["--stellar-cli-version", "26.0.0", "--rust-versions", "1.94.0-slim-trixie"])
        == 0
    )
    assert staged_minimal.read_text() == before


def test_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch, staged_minimal: Path) -> None:
    _no_git(monkeypatch)
    monkeypatch.setattr(refresh.docker_inspect, "index_digest", lambda ref: "sha256:" + "a" * 64)
    before = staged_minimal.read_text()
    assert (
        refresh.main(
            [
                "--stellar-cli-version",
                "26.0.0",
                "--rust-versions",
                "1.95.0-slim-trixie",
                "--dry-run",
            ]
        )
        == 0
    )
    assert staged_minimal.read_text() == before


def test_resolves_blank_ref(monkeypatch: pytest.MonkeyPatch, staged_unpinned_refs: Path) -> None:
    monkeypatch.setattr(refresh.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(refresh.git_remote, "resolve_tag_commit", lambda repo, tag: "a" * 40)
    monkeypatch.setattr(
        refresh.docker_inspect,
        "index_digest",
        lambda ref: DIGEST_94,
    )
    assert (
        refresh.main(["--stellar-cli-version", "26.0.0", "--rust-versions", "1.94.0-slim-trixie"])
        == 0
    )
    entry = builds.find_cli(json.loads(staged_unpinned_refs.read_text()), "26.0.0")
    assert entry["ref"] == "a" * 40


def test_creates_new_cli_entry(monkeypatch: pytest.MonkeyPatch, staged_minimal: Path) -> None:
    monkeypatch.setattr(refresh.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(refresh.git_remote, "resolve_tag_commit", lambda repo, tag: "c" * 40)
    new_digest = "sha256:" + "d" * 64
    monkeypatch.setattr(refresh.docker_inspect, "index_digest", lambda ref: new_digest)

    assert (
        refresh.main(["--stellar-cli-version", "27.0.0", "--rust-versions", "1.95.0-slim-trixie"])
        == 0
    )
    data = json.loads(staged_minimal.read_text())
    entry = builds.find_cli(data, "27.0.0")
    assert entry["ref"] == "c" * 40
    assert entry["rust_versions"] == [f"1.95.0-slim-trixie@{new_digest}"]
    # Versions stay sorted.
    assert [e["version"] for e in data["stellar_cli_versions"]] == ["26.0.0", "27.0.0"]


def test_malformed_builds_dies_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # A malformed builds.json must route through common.die() (SystemExit),
    # not surface a raw JSONDecodeError from builds.load().
    target = tmp_path / "builds.json"
    target.write_text("{ this is not valid json")
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    monkeypatch.setattr(refresh.common, "preflight_checks", lambda _: None)
    with pytest.raises(SystemExit):
        refresh.main(["--stellar-cli-version", "26.0.0", "--rust-versions", "1.94.0-slim-trixie"])


def test_unresolvable_tag_dies(monkeypatch: pytest.MonkeyPatch, staged_minimal: Path) -> None:
    monkeypatch.setattr(refresh.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(refresh.git_remote, "resolve_tag_commit", lambda repo, tag: None)
    monkeypatch.setattr(refresh.docker_inspect, "index_digest", lambda ref: "sha256:" + "a" * 64)
    with pytest.raises(SystemExit):
        refresh.main(["--stellar-cli-version", "27.0.0", "--rust-versions", "1.95.0-slim-trixie"])


def test_auto_picks_when_no_rust_versions(
    monkeypatch: pytest.MonkeyPatch, staged_minimal: Path, fixtures_dir: Path
) -> None:
    _no_git(monkeypatch)
    payload = json.loads((fixtures_dir / "rust_hub_tags.json").read_text())
    monkeypatch.setattr(refresh.runner, "http_get_json", lambda _: payload)
    monkeypatch.setattr(refresh.docker_inspect, "index_digest", lambda ref: "sha256:" + "a" * 64)

    assert refresh.main(["--stellar-cli-version", "26.0.0"]) == 0
    entry = builds.find_cli(json.loads(staged_minimal.read_text()), "26.0.0")
    labels = [builds.label_of(p) for p in entry["rust_versions"]]
    assert "1.94.1-slim-trixie" in labels
    assert "1.95.0-slim-trixie" in labels
