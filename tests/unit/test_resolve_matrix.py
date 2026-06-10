import json

import pytest

import resolve_matrix


def test_build_matrix_unrestricted_includes_all_clis(multi_cli_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(multi_cli_builds)
    versions = {row["stellar_cli_version"] for row in matrix["include"]}
    assert versions == {"25.1.0", "26.0.0"}


def test_build_matrix_emits_one_row_per_cli_rust_arch(multi_cli_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(multi_cli_builds)
    # 25.1.0 has 1 rust → 2 rows; 26.0.0 has 2 rusts → 4 rows; total 6.
    assert len(matrix["include"]) == 6


def test_build_matrix_filtered_to_one_cli(multi_cli_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(multi_cli_builds, only_cli="26.0.0")
    assert len(matrix["include"]) == 4
    assert all(row["stellar_cli_version"] == "26.0.0" for row in matrix["include"])


def test_build_matrix_row_carries_expected_keys(minimal_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(minimal_builds)
    row = matrix["include"][0]
    assert set(row.keys()) == {
        "arch",
        "cli_rust_image_digest",
        "platform",
        "rust_base_id",
        "rust_base_key",
        "rust_base_suffix",
        "rust_image_digest",
        "rust_version",
        "stellar_cli_ref",
        "stellar_cli_version",
    }


def test_build_matrix_row_id_carries_digest_fragment(minimal_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(minimal_builds)
    row = matrix["include"][0]
    # rust_base_id disambiguates two pins that share a label but differ by digest,
    # so downstream artifact/file names never collide.
    assert row["rust_base_id"] == "1.94.0-slim-trixie-f7bf1c266d9e48c"


def test_build_matrix_same_label_builds_only_last_pin() -> None:
    # builds.json keeps the full history, but only the newest pin per label
    # (last in the list) is published, so the mutable tag is deterministic.
    data = {
        "default_distro": "trixie",
        "stellar_cli_versions": [
            {
                "ref": "a" * 40,
                "version": "26.0.0",
                "rust_versions": [
                    "1.94.0-slim-trixie@sha256:" + "a" * 64,
                    "1.94.0-slim-trixie@sha256:" + "b" * 64,
                ],
            }
        ],
    }
    rows = resolve_matrix.build_matrix(data)["include"]
    # Only the last pin builds (one per arch); the superseded pin is not built.
    assert len(rows) == 2
    assert {r["rust_base_id"] for r in rows} == {"1.94.0-slim-trixie-" + "b" * 15}
    assert {r["rust_image_digest"] for r in rows} == {"sha256:" + "b" * 64}


def test_build_matrix_parses_rust_key(minimal_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(minimal_builds)
    row = matrix["include"][0]
    assert row["rust_base_key"] == "1.94.0-slim-trixie"
    assert row["rust_version"] == "1.94.0"
    assert row["rust_base_suffix"] == "slim-trixie"


def test_build_matrix_emits_both_archs_per_pair(minimal_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(minimal_builds)
    arches = [row["arch"] for row in matrix["include"]]
    assert arches == ["amd64", "arm64"]


def test_build_matrix_platform_is_linux_prefixed(minimal_builds: dict) -> None:
    matrix = resolve_matrix.build_matrix(minimal_builds)
    platforms = {row["platform"] for row in matrix["include"]}
    assert platforms == {"linux/amd64", "linux/arm64"}


def test_build_matrix_rejects_unknown_cli(multi_cli_builds: dict) -> None:
    with pytest.raises(ValueError, match="not declared"):
        resolve_matrix.build_matrix(multi_cli_builds, only_cli="99.0.0")


def test_main_compact_is_single_line(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, minimal_builds: dict
) -> None:
    monkeypatch.setattr(resolve_matrix.builds, "load", lambda: minimal_builds)
    assert resolve_matrix.main([]) == 0
    out = capsys.readouterr().out
    assert out.count("\n") == 1  # exactly one trailing newline
    assert json.loads(out)  # parses


def test_main_pretty_has_indents(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, minimal_builds: dict
) -> None:
    monkeypatch.setattr(resolve_matrix.builds, "load", lambda: minimal_builds)
    assert resolve_matrix.main(["--pretty"]) == 0
    out = capsys.readouterr().out
    assert "\n  " in out  # pretty-printed


def test_main_filtered_to_one_cli(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, multi_cli_builds: dict
) -> None:
    monkeypatch.setattr(resolve_matrix.builds, "load", lambda: multi_cli_builds)
    assert resolve_matrix.main(["--stellar-cli-version", "26.0.0"]) == 0
    matrix = json.loads(capsys.readouterr().out)
    assert all(row["stellar_cli_version"] == "26.0.0" for row in matrix["include"])
