"""Thin adapter around `docker buildx imagetools`.

Wraps the docker subcommands the project relies on so tests can patch
one symbol per script. Callers go through the functions here instead
of shelling out directly.
"""

import re

from lib import runner

_DIGEST_LINE = re.compile(r"^Digest:\s*(\S+)\s*$", re.MULTILINE)


def index_digest(image_ref: str) -> str:
    # `--format '{{.Manifest.Digest}}'` behaves inconsistently across
    # amd64/arm64 buildx releases (one prints the digest, the other dumps
    # the full manifest), so we parse the verbose output's "Digest:" line
    # which is identical on both.
    out = runner.capture(["docker", "buildx", "imagetools", "inspect", image_ref])
    match = _DIGEST_LINE.search(out)
    if match is None:
        raise RuntimeError(f"no Digest line in imagetools inspect output for {image_ref}")
    return match.group(1)


def exists(image_ref: str) -> bool:
    result = runner.run(
        ["docker", "buildx", "imagetools", "inspect", image_ref],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def create_manifest(tag: str, *sources: str) -> None:
    if not sources:
        raise ValueError("create_manifest requires at least one source image")
    runner.run(["docker", "buildx", "imagetools", "create", "--tag", tag, *sources])
