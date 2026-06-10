#!/usr/bin/env -S uv run python
"""Assemble the multi-arch manifest list for each declared (cli, rust base) pair.

For one stellar-cli version, walks its rust_versions[] and runs
`docker buildx imagetools create` to assemble the multi-arch list from
the per-arch tags. Tags are mutable, so an existing list is overwritten.
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--registry", default="docker.io/stellar/stellar-cli", metavar="REF")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the docker buildx imagetools create commands without running them.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["buildx"])

    try:
        common.reject_option_like(args.registry, "--registry")
    except ValueError as exc:
        common.die(str(exc))

    data = builds.load()
    entry = builds.find_cli(data, args.stellar_cli_version)
    if entry is None:
        common.die(f"no stellar_cli_versions entry for {args.stellar_cli_version}")

    for pin in entry["rust_versions"]:
        rust_key = builds.label_of(pin)
        list_ref, amd64_ref, arm64_ref = manifest_for_pair(
            registry=args.registry,
            cli=args.stellar_cli_version,
            rust_key=rust_key,
        )

        common.log(f"::group::manifest {list_ref}")
        if args.dry_run:
            common.log(f"docker buildx imagetools create --tag {list_ref} {amd64_ref} {arm64_ref}")
        else:
            docker_inspect.create_manifest(list_ref, amd64_ref, arm64_ref)
        common.log("::endgroup::")

    return 0


if __name__ == "__main__":
    sys.exit(main())
