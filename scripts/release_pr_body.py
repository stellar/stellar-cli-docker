#!/usr/bin/env -S uv run python
"""Compose the title and body for the release-staging pull request.

Differentiates a fresh release (e.g. v26.1.0) from a refresh iteration
(e.g. v26.0.0-1) so the PR title and "What" section read naturally for
either case.
"""

import argparse
import sys


def compose(
    *,
    version: str,
    release_tag: str,
    actor: str,
    repo: str,
    run_url: str,
    default_branch: str,
) -> tuple[str, str]:
    iteration = "-" in release_tag.removeprefix("v")
    if iteration:
        title = f"Refresh stellar-cli {version} ({release_tag.removeprefix('v')})"
        kind = "refresh"
    else:
        title = f"Release stellar-cli {version}"
        kind = "new release"

    body = (
        "### What\n\n"
        f"Stage a {kind} for stellar-cli {version}. `builds.json` is updated with "
        "the rust base pins auto-picked from the current last two minor stable "
        "releases on `rust-lang/rust`; each pin resolves the upstream base image "
        "digest at append time (`<label>@sha256:<digest>`).\n\n"
        "### Why\n\n"
        f"Triggered by @{actor} in {run_url}.\n\n"
        "### What is next\n\n"
        "See [RELEASE.md](./RELEASE.md) for the full release process.\n\n"
        f"Push any further changes to the `release/{release_tag}` branch that "
        "are needed in this release (for example, adjusting the paired "
        "`rust_versions` if the auto-pick isn't right for this iteration).\n\n"
        "When this PR is reviewed and merged, create a GitHub Release by going to:\n\n"
        f"https://github.com/{repo}/releases/new?tag={release_tag}"
        f"&title={release_tag.removeprefix('v')}&target={default_branch}\n\n"
        "The publish workflow fires on the release-published event and:\n"
        "- Builds and pushes per-arch images for any new (cli, rust base) pairs; "
        "existing pairs are skipped with a warning (per-arch tags are immutable)\n"
        "- Generates SLSA build provenance + SPDX SBOM attestations on each "
        "newly-built image (buildx-native + GitHub-native chains)\n"
        f"- Re-points the `:{version}` and (if newest) `:latest` aliases\n"
        "- Attaches the SBOM and provenance files to the new GitHub Release, "
        "with per-arch digests in the body"
    )
    return title, body


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--release-tag", required=True, metavar="TAG")
    parser.add_argument("--actor", required=True, metavar="LOGIN")
    parser.add_argument("--repo", required=True, metavar="SLUG")
    parser.add_argument("--run-url", required=True, metavar="URL")
    parser.add_argument("--default-branch", required=True, metavar="BRANCH")
    parser.add_argument(
        "--field",
        choices=("title", "body"),
        default="body",
        help="Which composed field to print (default: body).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    title, body = compose(
        version=args.stellar_cli_version,
        release_tag=args.release_tag,
        actor=args.actor,
        repo=args.repo,
        run_url=args.run_url,
        default_branch=args.default_branch,
    )
    sys.stdout.write(title if args.field == "title" else body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
