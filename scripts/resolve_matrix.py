#!/usr/bin/env -S uv run python
"""Read builds.json and emit a `{"include": [...]}` matrix for `fromJson()`.

Per stellar-cli entry, per rust base key, per arch, emits one row with
everything the build job needs. Output defaults to compact single-line
JSON so `$GITHUB_OUTPUT` encoding stays valid.
"""

import argparse
import json
import sys

import tag_names
from lib import builds, common, rust_keys

ARCHES = ("amd64", "arm64")


def build_matrix(data: dict, only_cli: str = "") -> dict:
    if only_cli and builds.find_cli(data, only_cli) is None:
        raise ValueError(f"stellar-cli {only_cli} is not declared in builds.json")

    rows = []
    for entry in data.get("stellar_cli_versions", []):
        cli = entry["version"]
        if only_cli and cli != only_cli:
            continue
        ref = entry["ref"]
        for pin in entry["rust_versions"]:
            label, digest = builds.split_entry(pin)
            parsed = rust_keys.parse(label)
            rust_base_id = f"{label}-{tag_names.short_digest(digest)}"
            for arch in ARCHES:
                rows.append(
                    {
                        "arch": arch,
                        "platform": f"linux/{arch}",
                        "rust_base_id": rust_base_id,
                        "rust_base_key": label,
                        "rust_base_suffix": parsed.suffix,
                        "rust_image_digest": digest,
                        "rust_version": parsed.version,
                        "stellar_cli_ref": ref,
                        "stellar_cli_version": cli,
                    }
                )
    return {"include": rows}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", default="", metavar="V")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--compact", dest="mode", action="store_const", const="compact")
    mode.add_argument("--pretty", dest="mode", action="store_const", const="pretty")
    parser.set_defaults(mode="compact")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data = builds.load()
    try:
        matrix = build_matrix(data, only_cli=args.stellar_cli_version)
    except ValueError as exc:
        common.die(str(exc))
    if args.mode == "compact":
        print(json.dumps(matrix, separators=(",", ":"), sort_keys=True))
    else:
        print(json.dumps(matrix, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
