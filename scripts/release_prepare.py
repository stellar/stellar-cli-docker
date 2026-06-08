#!/usr/bin/env -S uv run python
"""Stage a new stellar-cli release into builds.json.

Delegates the builds.json mutation to refresh.py (pick rust bases, resolve the
upstream cli ref + each base's image digest, append the pins), validates the
result, fails if nothing changed, and prints the chosen GitHub Release tag as
the final stdout line.

All log output goes to stderr; stdout is just the tag.
"""

import argparse
import re
import sys

import refresh
import validate_json
from lib import builds, common, gh_cli

ITERATION_RE = re.compile(r"^v(?P<cli>[0-9]+\.[0-9]+\.[0-9]+)(?:-(?P<n>[0-9]+))?$")


def pick_release_tag(cli: str, repo: str) -> str:
    """Next available GitHub Release tag: v<cli>, or v<cli>-N for refreshes."""
    existing = gh_cli.list_release_tags(repo)
    if f"v{cli}" not in existing:
        return f"v{cli}"
    max_iter = 0
    for tag in existing:
        match = ITERATION_RE.match(tag)
        if not match or match["cli"] != cli or match["n"] is None:
            continue
        max_iter = max(max_iter, int(match["n"]))
    return f"v{cli}-{max_iter + 1}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--rust-versions", default="", metavar="CSV")
    parser.add_argument(
        "--repo",
        default="stellar/stellar-cli-docker",
        metavar="SLUG",
        help="GitHub repo for release-tag lookups (default: stellar/stellar-cli-docker)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["gh", "git", "buildx"])

    cli = args.stellar_cli_version
    before = builds.DEFAULT_PATH.read_bytes()

    common.log(f"refreshing builds.json for stellar-cli {cli} ...")
    refresh_argv = ["--stellar-cli-version", cli]
    if args.rust_versions:
        refresh_argv += ["--rust-versions", args.rust_versions]
    if refresh.main(refresh_argv) != 0:
        common.die("refresh failed; see above")

    common.log("validating builds.json ...")
    if validate_json.main([]) != 0:
        common.die("validation failed; see above")

    after = builds.DEFAULT_PATH.read_bytes()
    if before == after:
        common.die(
            f"no changes to builds.json — nothing to release. The auto-picked rust "
            f"versions and cli ref already match what's declared for stellar-cli {cli}."
        )

    release_tag = pick_release_tag(cli, args.repo)
    common.log(f"release tag: {release_tag}")
    common.log("")
    common.log(f"release-prepare: builds.json staged for stellar-cli {cli}")

    print(release_tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
