#!/usr/bin/env -S uv run python
"""Verify a published stellar-cli image's attestation chains.

Runs `gh attestation verify` twice against the published image (once for
SLSA build provenance, once for SPDX SBOM). Both must succeed for the
verification to pass. Intended for SEP-58 verifiers and any consumer
about to record a `bldimg` digest.
"""

import argparse
import sys

from lib import common, gh_cli

DEFAULT_REPO = "stellar/stellar-cli-docker"
PROVENANCE_PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
SBOM_PREDICATE_TYPE = "https://spdx.dev/Document"


def verify_chain(image: str, repo: str, label: str, predicate_type: str) -> bool:
    common.log("")
    common.log(label)
    result = gh_cli.verify_attestation(image, repo, predicate_type=predicate_type)
    # gh writes its output to stderr; surface it so the user sees what failed.
    if result.stdout:
        sys.stderr.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    if result.returncode == 0:
        common.log("  ok")
        return True
    common.err(f"  FAILED: {label} did not verify")
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", required=True, metavar="REF")
    parser.add_argument("--repo", default=DEFAULT_REPO, metavar="SLUG")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if "@sha256:" not in args.image:
        common.die(
            f"image must be pinned to a sha256 digest (e.g. <repo>@sha256:...); got '{args.image}'"
        )

    common.preflight_checks(["gh"])
    common.log(f"verifying {args.image} against {args.repo} ...")

    ok = True
    ok &= verify_chain(
        args.image, args.repo, "[1/2] SLSA build provenance", PROVENANCE_PREDICATE_TYPE
    )
    ok &= verify_chain(args.image, args.repo, "[2/2] SPDX SBOM", SBOM_PREDICATE_TYPE)
    common.log("")
    if ok:
        common.log(f"verify-image: {args.image} passed all attestation checks")
        return 0
    common.err(f"verify-image: {args.image} FAILED one or more attestation checks")
    return 1


if __name__ == "__main__":
    sys.exit(main())
