import json
from pathlib import Path

import pytest

import validate_json


def test_has_sorted_keys_flat() -> None:
    assert validate_json.has_sorted_keys({"a": 1, "b": 2, "c": 3})


def test_has_sorted_keys_detects_unsorted_at_root() -> None:
    assert not validate_json.has_sorted_keys({"b": 1, "a": 2})


def test_has_sorted_keys_recurses_into_nested() -> None:
    assert not validate_json.has_sorted_keys({"a": {"z": 1, "y": 2}})


def test_has_sorted_keys_recurses_into_arrays() -> None:
    assert not validate_json.has_sorted_keys({"a": [{"z": 1, "y": 2}]})


def test_has_sorted_keys_handles_primitives() -> None:
    assert validate_json.has_sorted_keys("string")
    assert validate_json.has_sorted_keys(42)
    assert validate_json.has_sorted_keys(None)


def _schema(fixtures_dir: Path) -> dict:
    return json.loads((fixtures_dir.parent.parent / "builds.schema.json").read_text())


def test_check_schema_passes_for_valid(minimal_builds: dict, fixtures_dir: Path) -> None:
    assert validate_json.check_schema(minimal_builds, _schema(fixtures_dir))


def test_check_schema_rejects_missing_required(fixtures_dir: Path) -> None:
    broken = {"default_distro": "trixie"}  # missing stellar_cli_versions
    assert not validate_json.check_schema(broken, _schema(fixtures_dir))


def test_check_schema_rejects_bare_label_entry(minimal_builds: dict, fixtures_dir: Path) -> None:
    # rust_versions entries must be fully-qualified label@sha256:<digest>.
    minimal_builds["stellar_cli_versions"][0]["rust_versions"] = ["1.94.0-slim-trixie"]
    assert not validate_json.check_schema(minimal_builds, _schema(fixtures_dir))


def test_check_schema_rejects_duplicate_entry(minimal_builds: dict, fixtures_dir: Path) -> None:
    digest = "sha256:" + "f" * 64
    minimal_builds["stellar_cli_versions"][0]["rust_versions"] = [
        f"1.94.0-slim-trixie@{digest}",
        f"1.94.0-slim-trixie@{digest}",
    ]
    assert not validate_json.check_schema(minimal_builds, _schema(fixtures_dir))


def test_check_schema_allows_two_digests(minimal_builds: dict, fixtures_dir: Path) -> None:
    # The whole point of inlining: one label may carry two distinct digests.
    minimal_builds["stellar_cli_versions"][0]["rust_versions"] = [
        "1.94.0-slim-trixie@sha256:" + "a" * 64,
        "1.94.0-slim-trixie@sha256:" + "b" * 64,
    ]
    assert validate_json.check_schema(minimal_builds, _schema(fixtures_dir))


def test_iter_json_files_excludes_well_known_dirs(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}")
    for excluded in ("node_modules", "target", ".venv", "tests"):
        (tmp_path / excluded).mkdir()
        (tmp_path / excluded / "x.json").write_text("{}")

    found = {p.name for p in validate_json.iter_json_files(tmp_path)}
    assert found == {"a.json"}


def test_iter_json_files_skips_symlinks_out_of_tree(tmp_path: Path) -> None:
    # A *.json symlink that resolves outside the repo must not be read — that
    # would turn this lint into an arbitrary-file read.
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.json"
    secret.write_text('{"z": 1, "a": 2}')  # unsorted: would fail the lint if read

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "real.json").write_text("{}")
    (repo / "evil.json").symlink_to(secret)

    found = {p.name for p in validate_json.iter_json_files(repo)}
    assert found == {"real.json"}


def test_main_passes_on_real_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    # `validate_json.py` reads the actual builds.json. The repo as committed
    # must always be valid.
    assert validate_json.main([]) == 0


def test_main_fails_on_invalid_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    # Stage a fake repo root whose builds.json has a bare (un-pinned) entry.
    (tmp_path / "builds.json").write_text((fixtures_dir / "builds_invalid_entry.json").read_text())
    (tmp_path / "builds.schema.json").write_text(
        (fixtures_dir.parent.parent / "builds.schema.json").read_text()
    )
    monkeypatch.setattr(validate_json.common, "repo_root", lambda: tmp_path)
    assert validate_json.main([]) == 1


def test_main_returns_1_on_malformed_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    # A malformed builds.json must exit 1 cleanly, not raise JSONDecodeError.
    (tmp_path / "builds.json").write_text("{ this is not valid json")
    (tmp_path / "builds.schema.json").write_text(
        (fixtures_dir.parent.parent / "builds.schema.json").read_text()
    )
    monkeypatch.setattr(validate_json.common, "repo_root", lambda: tmp_path)
    assert validate_json.main([]) == 1


def test_main_returns_1_on_missing_builds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    # A missing builds.json must exit 1 cleanly, not raise FileNotFoundError.
    (tmp_path / "builds.schema.json").write_text(
        (fixtures_dir.parent.parent / "builds.schema.json").read_text()
    )
    monkeypatch.setattr(validate_json.common, "repo_root", lambda: tmp_path)
    assert validate_json.main([]) == 1
