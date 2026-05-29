#!/usr/bin/env -S uv run python
"""Re-resolve each rust_image_digests entry's upstream multi-arch index digest.

Only fills entries whose digest is blank/unpinned; bumping a pinned digest
must be requested per key via --rust-version. Mirrors the refresh-fills-blanks
contract from the bash predecessor.
"""

import argparse
import re
import sys

from lib import builds, common, docker_inspect

_PINNED = re.compile(r"^sha256:[0-9a-f]{64}$")


def unpinned_keys(data: dict) -> list[str]:
    return [
        key
        for key, value in data.get("rust_image_digests", {}).items()
        if not _PINNED.match(value or "")
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rust-version", default="", metavar="KEY")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["buildx"])
    data = builds.load()
    digests = data.setdefault("rust_image_digests", {})

    if args.rust_version:
        if args.rust_version not in digests:
            common.die(
                f"rust base key {args.rust_version} is not a key in builds.json rust_image_digests"
            )
        keys = [args.rust_version]
    else:
        keys = unpinned_keys(data)
        if not keys:
            common.log("all rust_image_digests entries are already pinned; nothing to do.")
            common.log("to re-resolve a specific one, pass --rust-version <key>.")
            return 0

    updates: dict[str, str] = {}
    for key in keys:
        common.log(f"resolving rust:{key} ...")
        digest = docker_inspect.index_digest(f"rust:{key}")
        if not digest:
            common.die(f"empty digest returned for rust:{key}")
        common.log(f"  -> {digest}")
        updates[key] = digest

    if args.dry_run:
        common.log("(dry-run; not writing builds.json)")
        return 0

    digests.update(updates)
    builds.dump(data)
    common.log(f"wrote {' '.join(updates.keys())} to {builds.DEFAULT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
