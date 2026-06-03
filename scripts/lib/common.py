"""Logging, exit helpers, and command preflight checks.

All log output goes to stderr so stdout stays reserved for each
script's data contract.
"""

import hashlib
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def log(message: str) -> None:
    print(message, file=sys.stderr)


def err(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)


def die(message: str) -> None:
    err(message)
    sys.exit(1)


def repo_root() -> Path:
    return REPO_ROOT


def step_summary(message: str) -> None:
    """Append a markdown block to the GitHub Actions step summary.

    No-op outside CI (when $GITHUB_STEP_SUMMARY is unset), so callers can
    invoke it unconditionally.
    """
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with open(path, "a") as f:
        f.write(message + "\n")


def require_cmd(*cmds: str) -> None:
    for cmd in cmds:
        if shutil.which(cmd) is None:
            die(f"required command not found: {cmd}")


def require_buildx() -> None:
    if shutil.which("docker") is None:
        die("docker is required (needed for buildx)")
    if subprocess.run(["docker", "buildx", "version"], capture_output=True).returncode != 0:
        die(
            "docker buildx plugin is required; install it or upgrade docker "
            "(docker buildx is the multi-arch build driver)"
        )
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        die(
            "docker daemon is not reachable; start it (e.g. start Docker Desktop / "
            "OrbStack) or check 'docker info' for details"
        )


def preflight_checks(tokens: Iterable[str] = ()) -> None:
    cmds: list[str] = []
    for token in tokens:
        if token == "buildx":
            require_buildx()
        elif token == "sha256":
            # Python's hashlib is always available; no external tool needed.
            continue
        else:
            cmds.append(token)
    if cmds:
        require_cmd(*cmds)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
