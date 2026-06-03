from unittest.mock import MagicMock

import pytest

import publish_manifests


def test_manifest_for_pair_composes_three_refs() -> None:
    digest = "sha256:f7bf1c266d9e48c8d724733fd97ba60464c44b743eb4f46f935577d3242d81d0"
    list_ref, amd64_ref, arm64_ref = publish_manifests.manifest_for_pair(
        registry="docker.io/stellar/stellar-cli",
        cli="26.0.0",
        rust_key="1.94.0-slim-trixie",
        rust_image_digest=digest,
        stellar_ref="abc123",
    )
    base = "docker.io/stellar/stellar-cli:26.0.0-abc123-rust1.94.0-slim-trixie-f7bf1c266d9e48c"
    assert list_ref == base
    assert amd64_ref == f"{base}-amd64"
    assert arm64_ref == f"{base}-arm64"


def test_main_creates_manifest_for_each_rust_version(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    monkeypatch.setattr(publish_manifests.docker_inspect, "exists", lambda _: False)
    captured = MagicMock()
    monkeypatch.setattr(publish_manifests.docker_inspect, "create_manifest", captured)

    assert publish_manifests.main(["--stellar-cli-version", "26.0.0"]) == 0
    # 26.0.0 has 2 rust_versions → 2 manifest creations.
    assert captured.call_count == 2


def test_main_skips_existing_manifests(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    monkeypatch.setattr(publish_manifests.docker_inspect, "exists", lambda _: True)
    captured = MagicMock()
    monkeypatch.setattr(publish_manifests.docker_inspect, "create_manifest", captured)
    summary = MagicMock()
    monkeypatch.setattr(publish_manifests.common, "step_summary", summary)

    assert publish_manifests.main(["--stellar-cli-version", "26.0.0"]) == 0
    assert captured.call_count == 0
    # Each skipped list records a step-summary note (26.0.0 has 2 rust_versions).
    assert summary.call_count == 2


def test_main_unknown_cli_dies(monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    with pytest.raises(SystemExit):
        publish_manifests.main(["--stellar-cli-version", "99.0.0"])


def test_main_dry_run_does_not_create(
    monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(publish_manifests.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(publish_manifests.builds, "load", lambda: multi_cli_builds)
    monkeypatch.setattr(publish_manifests.docker_inspect, "exists", lambda _: False)
    captured = MagicMock()
    monkeypatch.setattr(publish_manifests.docker_inspect, "create_manifest", captured)

    assert publish_manifests.main(["--stellar-cli-version", "26.0.0", "--dry-run"]) == 0
    assert captured.call_count == 0
