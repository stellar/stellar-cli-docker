#!/usr/bin/env -S uv run python
"""Re-resolve each stellar_cli_versions[].ref by asking upstream git for the tag.

Only fills entries whose ref is blank or not a valid 40-hex SHA; bumping a
pinned ref must be requested per version via --stellar-cli-version.
"""

import argparse
import re
import sys

from lib import builds, common, git_remote

STELLAR_CLI_REPO = "https://github.com/stellar/stellar-cli.git"

_PINNED = re.compile(r"^[0-9a-f]{40}$")


def unpinned_versions(data: dict) -> list[str]:
    return [
        entry["version"]
        for entry in data.get("stellar_cli_versions", [])
        if not _PINNED.match(entry.get("ref") or "")
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", default="", metavar="V")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["git"])
    data = builds.load()

    if args.stellar_cli_version:
        if builds.find_cli(data, args.stellar_cli_version) is None:
            common.die(
                f"stellar-cli version {args.stellar_cli_version} is not declared in builds.json"
            )
        versions = [args.stellar_cli_version]
    else:
        versions = unpinned_versions(data)
        if not versions:
            common.log("all stellar_cli_versions entries are already pinned; nothing to do.")
            common.log("to re-resolve a specific one, pass --stellar-cli-version <v>.")
            return 0

    resolved: dict[str, str] = {}
    for version in versions:
        common.log(f"resolving stellar-cli v{version} -> commit SHA ...")
        sha = git_remote.resolve_tag_commit(STELLAR_CLI_REPO, f"v{version}")
        if not sha:
            common.die(f"could not resolve tag v{version} in {STELLAR_CLI_REPO}")
        common.log(f"  -> {sha}")
        resolved[version] = sha

    if args.dry_run:
        common.log("(dry-run; not writing builds.json)")
        return 0

    for entry in data["stellar_cli_versions"]:
        if entry["version"] in resolved:
            entry["ref"] = resolved[entry["version"]]
    builds.dump(data)
    common.log(f"wrote {' '.join(resolved.keys())} to {builds.DEFAULT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
