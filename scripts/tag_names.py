#!/usr/bin/env -S uv run python
"""Compose canonical image tags from cli version, rust base key, base image
digest, optional platform, and optional stellar-cli git ref.

Tag scheme:
    multi-arch list:   <cli>[-<ref15>]-rust<key>-<digest15>
    per-arch:          <cli>[-<ref15>]-rust<key>-<digest15>-<arch>

`ref15`/`digest15` are the first 15 hex chars of the stellar-cli git ref
and of the rust base image digest (the `sha256:` algorithm prefix stripped).
Both full values stay authoritative in builds.json; the tag carries short
fragments so each (cli, ref, base label, base digest) resolves to a distinct,
immutable tag without blowing the 128-char tag limit.

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


def _short_ref(ref: str) -> str:
    return ref[:_SHORT]


def _short_digest(digest: str) -> str:
    return digest.removeprefix("sha256:")[:_SHORT]


def compose_tag(
    *,
    stellar_cli_version: str,
    rust_version: str,
    rust_image_digest: str,
    platform: str = "",
    stellar_cli_ref: str = "",
) -> str:
    tag = stellar_cli_version
    if stellar_cli_ref:
        tag = f"{tag}-{_short_ref(stellar_cli_ref)}"
    tag = f"{tag}-rust{rust_version}"
    tag = f"{tag}-{_short_digest(rust_image_digest)}"
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
    parser.add_argument("--rust-image-digest", required=True, metavar="DIGEST")
    parser.add_argument("--platform", default="", metavar="P")
    parser.add_argument("--stellar-cli-ref", default="", metavar="SHA")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        tag = compose_tag(
            stellar_cli_version=args.stellar_cli_version,
            rust_version=args.rust_version,
            rust_image_digest=args.rust_image_digest,
            platform=args.platform,
            stellar_cli_ref=args.stellar_cli_ref,
        )
    except ValueError as exc:
        common.die(str(exc))
    print(tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
