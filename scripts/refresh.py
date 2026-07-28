#!/usr/bin/env -S uv run python
"""Resolve and append rust base pins (and the cli ref) for one stellar-cli version.

For the given `--stellar-cli-version`:

  1. Pick the rust base labels to pair against — either `--rust-versions`
     (a CSV of labels) or, by default, the last two minor `slim-<distro>`
     tags published on Docker Hub.
  2. Resolve the upstream stellar-cli git ref (only when it's blank, or for a
     brand-new entry) so previously-published refs stay pinned.
  3. Resolve each label's current upstream multi-arch index digest and append
     the fully-qualified pin `<label>@<digest>` to the entry — but only when
     that exact pin isn't already present.

Appending (never rewriting) keeps already-published pins immutable: a rebuilt
base shows up as the same label with a fresh digest, i.e. a new pin, while the
old pin — and its immutable image tag — is retained. All log output goes to
stderr.
"""

import argparse
import re
import sys
from collections.abc import Iterable

from lib import builds, common, docker_inspect, git_remote, runner, rust_keys, semver

STELLAR_CLI_REPO = "https://github.com/stellar/stellar-cli.git"

_PINNED_REF = re.compile(r"^[0-9a-f]{40}$")


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
    picked.reverse()  # return ascending so callers iterate oldest-to-newest
    return picked


def resolve_ref(version: str) -> str:
    sha = git_remote.resolve_tag_commit(STELLAR_CLI_REPO, f"v{version}")
    if not sha:
        raise ValueError(f"could not resolve tag v{version} in {STELLAR_CLI_REPO}")
    return sha


def append_pins(entry: dict, labels: Iterable[str]) -> bool:
    """Resolve each label's digest and append `<label>@<digest>` pins.

    Returns True if any new pin was appended. A pin already present (same
    label and digest) is left untouched.
    """
    changed = False
    for label in labels:
        common.log(f"resolving rust:{label} ...")
        digest = docker_inspect.index_digest(f"rust:{label}")
        if not digest:
            raise ValueError(f"empty digest returned for rust:{label}")
        pin = f"{label}@{digest}"
        if pin in entry["rust_versions"]:
            common.log(f"  -> {pin} already declared; skipping")
            continue
        common.log(f"  -> appending {pin}")
        entry["rust_versions"].append(pin)
        changed = True
    entry["rust_versions"].sort(
        key=lambda p: semver.parse(rust_keys.version_of(builds.label_of(p)))
    )
    return changed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stellar-cli-version", required=True, metavar="V")
    parser.add_argument(
        "--rust-versions",
        default="",
        metavar="CSV",
        help="Comma-separated rust base labels; defaults to the last two minor "
        "slim-<distro> tags on Docker Hub.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.preflight_checks(["git", "buildx"])

    cli = args.stellar_cli_version

    try:
        data = builds.load()
        entry = builds.find_cli(data, cli)
        if args.rust_versions:
            labels = [k.strip() for k in args.rust_versions.split(",") if k.strip()]
            common.log(f"rust base labels (from --rust-versions): {' '.join(labels)}")
        else:
            suffix = current_rust_base_suffix(data)
            common.log(f"picking last 2 minor rust base labels '{suffix}' from Docker Hub ...")
            labels = pick_default_rust_base_keys(suffix)
            common.log(f"rust base labels (auto): {' '.join(labels)}")
        if not labels:
            common.die("no rust base labels selected")

        if entry is None:
            common.log(f"new stellar-cli {cli}; resolving upstream ref ...")
            entry = {"ref": resolve_ref(cli), "rust_versions": [], "version": cli}
            data.setdefault("stellar_cli_versions", []).append(entry)
        elif not _PINNED_REF.match(entry.get("ref") or ""):
            common.log(f"stellar-cli {cli} has no pinned ref; resolving ...")
            entry["ref"] = resolve_ref(cli)

        append_pins(entry, labels)
        data["stellar_cli_versions"].sort(key=lambda e: semver.parse(e["version"]))
    except ValueError as exc:
        common.die(str(exc))
    except OSError as exc:
        # Network failure from the Docker Hub tag lookup (urllib raises
        # URLError, an OSError) or a filesystem error.
        common.die(f"failed to refresh builds.json: {exc}")

    if args.dry_run:
        common.log("(dry-run; not writing builds.json)")
        return 0

    builds.dump(data)
    common.log(f"wrote {builds.DEFAULT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
