#!/usr/bin/env -S uv run python
"""Print one field of the newest stellar_cli_versions[] entry in builds.json.

Sorts numerically by `[MAJOR, MINOR, PATCH]` so 1.100.0 ranks above 1.99.0
regardless of array order — a backported entry cannot displace a higher
semver release.
"""

import argparse
import sys

from lib import builds, common, semver


def newest_cli(data: dict) -> str:
    versions = [entry["version"] for entry in data.get("stellar_cli_versions", [])]
    if not versions:
        raise ValueError("builds.json has no stellar_cli_versions")
    return semver.sort_versions(versions)[-1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stellar-cli-version", dest="mode", action="store_const", const="cli")
    mode.add_argument("--rust-version", dest="mode", action="store_const", const="rust")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    data = builds.load()
    try:
        cli = newest_cli(data)
        if args.mode == "cli":
            print(cli)
        else:
            print(builds.derive_default_rust(data, cli))
    except ValueError as exc:
        common.die(str(exc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
