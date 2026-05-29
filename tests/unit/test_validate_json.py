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


def test_check_cross_field_constraints_passes(multi_cli_builds: dict) -> None:
    assert validate_json.check_cross_field_constraints(multi_cli_builds)


def test_check_cross_field_constraints_detects_orphan(fixtures_dir: Path) -> None:
    data = json.loads((fixtures_dir / "builds_orphan_rust.json").read_text())
    assert not validate_json.check_cross_field_constraints(data)


def test_check_schema_passes_for_valid(minimal_builds: dict, fixtures_dir: Path) -> None:
    schema = json.loads((fixtures_dir.parent.parent / "builds.schema.json").read_text())
    assert validate_json.check_schema(minimal_builds, schema)


def test_check_schema_rejects_missing_required(fixtures_dir: Path) -> None:
    schema = json.loads((fixtures_dir.parent.parent / "builds.schema.json").read_text())
    broken = {"default_distro": "trixie"}  # missing rust_image_digests, stellar_cli_versions
    assert not validate_json.check_schema(broken, schema)


def test_iter_json_files_excludes_well_known_dirs(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_text("{}")
    for excluded in ("node_modules", "target", ".venv", "tests"):
        (tmp_path / excluded).mkdir()
        (tmp_path / excluded / "x.json").write_text("{}")

    found = {p.name for p in validate_json.iter_json_files(tmp_path)}
    assert found == {"a.json"}


def test_main_passes_on_real_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    # `validate_json.py` reads the actual builds.json. The repo as committed
    # must always be valid.
    assert validate_json.main([]) == 0


def test_main_fails_when_cross_field_violated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fixtures_dir: Path
) -> None:
    # Stage a fake repo root with an orphan rust_versions entry.
    (tmp_path / "builds.json").write_text((fixtures_dir / "builds_orphan_rust.json").read_text())
    (tmp_path / "builds.schema.json").write_text(
        (fixtures_dir.parent.parent / "builds.schema.json").read_text()
    )
    monkeypatch.setattr(validate_json.common, "repo_root", lambda: tmp_path)
    assert validate_json.main([]) == 1
