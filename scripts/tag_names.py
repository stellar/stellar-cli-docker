#!/usr/bin/env -S uv run python
"""Compose canonical image tags from cli version, rust base key, and platform.

Tag scheme:
    multi-arch list:   <cli>-rust<key>
    per-arch:          <cli>-rust<key>-<arch>

The base image digest and stellar-cli ref stay authoritative in builds.json
(and pin the build's FROM), but they are not encoded in the published tag —
the tag is a plain, human-readable pointer. Reproducibility is anchored by the
per-arch image content digest, which is what SEP-58 `bldimg` cites.

Output: exactly one tag on stdout, with no registry/repo prefix.
"""

import argparse
import sys

from lib import common

_ARCH_FOR_PLATFORM = {
    "linux/amd64": "amd64",
    "linux/arm64": "arm64",
}

_SHORT = 15


def short_digest(digest: str) -> str:
    """First 15 hex chars of an image digest, with any `sha256:` prefix stripped."""
    return digest.removeprefix("sha256:")[:_SHORT]


def compose_tag(*, stellar_cli_version: str, rust_version: str, platform: str = "") -> str:
    tag = f"{stellar_cli_version}-rust{rust_version}"
    if platform:
        arch = _ARCH_FOR_PLATFORM.get(platform)
        if arch is None:
            raise ValueError(f"unsupported platform: {platform}")
        tag = f"{tag}-{arch}"
    return tag


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--rust-version", required=True, metavar="KEY")
    parser.add_argument("--platform", default="", metavar="P")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        tag = compose_tag(
            stellar_cli_version=args.stellar_cli_version,
            rust_version=args.rust_version,
            platform=args.platform,
        )
    except ValueError as exc:
        common.die(str(exc))
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
