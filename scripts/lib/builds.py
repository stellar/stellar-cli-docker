"""Read, write, and query builds.json.

On-disk format: keys sorted at every level, 2-space indent, trailing
newline. Writes go through `dump()` which writes to a tempfile in the
same directory and then `os.replace()`s into place so a partially-
written file never lands.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from lib import rust_keys, semver

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_PATH = REPO_ROOT / "builds.json"


def load(path: Path | None = None) -> dict[str, Any]:
    target = path or DEFAULT_PATH
    return json.loads(target.read_text())


def dump(data: dict[str, Any], path: Path | None = None) -> None:
    target = path or DEFAULT_PATH
    encoded = json.dumps(data, indent=2, sort_keys=True) + "\n"
    parent = target.parent
    fd, tmp_name = tempfile.mkstemp(prefix=".builds.", suffix=".json", dir=parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(encoded)
        os.replace(tmp_name, target)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def find_cli(data: dict[str, Any], version: str) -> dict[str, Any] | None:
    for entry in data.get("stellar_cli_versions", []):
        if entry.get("version") == version:
            return entry
    return None


def stellar_cli_ref(data: dict[str, Any], version: str) -> str:
    entry = find_cli(data, version)
    if entry is None or not entry.get("ref"):
        raise ValueError(f"no stellar_cli_versions entry for version: {version}")
    return entry["ref"]


def rust_image_digest(data: dict[str, Any], rust_key: str) -> str:
    digest = data.get("rust_image_digests", {}).get(rust_key)
    if not digest:
        raise ValueError(f"no rust_image_digests entry for rust base key: {rust_key}")
    return digest


def assert_pair_declared(data: dict[str, Any], cli: str, rust_key: str) -> None:
    entry = find_cli(data, cli)
    if entry is None or rust_key not in entry.get("rust_versions", []):
        raise ValueError(
            f"stellar-cli {cli} is not declared with rust base key {rust_key} in builds.json"
        )


def derive_default_rust(data: dict[str, Any], cli: str) -> str:
    distro = data.get("default_distro")
    if not distro:
        raise ValueError("builds.json is missing default_distro")
    suffix = f"slim-{distro}"
    entry = find_cli(data, cli)
    if entry is None:
        raise ValueError(f"unknown stellar-cli version: {cli}")
    matches = [k for k in entry.get("rust_versions", []) if k.endswith(f"-{suffix}")]
    if not matches:
        raise ValueError(
            f"no rust_versions[] key matches default_distro {distro!r} "
            f"(suffix {suffix!r}) for stellar-cli {cli}"
        )
    matches.sort(key=lambda k: semver.parse(rust_keys.version_of(k)))
    return matches[-1]
