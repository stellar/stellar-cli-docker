#!/usr/bin/env bash
# Prints the newest declared (stellar-cli, rust) pair from builds.json.
#
# Used by CI to pick a single representative image for the smoke build, and
# usable interactively when you want to remember what `:latest` resolves to.

set -euo pipefail

script_dir="$(CDPATH= builtin cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/newest-pair.sh (--stellar-cli-version | --rust-version) [--help]

Prints exactly one field of the newest stellar_cli_versions[] entry in
builds.json. The newest entry is the last one in the array; entries are
expected to be appended in release order.

Options:
  --stellar-cli-version   Print the cli version (e.g. 26.0.0).
  --rust-version          Print the default rust version for that cli
                          (e.g. 1.94.0).
  --help                  Show this message.
EOF
}

main() {
  local field=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) field="version"; shift;;
      --rust-version)        field="default_rust"; shift;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$field" \
    || { err "one of --stellar-cli-version or --rust-version is required"; usage; exit 1; }

  preflight_checks jq

  builds_json --arg f "$field" '.stellar_cli_versions[-1][$f]'
}

main "$@"
