import json
from pathlib import Path

import pytest

import refresh_rust_digests
from lib import builds


@pytest.fixture
def staged_builds(tmp_path: Path, fixtures_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "builds.json"
    target.write_text((fixtures_dir / "builds_unpinned.json").read_text())
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    return target


def test_unpinned_keys_finds_blank_value() -> None:
    data = {
        "rust_image_digests": {
            "ok": "sha256:" + "a" * 64,
            "blank": "",
            "partial": "sha256:",
            "bogus": "not-a-digest",
        }
    }
    assert set(refresh_rust_digests.unpinned_keys(data)) == {"blank", "partial", "bogus"}


def test_main_dry_run_does_not_write(monkeypatch: pytest.MonkeyPatch, staged_builds: Path) -> None:
    monkeypatch.setattr(refresh_rust_digests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(
        refresh_rust_digests.docker_inspect,
        "index_digest",
        lambda ref: "sha256:" + "f" * 64,
    )
    before = staged_builds.read_text()
    assert refresh_rust_digests.main(["--dry-run"]) == 0
    assert staged_builds.read_text() == before


def test_main_fills_blanks_only(monkeypatch: pytest.MonkeyPatch, staged_builds: Path) -> None:
    monkeypatch.setattr(refresh_rust_digests.common, "preflight_checks", lambda _: None)
    expected = "sha256:" + "f" * 64
    monkeypatch.setattr(
        refresh_rust_digests.docker_inspect,
        "index_digest",
        lambda ref: expected,
    )
    assert refresh_rust_digests.main([]) == 0
    data = json.loads(staged_builds.read_text())
    assert data["rust_image_digests"]["1.94.0-slim-trixie"] == expected
    # Already-pinned entry is untouched.
    assert data["rust_image_digests"]["1.95.0-slim-trixie"].endswith("f340c3c1e24da6880141f7c0")


def test_main_explicit_key_refreshes_pinned(
    monkeypatch: pytest.MonkeyPatch, staged_builds: Path
) -> None:
    monkeypatch.setattr(refresh_rust_digests.common, "preflight_checks", lambda _: None)
    new_digest = "sha256:" + "9" * 64
    monkeypatch.setattr(
        refresh_rust_digests.docker_inspect,
        "index_digest",
        lambda ref: new_digest,
    )
    assert refresh_rust_digests.main(["--rust-version", "1.95.0-slim-trixie"]) == 0
    data = json.loads(staged_builds.read_text())
    assert data["rust_image_digests"]["1.95.0-slim-trixie"] == new_digest
    # Blank entry was not touched (we only refreshed the explicit key).
    assert data["rust_image_digests"]["1.94.0-slim-trixie"] == ""


def test_main_unknown_key_dies(monkeypatch: pytest.MonkeyPatch, staged_builds: Path) -> None:
    monkeypatch.setattr(refresh_rust_digests.common, "preflight_checks", lambda _: None)
    with pytest.raises(SystemExit):
        refresh_rust_digests.main(["--rust-version", "1.99.0-slim-bookworm"])


def test_main_all_pinned_is_noop(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fixtures_dir: Path
) -> None:
    target = tmp_path / "builds.json"
    target.write_text((fixtures_dir / "builds_minimal.json").read_text())
    monkeypatch.setattr(builds, "DEFAULT_PATH", target)
    monkeypatch.setattr(refresh_rust_digests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(
        refresh_rust_digests.docker_inspect,
        "index_digest",
        lambda ref: pytest.fail("should not query docker when nothing needs refresh"),
    )
    before = target.read_text()
    assert refresh_rust_digests.main([]) == 0
    assert target.read_text() == before
