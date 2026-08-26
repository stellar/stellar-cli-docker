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
reconstructs those tags for releases that predate that change.

It sources the per-arch digests straight from the registry's *current* tag
state, not from release provenance. Two reasons:

  1. The OCI/Docker Hub API cannot list untagged manifests, so the only digests
     that can still be protected are the ones a live tag points at right now.
     Anything already orphaned is unrecoverable — but nothing motivating this
     change is orphaned yet, only at risk of being orphaned by a future publish.
  2. It sidesteps releases whose provenance was never published. v25.1.0 and
     v25.2.0 — the releases issue #38 is about — both had publish runs that
     failed after pushing the per-arch images but before the provenance step, so
     no `prov-*.intoto.jsonl` exists, yet the images remain tagged and their
     digests are recoverable here.

For the given cli:
  1. Resolve iteration `N` — the highest `v<cli>[-N]` release tag, or an explicit
     `--iteration`. The mutable per-arch tags reflect that newest iteration's
     content, which is all the registry still exposes (superseded iterations were
     orphaned when overwritten and cannot be recovered). Auto-resolving assumes
     the newest release's publish reached the build+push step; if it failed
     *before* pushing images the live tags still hold an earlier iteration's
     content, so pass `--iteration <N>` to label it correctly instead of
     mislabeling it as the newest N.
  2. Read the index digest each current `:<cli>-rust<key>-<arch>` tag exposes
     (the tag's own top-level digest — the same `bldimg` anchor the publish
     workflow records, not the child per-platform submanifest).
  3. `docker buildx imagetools create` an immutable `:<cli>-rust<key>-<arch>-<N>`
     tag for each digest, re-referencing it so it can no longer become untagged.

A snapshot tag that already pins the same digest is skipped, so the script is
safe to re-run; one that exists pinning a *different* digest fails loudly rather
than being silently clobbered — that would be an immutability violation.
"""

import argparse
import re
import sys

from lib import common, docker_inspect, dockerhub, gh_cli

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


def latest_iteration(tags: list[str], cli: str) -> int | None:
    """The newest release iteration for a cli, or None if it has no releases.

    The mutable per-arch tags reflect the newest iteration that reached the
    build+push step, so its index is the one the recovered digests belong to.
    """
    iterations = iterations_for_cli(tags, cli)
    if not iterations:
        return None
    return max(iteration for _, iteration in iterations)


def _per_arch_tag_re(cli: str) -> re.Pattern[str]:
    """Matches a mutable per-arch tag `:<cli>-rust<key>-<arch>` for this cli.

    The immutable snapshots (`…-<arch>-<N>`) end in a digit and the multi-arch
    list tags (`…-rust<key>`) have no arch suffix, so neither is matched here.
    """
    arches = "|".join(ARCHES)
    return re.compile(rf"^{re.escape(cli)}-rust(?P<key>.+)-(?P<arch>{arches})$")


def _arch_digest(tag_obj: dict, arch: str) -> str | None:
    """The index digest a per-arch Hub tag exposes — the `bldimg` anchor.

    A per-arch tag `:<cli>-rust<key>-<arch>` is a single-platform build, but with
    attestations enabled buildx pushes it as an *index* (the real linux/<arch>
    image plus an `unknown/unknown` attestation manifest). The digest the rest of
    the system records as `bldimg` — `write_metadata` / `release_body` / the
    natively-minted snapshots — is that index's top-level digest
    (`docker_inspect.index_digest`, i.e. `{{.Manifest.Digest}}`), which the Hub
    tag record exposes as the tag's own `digest` field. The per-platform
    `images[].digest` is the child submanifest one level down, which is NOT what
    contracts pin, so pinning it would both diverge from natively-published tags
    and fail to keep the parent index reachable. Confirm the tag really carries
    the expected linux/<arch> image (and isn't attestation-only) before trusting
    it, then return the tag's own digest.

    This also handles a plain (non-attestation) per-arch manifest: there the
    top-level `digest` and the sole `images[].digest` coincide.
    """
    has_arch = any(
        image.get("architecture") == arch and image.get("os") == "linux"
        for image in tag_obj.get("images", [])
    )
    if not has_arch:
        return None
    return tag_obj.get("digest") or None


def current_pairs(tags: list[dict], cli: str) -> dict[tuple[str, str], str]:
    """`(rust key, arch) -> digest` for every per-arch tag the repo exposes now."""
    pattern = _per_arch_tag_re(cli)
    pairs: dict[tuple[str, str], str] = {}
    for tag_obj in tags:
        match = pattern.match(tag_obj.get("name", ""))
        if match is None:
            continue
        arch = match.group("arch")
        digest = _arch_digest(tag_obj, arch)
        if digest:
            pairs[(match.group("key"), arch)] = digest
    return pairs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--registry", default="docker.io/stellar/stellar-cli", metavar="REF")
    parser.add_argument("--repo", default="stellar/stellar-cli-docker", metavar="SLUG")
    parser.add_argument(
        "--iteration",
        type=int,
        metavar="N",
        help=(
            "Iteration index to label the recovered snapshots with. Defaults to "
            "the highest v<cli>[-N] release tag. Override when the newest "
            "release's publish failed before pushing images, so the live per-arch "
            "tags still hold an earlier iteration's content."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without touching the registry.",
    )
    return parser


def resolve_iteration(args: argparse.Namespace, cli: str) -> int:
    """The iteration index to label recovered snapshots with.

    An explicit `--iteration` wins. Otherwise it's the newest `v<cli>[-N]`
    release, which assumes that release's publish reached build+push so the live
    per-arch tags hold its content — a loud warning flags the assumption so an
    operator recovering from a publish that failed before pushing knows to pass
    `--iteration <N>` instead of mislabeling an earlier iteration as the newest.
    """
    if args.iteration is not None:
        return args.iteration
    iteration = latest_iteration(gh_cli.list_release_tags(args.repo), cli)
    if iteration is None:
        common.die(f"no published releases found for stellar-cli {cli}")
    common.log(
        f"labeling recovered snapshots as iteration {iteration} (newest "
        f"v{cli}[-N] release); this assumes that release's publish pushed its "
        f"per-arch images. If it failed before the build/push step, the live "
        f"tags still hold an earlier iteration — re-run with --iteration <N> to "
        f"pin the correct one."
    )
    return iteration


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.iteration is not None and args.iteration < 0:
        common.die(f"--iteration must be non-negative, got {args.iteration}")
    common.preflight_checks(["buildx", "gh"])

    cli = args.stellar_cli_version
    registry = args.registry

    iteration = resolve_iteration(args, cli)

    repo_path = dockerhub.repo_path(registry)
    pairs = current_pairs(dockerhub.list_tags(repo_path), cli)
    if not pairs:
        common.die(f"no per-arch tags found for stellar-cli {cli} on {repo_path}")

    created = 0
    skipped = 0
    for (key, arch), digest in sorted(pairs.items()):
        target = f"{registry}:{cli}-rust{key}-{arch}-{iteration}"
        source = f"{registry}@{digest}"
        if docker_inspect.exists(target):
            existing = docker_inspect.index_digest(target)
            if existing == digest:
                common.log(f"skip {target}: already pins {digest}")
                skipped += 1
                continue
            common.die(
                f"{target} already exists pinning {existing}, but the live "
                f"per-arch tag now exposes {digest}; refusing to re-point an "
                f"immutable tag. If a newer iteration has since published, pass "
                f"--iteration for the correct index."
            )
        common.log(f"::group::backfill {target} -> {source}")
        if args.dry_run:
            common.log(f"docker buildx imagetools create --tag {target} {source}")
        else:
            docker_inspect.create_manifest(target, source)
        common.log("::endgroup::")
        created += 1

    common.log(f"backfill complete: {created} created, {skipped} already tagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
