"""Adapter around the `gh` CLI.

Wraps the gh subcommands the project uses (release list, matching-refs,
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

    A release branch is created at prepare time and lives while its release PR
    is open. Consulting it stops the tag picker from reusing an iteration that's
    been prepared (branch/PR open) but not yet released — which would let a
    later publish overwrite the immutable `:<cli>-rust<key>-<arch>-<N>` tags.

    The repo auto-deletes the branch on merge, so this covers the review window
    (prepare -> merge); the normal flow publishes the GitHub Release right after
    merge, so the brief merge -> publish gap isn't separately guarded here.
    """
    out = runner.capture(
        [
            "gh",
            "api",
            f"repos/{repo}/git/matching-refs/heads/release/",
            # matching-refs is paginated (30/page); --paginate walks every page
            # so a large backlog of prepared release branches can't hide one and
            # let its reserved iteration be reused.
            "--paginate",
            "--jq",
            ".[].ref",
        ]
    )
    prefix = "refs/heads/release/"
    return [line[len(prefix) :] for line in out.splitlines() if line.startswith(prefix)]


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
