#!/usr/bin/env -S uv run python
"""Validate every *.json in the repo: sorted keys and schema.

Exits 0 if every check passes, 1 otherwise. Logs go to stderr so callers
(release_prepare.py et al.) can chain us without polluting stdout.
"""

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema

from lib import common

EXCLUDED_DIRS = {"node_modules", "target", ".git", ".venv", "tests"}


def iter_json_files(root: Path):
    for path in sorted(root.rglob("*.json")):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def has_sorted_keys(value: Any) -> bool:
    if isinstance(value, dict):
        if list(value.keys()) != sorted(value.keys()):
            return False
        return all(has_sorted_keys(v) for v in value.values())
    if isinstance(value, list):
        return all(has_sorted_keys(item) for item in value)
    return True


def sort_diff(file_text: str, sorted_text: str, rel: str) -> str:
    return "".join(
        difflib.unified_diff(
            file_text.splitlines(keepends=True),
            sorted_text.splitlines(keepends=True),
            fromfile=f"{rel} (as-is)",
            tofile=f"{rel} (sorted)",
            n=1,
        )
    )


def check_sorted_keys(root: Path) -> bool:
    ok = True
    for path in iter_json_files(root):
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text()
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            common.err(f"{rel}: invalid JSON: {exc}")
            ok = False
            continue
        if not has_sorted_keys(data):
            common.err(f"{rel}: object keys are not alphabetically sorted at every level")
            sorted_text = json.dumps(data, indent=2, sort_keys=True) + "\n"
            diff = sort_diff(text, sorted_text, rel)
            if diff:
                print(diff, file=sys.stderr, end="")
            ok = False
    return ok


def check_schema(builds_data: dict, schema: dict) -> bool:
    try:
        jsonschema.validate(builds_data, schema)
    except jsonschema.ValidationError as exc:
        common.err(f"builds.json failed JSON Schema validation: {exc.message}")
        return False
    return True


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__.splitlines()[0])


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    root = common.repo_root()
    ok = True
    ok &= check_sorted_keys(root)

    builds_path = root / "builds.json"
    schema_path = root / "builds.schema.json"
    builds_data = json.loads(builds_path.read_text())
    schema = json.loads(schema_path.read_text())

    ok &= check_schema(builds_data, schema)

    if ok:
        common.log("validate-json: all checks passed")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
