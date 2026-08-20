"""Adapter around the `gh` CLI.

Wraps the gh subcommands the project uses (release list, release download,
pr list, attestation verify) so tests can patch one symbol per script.
"""

import json
import subprocess

from lib import runner


def list_release_tags(repo: str) -> list[str]:
    out = runner.capture(
        [
            "gh",
            "release",
            "list",
            "--repo",
            repo,
            "--json",
            "tagName",
            "--limit",
            "1000",
        ]
    )
    return [item["tagName"] for item in json.loads(out)]


def list_release_branch_tags(repo: str) -> list[str]:
    """Release tags of the `release/<tag>` branches that exist on the repo.

    A release branch is created at prepare time and persists across the
    merge -> publish gap (merging the PR doesn't publish the GitHub
    Release). Consulting it stops the tag picker from reusing an iteration
    that's already been prepared but not yet published — which would let a
    later publish overwrite the immutable `:<cli>-rust<key>-<arch>-<N>` tags.
    """
    out = runner.capture(
        [
            "gh",
            "api",
            f"repos/{repo}/git/matching-refs/heads/release/",
            "--jq",
            ".[].ref",
        ]
    )
    prefix = "refs/heads/release/"
    return [line[len(prefix) :] for line in out.splitlines() if line.startswith(prefix)]


def read_repo_file(repo: str, ref: str, path: str) -> str:
    """Fetch a file's raw contents from a repo at a git ref via the GitHub API.

    Works without a local clone or fetched tags, and honours `repo` so it
    reads from the same repository the release lives in (which may differ
    from the local checkout, e.g. a fork used for testing).
    """
    return runner.capture(
        [
            "gh",
            "api",
            f"repos/{repo}/contents/{path}?ref={ref}",
            "-H",
            "Accept: application/vnd.github.raw",
        ]
    )


def download_release_assets(repo: str, tag: str, pattern: str, dest_dir: str) -> None:
    """Download a release's assets matching a glob into dest_dir.

    `--clobber` makes re-runs idempotent; `--pattern` limits the download
    to just the files we need (e.g. `prov-*.intoto.jsonl`).
    """
    runner.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            repo,
            "--pattern",
            pattern,
            "--dir",
            dest_dir,
            "--clobber",
        ]
    )


def open_pr_for_branch(repo: str, branch: str) -> int | None:
    out = runner.capture(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            repo,
            "--head",
            branch,
            "--state",
            "open",
            "--json",
            "number",
        ]
    )
    rows = json.loads(out)
    if not rows:
        return None
    return rows[0]["number"]


def verify_attestation(
    image_ref: str,
    repo: str,
    *,
    predicate_type: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run `gh attestation verify` against an OCI image reference.

    Returns the CompletedProcess so callers can decide what to do with
    the exit code and any output (which gh writes to stderr).
    """
    cmd = ["gh", "attestation", "verify", f"oci://{image_ref}", "--repo", repo]
    if predicate_type:
        cmd += ["--predicate-type", predicate_type]
    return runner.run(cmd, check=False, capture_output=True)
