"""Adapter around the `gh` CLI.

Wraps the three gh subcommands the project uses (release list, pr list,
attestation verify) so tests can patch one symbol per script.
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
