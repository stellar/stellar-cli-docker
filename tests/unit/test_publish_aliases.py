from unittest.mock import MagicMock

import pytest

import publish_aliases


def test_main_publishes_cli_alias_and_latest_for_newest(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_aliases.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_aliases.builds, "load", lambda: multi_cli_builds)
    captured = MagicMock()
    monkeypatch.setattr(publish_aliases.docker_inspect, "create_manifest", captured)

    # 26.0.0 is the newest in multi_cli_builds.
    rc = publish_aliases.main(["--stellar-cli-version", "26.0.0"])

    assert rc == 0
    aliases = [call.args[0] for call in captured.call_args_list]
    assert "docker.io/stellar/stellar-cli:26.0.0" in aliases
    assert "docker.io/stellar/stellar-cli:latest" in aliases


def test_main_skips_latest_for_non_newest(monkeypatch: pytest.MonkeyPatch) -> None:
    # Both clis carry a trixie key so derive_default_rust succeeds; 26.0.0 is newest.
    data = {
        "default_distro": "trixie",
        "rust_image_digests": {
            "1.94.0-slim-trixie": "sha256:" + "a" * 64,
        },
        "stellar_cli_versions": [
            {"ref": "a" * 40, "rust_versions": ["1.94.0-slim-trixie"], "version": "26.0.0"},
            {"ref": "b" * 40, "rust_versions": ["1.94.0-slim-trixie"], "version": "26.1.0"},
        ],
    }
    monkeypatch.setattr(publish_aliases.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_aliases.builds, "load", lambda: data)
    captured = MagicMock()
    monkeypatch.setattr(publish_aliases.docker_inspect, "create_manifest", captured)

    # 26.0.0 is not the newest (26.1.0 is).
    rc = publish_aliases.main(["--stellar-cli-version", "26.0.0"])

    assert rc == 0
    aliases = [call.args[0] for call in captured.call_args_list]
    assert "docker.io/stellar/stellar-cli:26.0.0" in aliases
    assert "docker.io/stellar/stellar-cli:latest" not in aliases


def test_main_dies_for_unknown_cli(monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict) -> None:
    monkeypatch.setattr(publish_aliases.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_aliases.builds, "load", lambda: multi_cli_builds)
    with pytest.raises(SystemExit):
        publish_aliases.main(["--stellar-cli-version", "99.0.0"])


def test_main_dry_run_does_not_create(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_aliases.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_aliases.builds, "load", lambda: multi_cli_builds)
    captured = MagicMock()
    monkeypatch.setattr(publish_aliases.docker_inspect, "create_manifest", captured)

    rc = publish_aliases.main(["--stellar-cli-version", "26.0.0", "--dry-run"])
    assert rc == 0
    assert captured.call_count == 0
