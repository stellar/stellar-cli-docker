#!/usr/bin/env -S uv run python
"""Re-point the `:<cli>` (and `:latest` if newest) tags at the default rust pair.

The default rust pair is the highest-version rust_versions[] key whose
suffix matches `slim-<default_distro>`. `:latest` is re-pointed only if
this cli is the newest declared one in builds.json.
"""

import argparse
import sys

import newest_pair
import tag_names
from lib import builds, common, docker_inspect


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--registry", default="docker.io/stellar/stellar-cli", metavar="REF")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the docker commands without running them.",
    )
    return parser


def publish_alias(alias: str, target: str, *, dry_run: bool) -> None:
    common.log(f"::group::alias {alias} -> {target}")
    if dry_run:
        common.log(f"docker buildx imagetools create --tag {alias} {target}")
    else:
        docker_inspect.create_manifest(alias, target)
    common.log("::endgroup::")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["buildx"])

    data = builds.load()
    try:
        default_pin = builds.derive_default_rust(data, args.stellar_cli_version)
        default_rust = builds.label_of(default_pin)
    except ValueError as exc:
        common.die(str(exc))

    target_tag = tag_names.compose_tag(
        stellar_cli_version=args.stellar_cli_version,
        rust_version=default_rust,
    )
    target = f"{args.registry}:{target_tag}"

    cli_alias = f"{args.registry}:{args.stellar_cli_version}"
    publish_alias(cli_alias, target, dry_run=args.dry_run)

    newest = newest_pair.newest_cli(data)
    if args.stellar_cli_version == newest:
        publish_alias(f"{args.registry}:latest", target, dry_run=args.dry_run)
    else:
        common.log(f"cli {args.stellar_cli_version} is not the newest ({newest}); skipping :latest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
