import base64
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import backfill_iteration_tags as backfill

BASE_DIGEST = "sha256:" + "a" * 64
PIN = f"1.90.0-slim-bookworm@{BASE_DIGEST}"
# resolve_matrix bakes <label>-<first 15 hex of base digest> into asset names.
BASE_ID = "1.90.0-slim-bookworm-" + "a" * 15
SNAPSHOT = {
    "default_distro": "bookworm",
    "stellar_cli_versions": [
        {"ref": "a" * 40, "rust_versions": [PIN], "version": "25.1.0"},
    ],
}


def _prov_bundle(image_digest: str) -> str:
    """A minimal DSSE-wrapped in-toto bundle exposing one subject digest."""
    statement = {"subject": [{"name": "reg/img", "digest": {"sha256": image_digest}}]}
    payload = base64.b64encode(json.dumps(statement).encode()).decode()
    return json.dumps({"dsseEnvelope": {"payload": payload}})


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


def test_rust_base_id_matches_resolve_matrix() -> None:
    assert backfill.rust_base_id(PIN) == BASE_ID


def test_subject_digest_decodes_dsse_payload(tmp_path: Path) -> None:
    path = tmp_path / "prov.intoto.jsonl"
    path.write_text(_prov_bundle("c" * 64))
    assert backfill.subject_digest(path) == "sha256:" + "c" * 64


def test_digests_by_arch_reads_both_bundles(tmp_path: Path) -> None:
    (tmp_path / f"prov-25.1.0-rust{BASE_ID}-arm64.intoto.jsonl").write_text(_prov_bundle("b" * 64))
    (tmp_path / f"prov-25.1.0-rust{BASE_ID}-amd64.intoto.jsonl").write_text(_prov_bundle("c" * 64))
    digests = backfill.digests_by_arch(tmp_path, "25.1.0", BASE_ID)
    assert digests == {
        "amd64": "sha256:" + "c" * 64,
        "arm64": "sha256:" + "b" * 64,
    }


def test_digests_by_arch_skips_missing_arch(tmp_path: Path) -> None:
    (tmp_path / f"prov-25.1.0-rust{BASE_ID}-amd64.intoto.jsonl").write_text(_prov_bundle("c" * 64))
    digests = backfill.digests_by_arch(tmp_path, "25.1.0", BASE_ID)
    assert digests == {"amd64": "sha256:" + "c" * 64}


# The per-arch immutable tag scheme minted for the fixture pin.
LABEL = "1.90.0-slim-bookworm"


def _arch_tag(iteration: int, arch: str) -> str:
    return f"reg/img:25.1.0-rust{LABEL}-{arch}-{iteration}"


def _wire_main(monkeypatch: pytest.MonkeyPatch, *, existing: set[str]) -> MagicMock:
    monkeypatch.setattr(backfill.common, "preflight_checks", lambda _: None)
    monkeypatch.setattr(backfill.gh_cli, "list_release_tags", lambda repo: ["v25.1.0", "v25.1.0-1"])
    monkeypatch.setattr(backfill, "load_builds_at_ref", lambda repo, ref: SNAPSHOT)

    def fake_download(repo: str, tag: str, pattern: str, dest_dir: str) -> None:
        # Digest varies per release tag so each iteration gets a distinct source.
        image_digest = tag[-1] * 64
        for arch in backfill.ARCHES:
            path = Path(dest_dir) / f"prov-25.1.0-rust{BASE_ID}-{arch}.intoto.jsonl"
            path.write_text(_prov_bundle(image_digest))

    monkeypatch.setattr(backfill.gh_cli, "download_release_assets", fake_download)
    monkeypatch.setattr(backfill.docker_inspect, "exists", lambda ref: ref in existing)
    created = MagicMock()
    monkeypatch.setattr(backfill.docker_inspect, "create_manifest", created)
    return created


def test_main_creates_missing_per_arch_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _wire_main(monkeypatch, existing=set())

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])

    assert rc == 0
    tags = [call.args[0] for call in created.call_args_list]
    # Both iterations, both arches.
    assert _arch_tag(0, "amd64") in tags
    assert _arch_tag(0, "arm64") in tags
    assert _arch_tag(1, "amd64") in tags
    assert _arch_tag(1, "arm64") in tags
    # Each immutable tag pins the digest recovered from its prov bundle.
    calls = {call.args[0]: call.args[1] for call in created.call_args_list}
    assert calls[_arch_tag(0, "amd64")] == "reg/img@sha256:" + "0" * 64
    assert calls[_arch_tag(1, "amd64")] == "reg/img@sha256:" + "1" * 64


def test_main_skips_already_tagged_arches(monkeypatch: pytest.MonkeyPatch) -> None:
    created = _wire_main(monkeypatch, existing={_arch_tag(0, "amd64"), _arch_tag(0, "arm64")})

    rc = backfill.main(["--stellar-cli-version", "25.1.0", "--registry", "reg/img"])

    assert rc == 0
    tags = [call.args[0] for call in created.call_args_list]
    # Iteration 0's arches already exist; only iteration 1 is created.
    assert _arch_tag(0, "amd64") not in tags
    assert _arch_tag(0, "arm64") not in tags
    assert _arch_tag(1, "amd64") in tags
    assert _arch_tag(1, "arm64") in tags


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
