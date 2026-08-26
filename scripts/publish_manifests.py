#!/usr/bin/env -S uv run python
"""Assemble the multi-arch manifest list for each declared (cli, rust base) pair.

For one stellar-cli version, walks its rust_versions[] and runs
`docker buildx imagetools create` to assemble the multi-arch list from
the per-arch tags. Tags are mutable, so an existing list is overwritten.

Alongside each pair it also mints an *immutable*
`:<cli>-rust<key>-<arch>-<iteration>` tag per arch. `iteration` is the
release's refresh index (`v<cli>` -> 0, `v<cli>-1` -> 1, ...). The mutable
`:<cli>-rust<key>-<arch>` tag is overwritten whenever a later iteration of
the same cli republishes that pair, orphaning the digest it used to expose;
because SEP-58 verifiable builds pin that per-arch digest (`bldimg`) into
deployed contracts permanently, an orphaned (untagged) image is eligible for
registry garbage collection. The per-iteration tag keeps every published
per-arch digest referenced by at least one tag, so it never becomes
GC-eligible. See issue #38.
"""

import argparse
import sys

import tag_names
from lib import builds, common, docker_inspect


def manifest_for_pair(*, registry: str, cli: str, rust_key: str) -> tuple[str, str, str]:
    list_tag = tag_names.compose_tag(stellar_cli_version=cli, rust_version=rust_key)
    amd64_tag = tag_names.compose_tag(
        stellar_cli_version=cli, rust_version=rust_key, platform="linux/amd64"
    )
    arm64_tag = tag_names.compose_tag(
        stellar_cli_version=cli, rust_version=rust_key, platform="linux/arm64"
    )
    return (
        f"{registry}:{list_tag}",
        f"{registry}:{amd64_tag}",
        f"{registry}:{arm64_tag}",
    )


def immutable_arch_ref(*, registry: str, cli: str, rust_key: str, arch: str, iteration: int) -> str:
    """The immutable per-arch snapshot tag for a pair at a release iteration."""
    tag = tag_names.compose_tag(
        stellar_cli_version=cli, rust_version=rust_key, platform=f"linux/{arch}"
    )
    return f"{registry}:{tag}-{iteration}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--registry", default="docker.io/stellar/stellar-cli", metavar="REF")
    parser.add_argument(
        "--iteration",
        required=True,
        type=int,
        metavar="N",
        help=(
            "Release refresh index (v<cli> -> 0, v<cli>-1 -> 1, ...). "
            "Names the immutable :<cli>-rust<key>-<arch>-<N> snapshot tags."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the docker buildx imagetools create commands without running them.",
    )
    return parser


def create(tag: str, *sources: str, dry_run: bool) -> None:
    common.log(f"::group::manifest {tag} -> {' '.join(sources)}")
    if dry_run:
        common.log(f"docker buildx imagetools create --tag {tag} {' '.join(sources)}")
    else:
        docker_inspect.create_manifest(tag, *sources)
    common.log("::endgroup::")


def create_snapshot(snapshot: str, arch_ref: str, *, dry_run: bool) -> None:
    """Mint an immutable per-arch snapshot, refusing to re-point an existing one.

    The tag's whole purpose is to never move, so a re-run must not overwrite it.
    If it already exists we leave it alone when it still pins the same digest,
    and fail loudly if it points somewhere else (a real immutability violation)
    rather than silently clobbering an on-chain `bldimg` anchor.

    Under --dry-run the exists()/index_digest() lookups are skipped, so a preview
    always reports "would create" even for a snapshot that already exists.
    """
    if not dry_run and docker_inspect.exists(snapshot):
        existing = docker_inspect.index_digest(snapshot)
        current = docker_inspect.index_digest(arch_ref)
        if existing == current:
            common.log(f"skip {snapshot}: already pins {existing}")
            return
        common.die(
            f"{snapshot} already exists pinning {existing}, "
            f"but this run built {current}; refusing to re-point an immutable tag"
        )
    create(snapshot, arch_ref, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.iteration < 0:
        common.die(f"--iteration must be non-negative, got {args.iteration}")
    common.preflight_checks(["buildx"])

    data = builds.load()
    entry = builds.find_cli(data, args.stellar_cli_version)
    if entry is None:
        common.die(f"no stellar_cli_versions entry for {args.stellar_cli_version}")

    # Only the newest pin per label is published (see resolve_matrix); dedup so a
    # relabelled base doesn't re-create the same tags twice. Only the label matters
    # here, and fromkeys keeps first-seen order.
    for rust_key in dict.fromkeys(builds.label_of(pin) for pin in entry["rust_versions"]):
        list_ref, amd64_ref, arm64_ref = manifest_for_pair(
            registry=args.registry,
            cli=args.stellar_cli_version,
            rust_key=rust_key,
        )
        create(list_ref, amd64_ref, arm64_ref, dry_run=args.dry_run)

        # Immutable per-arch snapshots: keep each published digest tagged even
        # after the mutable per-arch tag is overwritten, so SEP-58 `bldimg` pins
        # stay GC-safe (issue #38).
        for arch, arch_ref in (("amd64", amd64_ref), ("arm64", arm64_ref)):
            snapshot = immutable_arch_ref(
                registry=args.registry,
                cli=args.stellar_cli_version,
                rust_key=rust_key,
                arch=arch,
                iteration=args.iteration,
            )
            create_snapshot(snapshot, arch_ref, dry_run=args.dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
