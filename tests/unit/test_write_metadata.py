import json
from pathlib import Path

import pytest

import write_metadata


def _common_args(out: Path) -> list[str]:
    return [
        "--output",
        str(out),
        "--arch",
        "amd64",
        "--stellar-cli-version",
        "26.0.0",
        "--image",
        "docker.io/stellar/stellar-cli:26.0.0-abc-rust1.94.0-slim-trixie-amd64",
        "--rust-base-key",
        "1.94.0-slim-trixie",
        "--rust-version",
        "1.94.0",
        "--tag",
        "26.0.0-abc-rust1.94.0-slim-trixie-amd64",
    ]


def test_main_writes_metadata_with_explicit_digest(tmp_path: Path) -> None:
    out = tmp_path / "meta.json"
    args = [*_common_args(out), "--digest", "sha256:" + "a" * 64]
    assert write_metadata.main(args) == 0
    data = json.loads(out.read_text())
    assert data == {
        "arch": "amd64",
        "digest": "sha256:" + "a" * 64,
        "image": "docker.io/stellar/stellar-cli:26.0.0-abc-rust1.94.0-slim-trixie-amd64",
        "rust_base_key": "1.94.0-slim-trixie",
        "rust_version": "1.94.0",
        "stellar_cli_version": "26.0.0",
        "tag": "26.0.0-abc-rust1.94.0-slim-trixie-amd64",
    }


def test_main_resolves_digest_when_omitted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    looked_up = []
    fake_digest = "sha256:" + "f" * 64

    def fake_index_digest(image):
        looked_up.append(image)
        return fake_digest

    monkeypatch.setattr(write_metadata.docker_inspect, "index_digest", fake_index_digest)
    out = tmp_path / "meta.json"
    assert write_metadata.main(_common_args(out)) == 0
    data = json.loads(out.read_text())
    assert data["digest"] == fake_digest
    assert looked_up == ["docker.io/stellar/stellar-cli:26.0.0-abc-rust1.94.0-slim-trixie-amd64"]


def test_main_dies_if_lookup_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_image):
        raise RuntimeError("no Digest line in output")

    monkeypatch.setattr(write_metadata.docker_inspect, "index_digest", boom)
    out = tmp_path / "meta.json"
    with pytest.raises(SystemExit):
        write_metadata.main(_common_args(out))


def test_output_is_sorted_keys_with_trailing_newline(tmp_path: Path) -> None:
    out = tmp_path / "meta.json"
    args = [*_common_args(out), "--digest", "sha256:" + "a" * 64]
    write_metadata.main(args)
    text = out.read_text()
    assert text.endswith("\n")
    root_keys = [line.split('"')[1] for line in text.splitlines() if line.startswith('  "')]
    assert root_keys == sorted(root_keys)
