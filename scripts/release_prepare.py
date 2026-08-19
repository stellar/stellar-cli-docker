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
    """Next available GitHub Release tag: v<cli>-0 first, then v<cli>-1, -2, ...

    The iteration `-N` matches the immutable `:<cli>-rust<key>-<arch>-<N>` Docker
    tags one-to-one, starting at `-0` for the first release. It's picked from both published
    releases and existing `release/*` branches, so a refresh that's been
    prepared (branch/PR) but not yet published doesn't get its number reused —
    reuse would let a later publish overwrite the immutable Docker tag pinned by
    SEP-58 `bldimg` (issue #38). A grandfathered suffixless `v<cli>` tag from
    before this scheme counts as iteration 0.
    """
    existing = set(gh_cli.list_release_tags(repo)) | set(gh_cli.list_release_branch_tags(repo))
    iterations: list[int] = []
    for tag in existing:
        match = ITERATION_RE.match(tag)
        if not match or match["cli"] != cli:
            continue
        iterations.append(0 if match["n"] is None else int(match["n"]))
    if not iterations:
        return f"v{cli}-0"
    return f"v{cli}-{max(iterations) + 1}"


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
    parser.add_argument(
        "--skip-manifest-update",
        action="store_true",
        help="Do not touch builds.json; just pick a release tag for an empty-commit refresh.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cli = args.stellar_cli_version

    if args.skip_manifest_update:
        # No builds.json mutation → no docker/refresh work, just a tag for the
        # empty-commit refresh the push step will create.
        common.preflight_checks(["gh", "git"])
        if builds.find_cli(builds.load(), cli) is None:
            common.die(
                f"stellar-cli {cli} is not declared in builds.json — nothing to "
                f"republish. Run without --skip-manifest-update to stage it first."
            )
        common.log("skipping builds.json update (--skip-manifest-update)")
    else:
        common.preflight_checks(["gh", "git", "buildx"])
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
    if args.skip_manifest_update:
        common.log(f"release-prepare: builds.json left unchanged for stellar-cli {cli}")
    else:
        common.log(f"release-prepare: builds.json staged for stellar-cli {cli}")

    print(release_tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
