#!/usr/bin/env -S uv run python
"""Stage a new stellar-cli release into builds.json.

Adds (new cli) or refreshes (existing cli) the entry, picks rust base
pairings, resolves the upstream cli ref + any missing rust image digests,
validates the result, and prints the chosen GitHub Release tag as the
final stdout line.

All log output goes to stderr; stdout is just the tag.
"""

import argparse
import re
import sys
from collections.abc import Iterable

import refresh_rust_digests
import refresh_stellar_cli_digests
import validate_json
from lib import builds, common, gh_cli, runner, rust_keys, semver

ITERATION_RE = re.compile(r"^v(?P<cli>[0-9]+\.[0-9]+\.[0-9]+)(?:-(?P<n>[0-9]+))?$")


def current_rust_base_suffix(data: dict) -> str:
    distro = data.get("default_distro") or ""
    if not distro:
        raise ValueError("builds.json is missing default_distro")
    return f"slim-{distro}"


def pick_default_rust_base_keys(suffix: str) -> list[str]:
    """Return the last two unique minor rust base keys for the suffix.

    Sourced from Docker Hub library/rust tags so we never pick a key
    whose image hasn't been published yet. Output: ascending composite keys.
    """
    payload = runner.http_get_json(
        f"https://hub.docker.com/v2/repositories/library/rust/tags?page_size=100&name={suffix}"
    )
    full = re.compile(rf"^[0-9]+\.[0-9]+\.[0-9]+-{re.escape(suffix)}$")
    candidates = [t["name"] for t in payload.get("results", []) if full.match(t["name"])]
    # Sort newest first (descending by version), keep first occurrence per minor.
    candidates.sort(key=lambda k: semver.parse(rust_keys.version_of(k)), reverse=True)
    picked: list[str] = []
    seen_minors: set[tuple[int, int]] = set()
    for key in candidates:
        v = semver.parse(rust_keys.version_of(key))
        minor = (v.major, v.minor)
        if minor in seen_minors:
            continue
        seen_minors.add(minor)
        picked.append(key)
        if len(picked) == 2:
            break
    picked.reverse()  # ascending output to match bash
    return picked


def add_cli_entry(data: dict, cli: str, rust_versions: Iterable[str]) -> None:
    rust_list = sorted(rust_versions, key=lambda k: semver.parse(rust_keys.version_of(k)))
    entry = {"ref": "", "rust_versions": rust_list, "version": cli}
    data.setdefault("stellar_cli_versions", []).append(entry)
    data["stellar_cli_versions"].sort(key=lambda e: semver.parse(e["version"]))
    digests = data.setdefault("rust_image_digests", {})
    for key in rust_list:
        digests.setdefault(key, "")


def extend_cli_entry(data: dict, cli: str, rust_versions: Iterable[str]) -> None:
    entry = builds.find_cli(data, cli)
    if entry is None:
        raise ValueError(f"unknown stellar-cli version: {cli}")
    merged = set(entry["rust_versions"]) | set(rust_versions)
    entry["rust_versions"] = sorted(merged, key=lambda k: semver.parse(rust_keys.version_of(k)))
    data["stellar_cli_versions"].sort(key=lambda e: semver.parse(e["version"]))
    digests = data.setdefault("rust_image_digests", {})
    for key in entry["rust_versions"]:
        digests.setdefault(key, "")


def pick_release_tag(cli: str, repo: str) -> str:
    """Next available GitHub Release tag: v<cli>, or v<cli>-N for refreshes."""
    existing = gh_cli.list_release_tags(repo)
    if f"v{cli}" not in existing:
        return f"v{cli}"
    max_iter = 0
    for tag in existing:
        match = ITERATION_RE.match(tag)
        if not match or match["cli"] != cli or match["n"] is None:
            continue
        max_iter = max(max_iter, int(match["n"]))
    return f"v{cli}-{max_iter + 1}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument("--rust-versions", default="", metavar="CSV")
    parser.add_argument(
        "--repo",
        default="stellar/stellar-cli-docker",
        metavar="SLUG",
        help="GitHub repo for release-tag lookups (default: stellar/stellar-cli-docker)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["gh", "git", "buildx"])

    cli = args.stellar_cli_version
    before = builds.DEFAULT_PATH.read_bytes()
    data = builds.load()

    mode = "refresh" if builds.find_cli(data, cli) is not None else "new"
    common.log(f"mode: {mode}")

    try:
        if args.rust_versions:
            rusts = [k.strip() for k in args.rust_versions.split(",") if k.strip()]
            common.log(f"rust base keys (from --rust-versions): {' '.join(rusts)}")
        else:
            suffix = current_rust_base_suffix(data)
            common.log(
                f"picking the last 2 minor rust base keys with suffix "
                f"'{suffix}' from Docker Hub ..."
            )
            rusts = pick_default_rust_base_keys(suffix)
            common.log(f"rust base keys (auto): {' '.join(rusts)}")
        if not rusts:
            common.die("no rust base keys selected")

        common.log(f"applying changes to {builds.DEFAULT_PATH} ...")
        if mode == "new":
            add_cli_entry(data, cli, rusts)
        else:
            extend_cli_entry(data, cli, rusts)
        builds.dump(data)
    except ValueError as exc:
        common.die(str(exc))

    common.log("resolving upstream stellar-cli ref ...")
    refresh_stellar_cli_digests.main([])

    common.log("resolving rust image digests ...")
    refresh_rust_digests.main([])

    common.log("validating builds.json ...")
    if validate_json.main([]) != 0:
        common.die("validation failed; see above")

    after = builds.DEFAULT_PATH.read_bytes()
    if before == after:
        common.die(
            f"no changes to builds.json — nothing to release. The auto-picked rust "
            f"versions and cli ref already match what's declared for stellar-cli {cli}."
        )

    release_tag = pick_release_tag(cli, args.repo)
    common.log(f"release tag: {release_tag}")
    common.log("")
    common.log(
        f"release-prepare: builds.json staged for stellar-cli {cli} with rust {' '.join(rusts)}"
    )

    print(release_tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())
