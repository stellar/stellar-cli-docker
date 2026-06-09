import json
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


def test_main_delegates_to_refresh_and_emits_tag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    staged_minimal: Path,
) -> None:
    monkeypatch.setattr(release_prepare.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(release_prepare.gh_cli, "list_release_tags", lambda _: [])
    monkeypatch.setattr(release_prepare.validate_json, "main", lambda _: 0)

    captured_argv: list[list[str]] = []

    def fake_refresh(argv):
        captured_argv.append(argv)
        data = builds.load()
        data["stellar_cli_versions"].append(
            {
                "ref": "a" * 40,
                "rust_versions": ["1.95.0-slim-trixie@sha256:" + "f" * 64],
                "version": "27.0.0",
            }
        )
        builds.dump(data)
        return 0

    monkeypatch.setattr(release_prepare.refresh, "main", fake_refresh)

    rc = release_prepare.main(
        ["--stellar-cli-version", "27.0.0", "--rust-versions", "1.95.0-slim-trixie"]
    )
    assert rc == 0
    assert capsys.readouterr().out == "v27.0.0\n"
    # The cli version and the rust-versions override are forwarded to refresh.
    assert captured_argv[0][:2] == ["--stellar-cli-version", "27.0.0"]
    assert "--rust-versions" in captured_argv[0]
    data = json.loads(staged_minimal.read_text())
    versions = [e["version"] for e in data["stellar_cli_versions"]]
    assert "27.0.0" in versions


def test_main_dies_when_nothing_changes(
    monkeypatch: pytest.MonkeyPatch, staged_minimal: Path
) -> None:
    monkeypatch.setattr(release_prepare.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(release_prepare.gh_cli, "list_release_tags", lambda _: [])
    monkeypatch.setattr(release_prepare.validate_json, "main", lambda _: 0)
    # refresh resolves to exactly what's already declared → no write.
    monkeypatch.setattr(release_prepare.refresh, "main", lambda _: 0)

    with pytest.raises(SystemExit):
        release_prepare.main(
            ["--stellar-cli-version", "26.0.0", "--rust-versions", "1.94.0-slim-trixie"]
        )


def test_main_dies_when_refresh_fails(
    monkeypatch: pytest.MonkeyPatch, staged_minimal: Path
) -> None:
    monkeypatch.setattr(release_prepare.common, "preflight_checks", lambda _: None)

    def boom(_argv):
        raise SystemExit(1)

    monkeypatch.setattr(release_prepare.refresh, "main", boom)
    with pytest.raises(SystemExit):
        release_prepare.main(["--stellar-cli-version", "27.0.0"])
