"""Thin adapter around `docker buildx imagetools`.

Wraps the docker subcommands the project relies on so tests can patch
one symbol per script. Callers go through the functions here instead
of shelling out directly.
"""

import re

from lib import common, runner

_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def index_digest(image_ref: str) -> str:
    common.reject_option_like(image_ref, "image reference")
    # `--format '{{.Manifest.Digest}}'` targets the top-level (index)
    # descriptor's digest. Some buildx releases print the bare digest while
    # others dump the whole descriptor struct, but the descriptor only ever
    # carries the single index digest (child manifests aren't included), so
    # extracting the lone sha256 is unambiguous across both forms.
    out = runner.capture(
        ["docker", "buildx", "imagetools", "inspect", image_ref, "--format", "{{.Manifest.Digest}}"]
    )
    match = _DIGEST.search(out)
    if match is None:
        raise RuntimeError(f"no digest in imagetools inspect output for {image_ref}")
    return match.group(0)


def exists(image_ref: str) -> bool:
    common.reject_option_like(image_ref, "image reference")
    result = runner.run(
        ["docker", "buildx", "imagetools", "inspect", image_ref],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def create_manifest(tag: str, *sources: str) -> None:
    if not sources:
        raise ValueError("create_manifest requires at least one source image")
    common.reject_option_like(tag, "manifest tag")
    for source in sources:
        common.reject_option_like(source, "source image")
    runner.run(["docker", "buildx", "imagetools", "create", "--tag", tag, *sources])
