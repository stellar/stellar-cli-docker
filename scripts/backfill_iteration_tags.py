#!/usr/bin/env -S uv run python
"""Backfill immutable per-arch `:<cli>-rust<key>-<arch>-<iteration>` tags.

Every published per-arch image is a SEP-58 `bldimg` anchor: deployed contracts
pin its content digest permanently (issue #38). But the tags that expose those
digests are mutable — `:<cli>-rust<key>-<arch>` is overwritten whenever a later
iteration of the same cli republishes that pair, and `:<cli>` / `:latest` move
on every publish. Once overwritten, the old digest is untagged and eligible for
registry garbage collection, which breaks on-chain reproducibility.

The publish workflow now mints an immutable `:<cli>-rust<key>-<arch>-<iteration>`
tag per released image (see `scripts/publish_manifests.py`). This one-shot script
reconstructs those tags for releases that predate that change, while the orphaned
digests still exist in the registry.

For each release iteration of the given cli (`v<cli>` -> 0, `v<cli>-<N>` -> N):
  1. Read that release's builds.json snapshot at its git tag (from `--repo` via
     the GitHub API, so no local clone or fetched tags are needed) to enumerate
     the (rust base, arch) pairs it published — the newest pin per label, exactly
     what the build matrix built.
  2. Download each pair's `prov-*.intoto.jsonl` assets and recover the per-arch
     content digests from each attestation's subject. `meta-*.json` only ever
     lives as a 7-day workflow artifact — it is never attached to the release —
     so the SEP-58-relevant digests are read from the provenance bundles, which
     the publish workflow does upload to the release permanently.
  3. `docker buildx imagetools create` an immutable
     `:<cli>-rust<key>-<arch>-<iteration>` tag for each digest, re-referencing it
     so it is no longer untagged.

Per-arch tags that already exist are skipped, so the script is safe to re-run.
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import tag_names
from lib import builds, common, docker_inspect, gh_cli

# Fixed arch order so the work (and its logs) are deterministic.
ARCHES = ("amd64", "arm64")


def iterations_for_cli(tags: list[str], cli: str) -> list[tuple[str, int]]:
    """Release (tag, iteration) pairs for one cli, ordered by iteration.

    `v<cli>` is iteration 0; `v<cli>-<N>` is iteration N. Tags for other
    cli versions (and non-`v` tags) are ignored. The `<cli>-` prefix match
    is exact — `25.1.0` never swallows `25.1.05`.
    """
    found: list[tuple[str, int]] = []
    for tag in tags:
        if not tag.startswith("v"):
            continue
        rest = tag[1:]
        if rest == cli:
            found.append((tag, 0))
        elif rest.startswith(f"{cli}-"):
            suffix = rest[len(cli) + 1 :]
            if suffix.isdigit():
                found.append((tag, int(suffix)))
    return sorted(found, key=lambda pair: pair[1])


def load_builds_at_ref(repo: str, ref: str) -> dict:
    """Parse builds.json as it stood at a repo's git ref (e.g. a release tag)."""
    return json.loads(gh_cli.read_repo_file(repo, ref, "builds.json"))


def latest_pins_by_label(entry: dict) -> dict[str, str]:
    """The newest pin per rust base label — the pairs the build matrix built.

    Mirrors `resolve_matrix.build_matrix`: builds.json keeps superseded pins as
    history but only the last occurrence of each label is published, so only its
    assets exist on the release.
    """
    return {builds.label_of(pin): pin for pin in entry.get("rust_versions", [])}


def rust_base_id(pin: str) -> str:
    """The `<label>-<short-digest>` id the publish workflow bakes into asset names.

    Matches `resolve_matrix.build_matrix`, so `prov-<cli>-rust<id>-<arch>.intoto.jsonl`
    resolves to the assets actually uploaded for this pair.
    """
    label, digest = builds.split_entry(pin)
    return f"{label}-{tag_names.short_digest(digest)}"


def prov_pattern(cli: str, base_id: str) -> str:
    """Glob for both arch provenance bundles of one (cli, rust base) pair."""
    return f"prov-{cli}-rust{base_id}-*.intoto.jsonl"


def subject_digest(path: Path) -> str:
    """The image digest attested by a `prov-*.intoto.jsonl` bundle's subject.

    The in-toto statement is base64-encoded inside the DSSE envelope; its lone
    subject is the per-arch image the publish workflow pushed and attested.
    """
    envelope = json.loads(path.read_text())
    statement = json.loads(base64.b64decode(envelope["dsseEnvelope"]["payload"]))
    return f"sha256:{statement['subject'][0]['digest']['sha256']}"


def digests_by_arch(directory: Path, cli: str, base_id: str) -> dict[str, str]:
    """`arch -> sha256:...` recovered from each provenance bundle present."""
    out: dict[str, str] = {}
    for arch in ARCHES:
        path = directory / f"prov-{cli}-rust{base_id}-{arch}.intoto.jsonl"
        if path.exists():
            out[arch] = subject_digest(path)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--registry", default="docker.io/stellar/stellar-cli", metavar="REF")
    parser.add_argument("--repo", default="stellar/stellar-cli-docker", metavar="SLUG")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without touching the registry.",
    )
    return parser


def backfill_pair(
    *,
    repo: str,
    tag: str,
    iteration: int,
    cli: str,
    label: str,
    pin: str,
    registry: str,
    dry_run: bool,
) -> int:
    """Reconstruct the missing per-arch immutable tags for one (cli, rust) pair.

    Returns the number of arches that could not be reconstructed (0 on success).
    """
    targets = {
        arch: f"{registry}:{cli}-rust{label}-{arch}-{iteration}" for arch in ARCHES
    }
    pending: dict[str, str] = {}
    for arch, target in targets.items():
        if docker_inspect.exists(target):
            common.log(f"skip {target}: already tagged")
        else:
            pending[arch] = target
    if not pending:
        return 0

    base_id = rust_base_id(pin)
    try:
        with tempfile.TemporaryDirectory(prefix="backfill-prov-") as tmp:
            gh_cli.download_release_assets(repo, tag, prov_pattern(cli, base_id), tmp)
            digests = digests_by_arch(Path(tmp), cli, base_id)
    except (subprocess.CalledProcessError, RuntimeError, ValueError, KeyError) as exc:
        common.err(f"{tag}: cannot read prov-*.intoto.jsonl for pair '{label}': {exc}")
        return len(pending)

    failures = 0
    for arch, target in pending.items():
        digest = digests.get(arch)
        if digest is None:
            common.err(f"{tag}: no prov bundle for pair '{label}' arch '{arch}'")
            failures += 1
            continue
        source = f"{registry}@{digest}"
        common.log(f"::group::backfill {target} -> {source}")
        if dry_run:
            common.log(f"docker buildx imagetools create --tag {target} {source}")
        else:
            docker_inspect.create_manifest(target, source)
        common.log("::endgroup::")
    return failures


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["buildx", "gh"])

    cli = args.stellar_cli_version
    registry = args.registry

    tags = gh_cli.list_release_tags(args.repo)
    iterations = iterations_for_cli(tags, cli)
    if not iterations:
        common.die(f"no published releases found for stellar-cli {cli}")

    failures = 0
    for tag, iteration in iterations:
        try:
            snapshot = load_builds_at_ref(args.repo, tag)
            entry = builds.find_cli(snapshot, cli)
            if entry is None:
                raise ValueError(f"builds.json at {tag} declares no stellar-cli {cli}")
            pins = latest_pins_by_label(entry)
            if not pins:
                raise ValueError(f"builds.json at {tag} declares no rust_versions[] for {cli}")
        except (ValueError, RuntimeError) as exc:
            common.err(f"{tag}: cannot enumerate published pairs: {exc}")
            failures += 1
            continue

        for label, pin in sorted(pins.items()):
            failures += backfill_pair(
                repo=args.repo,
                tag=tag,
                iteration=iteration,
                cli=cli,
                label=label,
                pin=pin,
                registry=registry,
                dry_run=args.dry_run,
            )

    if failures:
        common.die(f"{failures} per-arch tag(s) could not be backfilled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
