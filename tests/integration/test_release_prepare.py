import json
import urllib.error
from pathlib import Path

import pytest

import release_prepare
from lib import builds


@pytest.fixture
def staged_minimal(tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "builds.json"
    target.write_text((fixtures_dir / "builds_minimal.json").read_text())
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    return target


def test_current_rust_base_suffix_uses_default_distro(multi_cli_builds: dict) -> None:
    assert release_prepare.current_rust_base_suffix(multi_cli_builds) == "slim-trixie"


def test_current_rust_base_suffix_dies_without_default(multi_cli_builds: dict) -> None:
    data = {**multi_cli_builds}
    del data["default_distro"]
    with pytest.raises(ValueError, match="missing default_distro"):
        release_prepare.current_rust_base_suffix(data)


def test_pick_default_rust_base_keys_keeps_two_minors(
    monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    payload = json.loads((fixtures_dir / "rust_hub_tags.json").read_text())
    monkeypatch.setattr(release_prepare.runner, "http_get_json", lambda _: payload)
    keys = release_prepare.pick_default_rust_base_keys("slim-trixie")
    # 1.94.1 wins over 1.94.0 for the 1.94 minor; 1.95.0 wins for 1.95.
    assert keys == ["1.94.1-slim-trixie", "1.95.0-slim-trixie"]


def test_pick_default_rust_base_keys_rejects_wrong_suffix(
    monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    payload = json.loads((fixtures_dir / "rust_hub_tags.json").read_text())
    monkeypatch.setattr(release_prepare.runner, "http_get_json", lambda _: payload)
    keys = release_prepare.pick_default_rust_base_keys("slim-bookworm")
    assert keys == ["1.94.0-slim-bookworm"]


def test_add_cli_entry_appends_and_stubs_digests(minimal_builds: dict) -> None:
    release_prepare.add_cli_entry(minimal_builds, "27.0.0", ["1.95.0-slim-trixie"])
    versions = [e["version"] for e in minimal_builds["stellar_cli_versions"]]
    assert "27.0.0" in versions
    assert versions == sorted(versions)
    # Stub digest was added (so refresh has something to fill).
    assert "1.95.0-slim-trixie" in minimal_builds["rust_image_digests"]


def test_extend_cli_entry_unions_and_sorts(minimal_builds: dict) -> None:
    release_prepare.extend_cli_entry(
        minimal_builds, "26.0.0", ["1.94.0-slim-trixie", "1.95.0-slim-trixie"]
    )
    entry = builds.find_cli(minimal_builds, "26.0.0")
    assert entry is not None
    assert entry["rust_versions"] == ["1.94.0-slim-trixie", "1.95.0-slim-trixie"]


def test_extend_cli_entry_rejects_unknown_cli(minimal_builds: dict) -> None:
    with pytest.raises(ValueError, match="unknown"):
        release_prepare.extend_cli_entry(minimal_builds, "99.0.0", ["1.95.0-slim-trixie"])


def test_pick_release_tag_no_prior_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_prepare.gh_cli, "list_release_tags", lambda _: [])
    assert release_prepare.pick_release_tag("26.0.0", "foo/bar") == "v26.0.0"


def test_pick_release_tag_first_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_prepare.gh_cli, "list_release_tags", lambda _: ["v26.0.0"])
    assert release_prepare.pick_release_tag("26.0.0", "foo/bar") == "v26.0.0-1"


def test_pick_release_tag_increments_existing_iteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        release_prepare.gh_cli,
        "list_release_tags",
        lambda _: ["v26.0.0", "v26.0.0-1", "v26.0.0-2"],
    )
    assert release_prepare.pick_release_tag("26.0.0", "foo/bar") == "v26.0.0-3"


def test_pick_release_tag_ignores_other_clis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        release_prepare.gh_cli,
        "list_release_tags",
        lambda _: ["v25.1.0-3", "v27.0.0"],
    )
    assert release_prepare.pick_release_tag("26.0.0", "foo/bar") == "v26.0.0"


def test_main_new_release_writes_entry_and_emits_tag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    staged_minimal: Path,
) -> None:
    monkeypatch.setattr(release_prepare.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(release_prepare.gh_cli, "list_release_tags", lambda _: [])
    # Stub the downstream subscripts so we don't hit the network.
    monkeypatch.setattr(release_prepare.refresh_stellar_cli_digests, "main", lambda _: 0)

    def fake_rust_refresh(_argv):
        data = builds.load()
        for key in data["rust_image_digests"]:
            if not data["rust_image_digests"][key]:
                data["rust_image_digests"][key] = "sha256:" + "f" * 64
        # Backfill a ref so validate_json passes.
        for entry in data["stellar_cli_versions"]:
            if not entry["ref"]:
                entry["ref"] = "a" * 40
        builds.dump(data)
        return 0

    monkeypatch.setattr(release_prepare.refresh_rust_digests, "main", fake_rust_refresh)
    monkeypatch.setattr(release_prepare.validate_json, "main", lambda _: 0)

    rc = release_prepare.main(
        [
            "--stellar-cli-version",
            "27.0.0",
            "--rust-versions",
            "1.95.0-slim-trixie",
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out == "v27.0.0\n"
    data = json.loads(staged_minimal.read_text())
    versions = [e["version"] for e in data["stellar_cli_versions"]]
    assert "27.0.0" in versions


def test_main_dies_cleanly_on_network_failure(
    monkeypatch: pytest.MonkeyPatch, staged_minimal: Path
) -> None:
    monkeypatch.setattr(release_prepare.common, "preflight_checks", lambda _: None)

    def boom(_url):
        raise urllib.error.URLError("name resolution failed")

    # No --rust-versions, so the auto-pick hits Docker Hub and raises.
    monkeypatch.setattr(release_prepare.runner, "http_get_json", boom)
    with pytest.raises(SystemExit):
        release_prepare.main(["--stellar-cli-version", "27.0.0"])


def test_main_dies_when_nothing_changes(
    monkeypatch: pytest.MonkeyPatch, staged_minimal: Path
) -> None:
    monkeypatch.setattr(release_prepare.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(release_prepare.gh_cli, "list_release_tags", lambda _: [])
    monkeypatch.setattr(release_prepare.refresh_stellar_cli_digests, "main", lambda _: 0)
    monkeypatch.setattr(release_prepare.refresh_rust_digests, "main", lambda _: 0)
    monkeypatch.setattr(release_prepare.validate_json, "main", lambda _: 0)

    with pytest.raises(SystemExit):
        release_prepare.main(
            [
                "--stellar-cli-version",
                "26.0.0",
                "--rust-versions",
                "1.94.0-slim-trixie",
            ]
        )
