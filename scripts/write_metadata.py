#!/usr/bin/env -S uv run python
"""Write the per-arch meta-<cli>-rust<key>-<arch>.json file.

Used by the publish workflow after a successful build (digest is the
freshly-built digest passed in via --digest) and for skipped pairs
already in the registry (omit --digest and the script looks it up via
`docker buildx imagetools inspect`).
"""

import argparse
import subprocess
import sys
from pathlib import Path

from lib import builds, common, docker_inspect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True, metavar="PATH")
    parser.add_argument("--arch", required=True, metavar="ARCH")
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--image", required=True, metavar="REF")
    parser.add_argument("--rust-base-key", required=True, metavar="KEY")
    parser.add_argument("--rust-version", required=True, metavar="V")
    parser.add_argument("--tag", required=True, metavar="TAG")
    parser.add_argument(
        "--digest",
        default="",
        metavar="SHA",
        help=(
            "Per-arch image digest. If omitted, resolved from --image via docker buildx imagetools."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    digest = args.digest
    if not digest:
        try:
            digest = docker_inspect.index_digest(args.image)
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            common.die(f"could not resolve digest for {args.image}: {exc}")

    metadata = {
        "arch": args.arch,
        "digest": digest,
        "image": args.image,
        "rust_base_key": args.rust_base_key,
        "rust_version": args.rust_version,
        "stellar_cli_version": args.stellar_cli_version,
        "tag": args.tag,
    }
    builds.dump(metadata, Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
