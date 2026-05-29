#!/usr/bin/env -S uv run python
"""Commit the staged builds.json and push the release branch.

Refuses to clobber an in-progress review PR; force-pushes orphan branches
left over from a prior failed run; pushes fresh otherwise.
"""

import argparse
import sys

from lib import common, gh_cli, runner


def remote_branch_exists(branch: str) -> bool:
    result = runner.run(
        ["git", "ls-remote", "--exit-code", "--heads", "origin", branch],
        check=False,
        capture_output=True,
    )
    return result.returncode == 0


def commit_and_push(release_tag: str, repo: str) -> int:
    branch = f"release/{release_tag}"
    runner.run(["git", "add", "builds.json"])
    runner.run(["git", "commit", "-m", f"Release {release_tag}."])

    force = False
    if remote_branch_exists(branch):
        try:
            open_pr = gh_cli.open_pr_for_branch(repo, branch)
        except Exception:
            print(
                f"::error::failed to check for open PRs on {branch} — refusing to push",
                file=sys.stderr,
            )
            return 1
        if open_pr is not None:
            print(
                f"::error::{branch} already has an open PR (#{open_pr}). "
                "Close it or pick a different version.",
                file=sys.stderr,
            )
            return 1
        print(
            f"::warning::{branch} exists on remote with no open PR "
            "(orphan from a prior failed run); force-pushing.",
            file=sys.stderr,
        )
        force = True

    cmd = ["git", "push"]
    if force:
        cmd.append("--force")
    cmd += ["origin", branch]
    runner.run(cmd)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release-tag", required=True, metavar="TAG")
    parser.add_argument(
        "--repo",
        default="stellar/stellar-cli-docker",
        metavar="SLUG",
        help="GitHub repo for open-PR lookups (default: stellar/stellar-cli-docker)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["gh", "git"])
    return commit_and_push(args.release_tag, args.repo)


if __name__ == "__main__":
    sys.exit(main())
