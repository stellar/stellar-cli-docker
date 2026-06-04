#!/usr/bin/env -S uv run python
"""Compose the markdown body for a GitHub Release.

Reads meta-*.json files written by the publish workflow's build job
(one per (cli, rust base, arch) triple) and emits the rendered release
body to stdout.
"""

import argparse
import io
import json
import sys
from pathlib import Path

from lib import builds, common, semver


def load_metadata(metadata_dir: Path, expected_cli: str) -> list[dict]:
    files = sorted(metadata_dir.glob("meta-*.json"))
    if not files:
        raise ValueError(f"no meta-*.json files under {metadata_dir}")
    rows: list[dict] = []
    for f in files:
        row = json.loads(f.read_text())
        entry_cli = row.get("stellar_cli_version") or ""
        if not entry_cli:
            raise ValueError(f"metadata file {f} is missing the stellar_cli_version field")
        if entry_cli != expected_cli:
            raise ValueError(
                f"metadata file {f} has stellar_cli_version='{entry_cli}', "
                f"expected '{expected_cli}'"
            )
        rows.append(row)
    rows.sort(key=lambda r: (semver.parse(r["rust_version"]), r["rust_base_key"], r["arch"]))
    return rows


def list_tag(row: dict) -> str:
    """The multi-arch manifest-list tag for a row: its per-arch tag minus the arch."""
    return row["tag"].removesuffix(f"-{row['arch']}")


def pins_newest_first(rows: list[dict]) -> list[str]:
    """Unique multi-arch list tags (one per base pin), ordered by version descending."""
    seen: dict[str, tuple] = {}
    for row in rows:
        tag = list_tag(row)
        if tag not in seen:
            seen[tag] = semver.parse(row["rust_version"])
    return sorted(seen.keys(), key=lambda t: (seen[t], t), reverse=True)


def emit_body(*, cli: str, rows: list[dict], registry: str, repo: str, stellar_ref: str) -> str:
    out = io.StringIO()
    p = lambda *args: print(*args, file=out)  # noqa: E731

    p(f"# stellar-cli {cli}\n")
    p("Stellar CLI image (SEP-58-compatible image for Stellar smart contracts).\n")

    p("## Tags\n")
    p("Moving tags (re-pointed on each publish; do not use for SEP-58 `bldimg`):\n")
    p(f"- `{registry}:latest` — newest declared cli, default Rust")
    p(f"- `{registry}:{cli}` — this cli, default Rust")
    p()
    p(f"Pinned to stellar-cli `{stellar_ref}`:\n")
    for tag in pins_newest_first(rows):
        p(f"- `{registry}:{tag}` — multi-arch")
        for row in [r for r in rows if list_tag(r) == tag]:
            p(f"- `{registry}:{row['tag']}`")

    p("\n## Per-architecture digests (for SEP-58 `bldimg`)\n")
    p(
        "Use the per-architecture digest when recording `bldimg` in your contract "
        "metadata. Never use a tag — only the per-arch digest is a stable reference.\n"
    )

    for tag in pins_newest_first(rows):
        pin_rows = [r for r in rows if list_tag(r) == tag]
        key = pin_rows[0]["rust_base_key"]
        p(f"### Rust {key}\n")
        for row in pin_rows:
            p(f"- `linux/{row['arch']}`: `{registry}@{row['digest']}`")
        p("\nVerify:\n")
        p("```sh")
        for row in pin_rows:
            p(f"gh attestation verify oci://{registry}@{row['digest']} --repo {repo}")
        p()
        for row in pin_rows:
            p("cosign verify-attestation \\")
            p("  --type slsaprovenance1 \\")
            identity_re = f"https://github.com/{repo}/\\.github/workflows/.*"
            p(f'  --certificate-identity-regexp "{identity_re}" \\')
            p("  --certificate-oidc-issuer https://token.actions.githubusercontent.com \\")
            p(f"  {registry}@{row['digest']}")
        p()
        for row in pin_rows:
            p(f"docker buildx imagetools inspect {registry}@{row['digest']}")
        p("```\n")

    p(
        "## Verification\n\n"
        "Each per-architecture image carries two independent attestation chains — "
        "SLSA build provenance and SPDX SBOM — signed by this repo's GitHub Actions "
        "OIDC identity. The per-Rust `Verify:` blocks above are copy-paste-runnable "
        "for every published image across three tools:\n\n"
        "- `gh attestation verify` — checks every attestation chain in one call (recommended).\n"
        "- `cosign verify-attestation` — registry-attached verification with explicit "
        "certificate identity + OIDC issuer flags so trust is anchored to this repo's "
        'workflows, not just "any valid Sigstore signature".\n'
        "- `docker buildx imagetools inspect` — manifest + attached attestation "
        "metadata, useful for inspection (not signature verification).\n\n"
        "Verification requires a per-architecture reference (digest or per-arch tag). "
        f"Verifying against `:latest`, `:{cli}`, or the multi-arch list tag fails because "
        "those resolve to the manifest list digest, which isn't what the per-arch "
        "attestations were signed against.\n\n"
        "## Assets\n\n"
        "This release attaches one SBOM file (`.spdx.json`) and one provenance bundle "
        "(`.intoto.jsonl`) per per-architecture image."
    )

    return out.getvalue()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--metadata-dir", required=True, metavar="PATH")
    parser.add_argument("--registry", default="docker.io/stellar/stellar-cli", metavar="REF")
    parser.add_argument("--repo", default="stellar/stellar-cli-docker", metavar="SLUG")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    metadata_dir = Path(args.metadata_dir)
    if not metadata_dir.is_dir():
        common.die(f"{metadata_dir} is not a directory")

    try:
        rows = load_metadata(metadata_dir, args.stellar_cli_version)
        stellar_ref = builds.stellar_cli_ref(builds.load(), args.stellar_cli_version)
    except ValueError as exc:
        common.die(str(exc))

    body = emit_body(
        cli=args.stellar_cli_version,
        rows=rows,
        registry=args.registry,
        repo=args.repo,
        stellar_ref=stellar_ref,
    )
    sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    sys.exit(main())
