import shutil
from pathlib import Path

import pytest

import release_body


def test_load_metadata_reads_all_files(tmp_path: Path, fixtures_dir: Path) -> None:
    for name in ("meta_amd64.json", "meta_arm64.json"):
        shutil.copy(fixtures_dir / name, tmp_path / name.replace("_", "-"))
    rows = release_body.load_metadata(tmp_path, "26.0.0")
    arches = [r["arch"] for r in rows]
    assert arches == ["amd64", "arm64"]


def test_load_metadata_empty_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no meta-"):
        release_body.load_metadata(tmp_path, "26.0.0")


def test_load_metadata_rejects_mismatched_cli(tmp_path: Path, fixtures_dir: Path) -> None:
    shutil.copy(fixtures_dir / "meta_amd64.json", tmp_path / "meta-x.json")
    with pytest.raises(ValueError, match=r"expected '99\.0\.0'"):
        release_body.load_metadata(tmp_path, "99.0.0")


def test_load_metadata_sorts_by_rust_version_then_key_then_arch(tmp_path: Path) -> None:
    import json

    rows_in = [
        {
            "arch": "arm64",
            "digest": "sha256:" + "a" * 64,
            "image": "x",
            "rust_base_key": "1.94.0-slim-trixie",
            "rust_version": "1.94.0",
            "stellar_cli_version": "26.0.0",
            "tag": "x",
        },
        {
            "arch": "amd64",
            "digest": "sha256:" + "b" * 64,
            "image": "x",
            "rust_base_key": "1.100.0-slim-trixie",
            "rust_version": "1.100.0",
            "stellar_cli_version": "26.0.0",
            "tag": "x",
        },
        {
            "arch": "amd64",
            "digest": "sha256:" + "c" * 64,
            "image": "x",
            "rust_base_key": "1.94.0-slim-trixie",
            "rust_version": "1.94.0",
            "stellar_cli_version": "26.0.0",
            "tag": "x",
        },
    ]
    for i, row in enumerate(rows_in):
        (tmp_path / f"meta-{i}.json").write_text(json.dumps(row))
    out = release_body.load_metadata(tmp_path, "26.0.0")
    # Sorted numerically by rust_version (1.94 before 1.100) then by arch.
    assert [(r["rust_version"], r["arch"]) for r in out] == [
        ("1.94.0", "amd64"),
        ("1.94.0", "arm64"),
        ("1.100.0", "amd64"),
    ]


def test_rust_keys_newest_first_orders_by_version_desc() -> None:
    rows = [
        {"rust_base_key": "1.94.0-slim-trixie", "rust_version": "1.94.0"},
        {"rust_base_key": "1.100.0-slim-trixie", "rust_version": "1.100.0"},
        {"rust_base_key": "1.94.0-slim-trixie", "rust_version": "1.94.0"},  # dup
    ]
    assert release_body.rust_keys_newest_first(rows) == [
        "1.100.0-slim-trixie",
        "1.94.0-slim-trixie",
    ]


def test_emit_body_includes_expected_sections() -> None:
    rows = [
        {
            "arch": "amd64",
            "digest": "sha256:" + "1" * 64,
            "rust_base_key": "1.94.0-slim-trixie",
            "rust_version": "1.94.0",
        },
        {
            "arch": "arm64",
            "digest": "sha256:" + "2" * 64,
            "rust_base_key": "1.94.0-slim-trixie",
            "rust_version": "1.94.0",
        },
    ]
    body = release_body.emit_body(
        cli="26.0.0",
        rows=rows,
        registry="docker.io/stellar/stellar-cli",
        repo="stellar/stellar-cli-docker",
        stellar_ref="abc123",
    )
    assert "# stellar-cli 26.0.0" in body
    assert "## Tags" in body
    assert "docker.io/stellar/stellar-cli:latest" in body
    assert "26.0.0-abc123-rust1.94.0-slim-trixie" in body
    assert "## Per-architecture digests" in body
    assert "### Rust 1.94.0-slim-trixie" in body
    assert "linux/amd64" in body
    assert "linux/arm64" in body
    assert "gh attestation verify" in body
    assert "cosign verify-attestation" in body
    assert "docker buildx imagetools inspect" in body
    assert "## Verification" in body
    assert "## Assets" in body
    # Each shell-continuation line in the cosign block must end with a single
    # backslash, not two — `\\` in the rendered markdown would land as a
    # literal `\\` in the user's terminal instead of a line continuation.
    cosign_lines = [
        line for line in body.splitlines() if "cosign" in line or "certificate-" in line
    ]
    assert cosign_lines, "expected cosign verify lines in body"
    for line in cosign_lines:
        if line.endswith("\\"):
            assert not line.endswith(r"\\"), f"double-backslash continuation: {line!r}"


def test_main_writes_body_to_stdout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fixtures_dir: Path,
    capsys: pytest.CaptureFixture[str],
    minimal_builds: dict,
) -> None:
    for name in ("meta_amd64.json", "meta_arm64.json"):
        shutil.copy(fixtures_dir / name, tmp_path / name.replace("_", "-"))
    monkeypatch.setattr(release_body.builds, "load", lambda: minimal_builds)
    rc = release_body.main(
        [
            "--stellar-cli-version",
            "26.0.0",
            "--metadata-dir",
            str(tmp_path),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert out.startswith("# stellar-cli 26.0.0")
