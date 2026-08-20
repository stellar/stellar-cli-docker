from unittest.mock import MagicMock

import pytest

import backfill_iteration_tags as backfill

KEY = "1.90.0-slim-bookworm"
AMD64_DIGEST = "sha256:" + "a" * 64
ARM64_DIGEST = "sha256:" + "b" * 64


def _image(arch: str, digest: str, os_: str = "linux") -> dict:
    return {"architecture": arch, "os": os_, "digest": digest}


def _hub_tags(cli: str = "25.1.0") -> list[dict]:
    """A repo's current tag state as the Docker Hub API returns it.

    Includes the noise the real API carries — the multi-arch list tag, the
    `unknown/unknown` attestation manifests, an already-minted immutable
    snapshot, and an unrelated cli — so the parser is exercised against it.
    """
    unknown = _image("unknown", "sha256:" + "f" * 64, os_="unknown")
    return [
        {
            "name": f"{cli}-rust{KEY}",  # multi-arch list tag: no arch suffix
            "images": [_image("amd64", AMD64_DIGEST), unknown, _image("arm64", ARM64_DIGEST)],
        },
        {"name": f"{cli}-rust{KEY}-amd64", "images": [_image("amd64", AMD64_DIGEST), unknown]},
        {"name": f"{cli}-rust{KEY}-arm64", "images": [_image("arm64", ARM64_DIGEST), unknown]},
        {  # already-minted immutable snapshot: ends in a digit, must be ignored
            "name": f"{cli}-rust{KEY}-amd64-0",
            "images": [_image("amd64", AMD64_DIGEST), unknown],
        },
        {  # unrelated cli
            "name": f"26.0.0-rust{KEY}-amd64",
            "images": [_image("amd64", "sha256:" + "c" * 64), unknown],
        },
    ]


def test_iterations_for_cli_parses_and_orders() -> None:
    tags = [
        "v25.1.0",
        "v25.1.0-1",
        "v25.2.0",
        "v25.1.0-2",
        "v26.0.0-1",
        "not-a-release",
    ]
    assert backfill.iterations_for_cli(tags, "25.1.0") == [
        ("v25.1.0", 0),
        ("v25.1.0-1", 1),
        ("v25.1.0-2", 2),
    ]


def test_iterations_for_cli_does_not_prefix_match_other_versions() -> None:
    # 25.1.0 must not swallow 25.1.05 or unrelated versions.
    tags = ["v25.1.05", "v25.1.0"]
    assert backfill.iterations_for_cli(tags, "25.1.0") == [("v25.1.0", 0)]


def test_latest_iteration_is_the_highest_index() -> None:
    assert backfill.latest_iteration(["v25.2.0", "v25.2.0-1"], "25.2.0") == 1
    assert backfill.latest_iteration(["v25.1.0"], "25.1.0") == 0
    assert backfill.latest_iteration(["v26.0.0"], "25.1.0") is None


def test_current_pairs_reads_per_arch_tags_only() -> None:
    pairs = backfill.current_pairs(_hub_tags(), "25.1.0")
    # Only the two per-arch tags of 25.1.0 — not the list tag, the immutable
    # snapshot, the attestation manifests, or the unrelated cli.
    assert pairs == {
        (KEY, "amd64"): AMD64_DIGEST,
        (KEY, "arm64"): ARM64_DIGEST,
    }


def _wire_main(monkeypatch: pytest.MonkeyPatch, *, existing: set[str], releases=None) -> MagicMock:
    monkeypatch.setattr(backfill.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(backfill.gh_cli, "list_release_tags", lambda repo: releases or ["v25.1.0"])
    monkeypatch.setattr(backfill.dockerhub, "list_tags", lambda repo_path: _hub_tags())
    monkeypatch.setattr(backfill.docker_inspect, "exists", lambda ref: ref in existing)
    created = MagicMock()
    monkeypatch.setattr(backfill.docker_inspect, "create_manifest", created)
    return created


def _arch_tag(arch: str, iteration: int = 0) -> str:
    return f"reg/img:25.1.0-rust{KEY}-{arch}-{iteration}"


def test_main_creates_missing_per_arch_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _wire_main(monkeypatch, existing=set())

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])

    assert rc == 0
    calls = {call.args[0]: call.args[1] for call in created.call_args_list}
    # Both arches, at iteration 0, each pinning the digest its live tag exposes.
    assert calls[_arch_tag("amd64")] == f"reg/img@{AMD64_DIGEST}"
    assert calls[_arch_tag("arm64")] == f"reg/img@{ARM64_DIGEST}"


def test_main_uses_highest_release_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _wire_main(monkeypatch, existing=set(), releases=["v25.1.0", "v25.1.0-1"])

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])

    assert rc == 0
    tags = [call.args[0] for call in created.call_args_list]
    # Current tag content belongs to the newest iteration (1), not 0.
    assert _arch_tag("amd64", 1) in tags
    assert _arch_tag("arm64", 1) in tags


def test_main_skips_already_tagged_arches(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _wire_main(monkeypatch, existing={_arch_tag("amd64")})

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])

    assert rc == 0
    tags = [call.args[0] for call in created.call_args_list]
    assert _arch_tag("amd64") not in tags
    assert _arch_tag("arm64") in tags


def test_main_dry_run_creates_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _wire_main(monkeypatch, existing=set())

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img", "--dry-run"])

    assert rc == 0
    assert created.call_count == 0


def test_main_reports_no_releases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backfill.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(backfill.gh_cli, "list_release_tags", lambda repo: ["v99.0.0"])
    with pytest.raises(SystemExit):
        backfill.main(["--stellar-cli-version", "25.1.0"])


def test_main_reports_no_per_arch_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(backfill.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(backfill.gh_cli, "list_release_tags", lambda repo: ["v25.1.0"])
    monkeypatch.setattr(backfill.dockerhub, "list_tags", lambda repo_path: [])
    with pytest.raises(SystemExit):
        backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])
