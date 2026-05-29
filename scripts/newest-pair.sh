#!/usr/bin/env bash
# Prints the newest declared (stellar-cli, rust base key) pair from
# builds.json.
#
# Used by CI to pick a single representative image for the smoke build, and
# usable interactively when you want to remember what `:latest` resolves to.

source scripts/lib/common.sh

usage() {
  cat <<'EOF'
Usage: scripts/newest-pair.sh (--stellar-cli-version | --rust-version) [--help]

Prints exactly one field of the newest stellar_cli_versions[] entry in
builds.json. The newest entry is the one whose .version sorts highest by
semver (numeric MAJOR.MINOR.PATCH comparison); array order is ignored so a
backported entry added out of order cannot displace a higher-semver release.

Options:
  --stellar-cli-version   Print the cli version (e.g. 26.0.0).
  --rust-version          Print the default rust base key for that cli
                          (e.g. 1.94.0-trixie).
  --help                  Show this message.
EOF
}

main() {
  local mode=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) mode="cli"; shift;;
      --rust-version)        mode="rust"; shift;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$mode" \
    || { err "one of --stellar-cli-version or --rust-version is required"; usage; exit 1; }

  preflight_checks jq

  # Sort numerically by [MAJOR, MINOR, PATCH] so 1.100.0 ranks above
  # 1.99.0 (default jq sort on strings is lexicographic and would invert
  # that), and so an entry added out of order — backport, manual edit —
  # cannot displace a higher-semver release.
  local newest_cli
  newest_cli="$(builds_json '
    .stellar_cli_versions
    | sort_by(.version | split(".") | map(tonumber))
    | .[-1].version
  ')"

  case "$mode" in
    cli)  printf '%s\n' "$newest_cli";;
    rust) derive_default_rust_for_cli "$newest_cli"; printf '\n';;
  esac
}

main "$@"
