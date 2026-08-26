from unittest.mock import MagicMock

import pytest

import backfill_iteration_tags as backfill

KEY = "1.90.0-slim-bookworm"
# The `bldimg` anchor is the tag's top-level *index* digest, not the child
# per-platform submanifest one level down — keep the two distinct so the tests
# fail if the backfill ever pins the child digest again.
AMD64_INDEX = "sha256:" + "1" * 64
ARM64_INDEX = "sha256:" + "2" * 64
AMD64_CHILD = "sha256:" + "a" * 64
ARM64_CHILD = "sha256:" + "b" * 64


def _image(arch: str, digest: str, os_: str = "linux") -> dict:
    return {"architecture": arch, "os": os_, "digest": digest}


def _hub_tags(cli: str = "25.1.0") -> list[dict]:
    """A repo's current tag state as the Docker Hub API returns it.

    Includes the noise the real API carries — the multi-arch list tag, the
    `unknown/unknown` attestation manifests, an already-minted immutable
    snapshot, and an unrelated cli — so the parser is exercised against it. Each
    per-arch tag is an attestation-bearing *index*: its top-level `digest` is the
    index digest (the `bldimg` anchor) while `images[].digest` is the child
    submanifest, so the two must not be conflated.
    """
    unknown = _image("unknown", "sha256:" + "f" * 64, os_="unknown")
    return [
        {
            "name": f"{cli}-rust{KEY}",  # multi-arch list tag: no arch suffix
            "digest": "sha256:" + "d" * 64,
            "images": [_image("amd64", AMD64_CHILD), unknown, _image("arm64", ARM64_CHILD)],
        },
        {
            "name": f"{cli}-rust{KEY}-amd64",
            "digest": AMD64_INDEX,
            "images": [_image("amd64", AMD64_CHILD), unknown],
        },
        {
            "name": f"{cli}-rust{KEY}-arm64",
            "digest": ARM64_INDEX,
            "images": [_image("arm64", ARM64_CHILD), unknown],
        },
        {  # already-minted immutable snapshot: ends in a digit, must be ignored
            "name": f"{cli}-rust{KEY}-amd64-0",
            "digest": AMD64_INDEX,
            "images": [_image("amd64", AMD64_CHILD), unknown],
        },
        {  # unrelated cli
            "name": f"26.0.0-rust{KEY}-amd64",
            "digest": "sha256:" + "e" * 64,
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
    # snapshot, the attestation manifests, or the unrelated cli. Each pins the
    # tag's top-level index digest, never the child per-platform submanifest.
    assert pairs == {
        (KEY, "amd64"): AMD64_INDEX,
        (KEY, "arm64"): ARM64_INDEX,
    }


def test_current_pairs_uses_index_digest_not_child_submanifest() -> None:
    # Guards the issue #38 anchor: the recovered digest must be the index digest
    # (the tag's own `digest`), matching docker_inspect.index_digest and what the
    # publish workflow records as `bldimg` — not the child `images[].digest`.
    pairs = backfill.current_pairs(_hub_tags(), "25.1.0")
    assert AMD64_CHILD not in pairs.values()
    assert ARM64_CHILD not in pairs.values()


def test_current_pairs_handles_plain_manifest_per_arch_tag() -> None:
    # A non-attestation per-arch tag is a plain single manifest: its top-level
    # `digest` equals its sole `images[].digest`. Both shapes resolve correctly.
    plain = "sha256:" + "9" * 64
    tags = [
        {
            "name": f"25.1.0-rust{KEY}-amd64",
            "digest": plain,
            "images": [_image("amd64", plain)],
        }
    ]
    assert backfill.current_pairs(tags, "25.1.0") == {(KEY, "amd64"): plain}


def _wire_main(monkeypatch: pytest.MonkeyPatch, *, existing: set[str], releases=None) -> MagicMock:
    monkeypatch.setattr(backfill.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(backfill.gh_cli, "list_release_tags", lambda repo: releases or ["v25.1.0"])
    monkeypatch.setattr(backfill.dockerhub, "list_tags", lambda repo_path: _hub_tags())
    monkeypatch.setattr(backfill.docker_inspect, "exists", lambda ref: ref in existing)

    # An already-existing snapshot pins the same index digest its live per-arch
    # tag exposes — the safe, re-runnable case, so `main` skips it. Tests that
    # want a re-point conflict patch index_digest to return something else.
    def _index_digest(ref: str) -> str:
        return ARM64_INDEX if ref.rsplit("-", 1)[0].endswith("arm64") else AMD64_INDEX

    monkeypatch.setattr(backfill.docker_inspect, "index_digest", _index_digest)
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
    # Both arches, at iteration 0, each pinning the index digest its live tag
    # exposes (the `bldimg` anchor), never the child submanifest.
    assert calls[_arch_tag("amd64")] == f"reg/img@{AMD64_INDEX}"
    assert calls[_arch_tag("arm64")] == f"reg/img@{ARM64_INDEX}"


def test_main_uses_highest_release_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _wire_main(monkeypatch, existing=set(), releases=["v25.1.0", "v25.1.0-1"])

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])

    assert rc == 0
    tags = [call.args[0] for call in created.call_args_list]
    # Current tag content belongs to the newest iteration (1), not 0.
    assert _arch_tag("amd64", 1) in tags
    assert _arch_tag("arm64", 1) in tags


def test_main_skips_already_tagged_arches(monkeypatch: pytest.MonkeyPatch) -> None:
    # amd64's snapshot already exists pinning the same digest → skip; arm64's is
    # created.
    created = _wire_main(monkeypatch, existing={_arch_tag("amd64")})

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])

    assert rc == 0
    tags = [call.args[0] for call in created.call_args_list]
    assert _arch_tag("amd64") not in tags
    assert _arch_tag("arm64") in tags


def test_main_refuses_to_repoint_existing_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    # A snapshot that already exists pinning a *different* digest than the live
    # per-arch tag is an immutability violation — fail loudly, don't clobber.
    _wire_main(monkeypatch, existing={_arch_tag("amd64")})
    monkeypatch.setattr(backfill.docker_inspect, "index_digest", lambda ref: "sha256:" + "0" * 64)

    with pytest.raises(SystemExit):
        backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])


def test_main_accepts_explicit_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    # Newest release is -1, but --iteration pins the live content to 0 (e.g. the
    # -1 publish failed before pushing, so the live tags still hold -0's images).
    created = _wire_main(monkeypatch, existing=set(), releases=["v25.1.0", "v25.1.0-1"])

    rc = backfill.main(
        ["--stellar-cli-version", "25.1.0", "--registry", "reg/img", "--iteration", "0"]
    )

    assert rc == 0
    tags = [call.args[0] for call in created.call_args_list]
    assert _arch_tag("amd64", 0) in tags
    assert _arch_tag("arm64", 0) in tags
    assert _arch_tag("amd64", 1) not in tags


def test_main_rejects_negative_iteration(monkeypatch: pytest.MonkeyPatch) -> None:
    _wire_main(monkeypatch, existing=set())

    with pytest.raises(SystemExit):
        backfill.main(
            ["--stellar-cli-version", "25.1.0", "--registry", "reg/img", "--iteration", "-1"]
        )


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
