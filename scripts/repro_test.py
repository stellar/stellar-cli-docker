#!/usr/bin/env -S uv run python
"""Verify WASM reproducibility by building each contract twice in fresh containers.

Clones an upstream contracts repo (default: stellar/soroban-examples@main)
and confirms that `stellar contract build --locked` produces byte-identical
.wasm files across two cold builds, per contract. Same-arch only.
"""

import argparse
import atexit
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from lib import common, runner

DEFAULT_REPO = "https://github.com/stellar/soroban-examples.git"
DEFAULT_REV = "main"
DEFAULT_CONTRACTS = ("token", "liquidity_pool", "atomic_swap")

_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", required=True, metavar="REF")
    parser.add_argument("--repo", default=DEFAULT_REPO, metavar="URL")
    parser.add_argument("--rev", default=DEFAULT_REV, metavar="REF")
    parser.add_argument("--contract", action="append", default=[], dest="contracts", metavar="NAME")
    parser.add_argument("--keep-workdir", action="store_true")
    return parser


def build_and_hash(image: str, contract_dir: Path) -> str:
    script = (
        "set -eo pipefail\n"
        "rm -rf /source/target\n"
        "/usr/local/bin/stellar contract build --locked >&2\n"
        'sha256sum /source/target/wasm32v1-none/release/*.wasm | awk "{print \\$1}"\n'
    )
    out = runner.capture(
        [
            "docker",
            "run",
            "--rm",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "CARGO_HOME=/tmp/cargo",
            "--entrypoint",
            "bash",
            "-v",
            f"{contract_dir}:/source",
            image,
            "-c",
            script,
        ]
    )
    return out.strip()


def assert_sha256(value: str, label: str) -> bool:
    if _SHA256_HEX.match(value):
        return True
    common.err(f"  {label} produced an invalid hash: '{value}'")
    return False


def test_one_contract(image: str, workdir: Path, name: str) -> bool:
    contract_dir = workdir / name
    common.log("")
    common.log(f"=== {name} ===")
    if not contract_dir.is_dir():
        common.err(f"no contract directory at {contract_dir}")
        return False
    if not (contract_dir / "Cargo.toml").is_file():
        common.err(f"{name}/Cargo.toml missing")
        return False
    if not (contract_dir / "Cargo.lock").is_file():
        common.err(f"{name}/Cargo.lock missing (required for --locked builds)")
        return False

    hash_a = build_and_hash(image, contract_dir)
    if not assert_sha256(hash_a, "build A"):
        return False
    common.log(f"  build A: {hash_a}")
    hash_b = build_and_hash(image, contract_dir)
    if not assert_sha256(hash_b, "build B"):
        return False
    common.log(f"  build B: {hash_b}")

    if hash_a == hash_b:
        common.log("  ok — reproducible")
        return True
    common.err("  WASM hash mismatch — build is NOT reproducible")
    return False


def clone(repo: str, rev: str, workdir: Path) -> None:
    # Both values are untrusted CLI input. git permutes its argv and treats any
    # '-'-prefixed token as an option wherever it sits, so a rev like
    # '--upload-pack=<cmd>' (with a file:// repo) would run an arbitrary binary.
    # Reject the dash prefix and pin '--end-of-options' before the positionals
    # so git can never reinterpret them as flags.
    common.reject_option_like(repo, "repo URL")
    common.reject_option_like(rev, "rev")
    common.log(f"cloning {repo} @ {rev} into {workdir} ...")
    runner.run(["git", "-C", str(workdir), "init", "-q"])
    runner.run(["git", "-C", str(workdir), "remote", "add", "--", "origin", repo])
    runner.run(
        ["git", "-C", str(workdir), "fetch", "--depth=1", "-q", "--end-of-options", "origin", rev]
    )
    runner.run(["git", "-C", str(workdir), "checkout", "-q", "FETCH_HEAD"])


def make_cleanup(workdir: Path, keep: bool):
    def cleanup() -> None:
        if keep:
            common.log(f"keeping workdir on exit: {workdir}")
            return
        if not workdir.exists():
            return
        shutil.rmtree(workdir, ignore_errors=True)

    return cleanup


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["git", "buildx"])

    try:
        common.reject_option_like(args.image, "--image")
        common.reject_option_like(args.repo, "--repo")
        common.reject_option_like(args.rev, "--rev")
    except ValueError as exc:
        common.die(str(exc))

    contracts = args.contracts or list(DEFAULT_CONTRACTS)
    workdir = Path(tempfile.mkdtemp(prefix="repro-test."))
    atexit.register(make_cleanup(workdir, args.keep_workdir))

    clone(args.repo, args.rev, workdir)

    ok = True
    for c in contracts:
        if not test_one_contract(args.image, workdir, c):
            ok = False

    if ok:
        common.log("")
        common.log(f"repro-test: all {len(contracts)} contracts produce stable WASM")
        return 0
    common.err("")
    common.err("repro-test: one or more contracts FAILED reproducibility")
    return 1


if __name__ == "__main__":
    sys.exit(main())
