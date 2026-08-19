from unittest.mock import MagicMock

import pytest

import publish_manifests


def test_manifest_for_pair_composes_three_refs() -> None:
    list_ref, amd64_ref, arm64_ref = publish_manifests.manifest_for_pair(
        registry="docker.io/stellar/stellar-cli",
        cli="26.0.0",
        rust_key="1.94.0-slim-trixie",
    )
    base = "docker.io/stellar/stellar-cli:26.0.0-rust1.94.0-slim-trixie"
    assert list_ref == base
    assert amd64_ref == f"{base}-amd64"
    assert arm64_ref == f"{base}-arm64"


def test_immutable_arch_ref_appends_iteration() -> None:
    ref = publish_manifests.immutable_arch_ref(
        registry="docker.io/stellar/stellar-cli",
        cli="26.0.0",
        rust_key="1.94.0-slim-trixie",
        arch="amd64",
        iteration=3,
    )
    assert ref == "docker.io/stellar/stellar-cli:26.0.0-rust1.94.0-slim-trixie-amd64-3"


def test_main_creates_list_and_immutable_per_arch_tags(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    captured = MagicMock()
    monkeypatch.setattr(publish_manifests.docker_inspect, "create_manifest", captured)

    assert publish_manifests.main(["--stellar-cli-version", "26.0.0", "--iteration", "0"]) == 0
    # 26.0.0 has 2 rust labels → per label: 1 list + 2 per-arch snapshots = 6.
    assert captured.call_count == 6
    tags = [call.args[0] for call in captured.call_args_list]
    reg = "docker.io/stellar/stellar-cli"
    assert f"{reg}:26.0.0-rust1.94.0-slim-trixie" in tags
    assert f"{reg}:26.0.0-rust1.94.0-slim-trixie-amd64-0" in tags
    assert f"{reg}:26.0.0-rust1.94.0-slim-trixie-arm64-0" in tags


def test_main_immutable_tag_sources_the_mutable_per_arch_tag(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    captured = MagicMock()
    monkeypatch.setattr(publish_manifests.docker_inspect, "create_manifest", captured)

    assert publish_manifests.main(["--stellar-cli-version", "26.0.0", "--iteration", "1"]) == 0
    calls = {call.args[0]: call.args[1:] for call in captured.call_args_list}
    reg = "docker.io/stellar/stellar-cli"
    # The immutable per-arch snapshot references the mutable per-arch tag.
    assert calls[f"{reg}:26.0.0-rust1.94.0-slim-trixie-amd64-1"] == (
        f"{reg}:26.0.0-rust1.94.0-slim-trixie-amd64",
    )


def test_main_unknown_cli_dies(monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    with pytest.raises(SystemExit):
        publish_manifests.main(["--stellar-cli-version", "99.0.0", "--iteration", "0"])


def test_main_dies_for_negative_iteration(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    with pytest.raises(SystemExit):
        publish_manifests.main(["--stellar-cli-version", "26.0.0", "--iteration", "-1"])


def test_main_dry_run_does_not_create(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    captured = MagicMock()
    monkeypatch.setattr(publish_manifests.docker_inspect, "create_manifest", captured)

    argv = ["--stellar-cli-version", "26.0.0", "--iteration", "0", "--dry-run"]
    assert publish_manifests.main(argv) == 0
    assert captured.call_count == 0
