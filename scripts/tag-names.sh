#!/usr/bin/env bash
# Single source of truth for image tag naming.
#
# Given the three ingredients that fully describe an image — stellar-cli
# version, rust version, optional platform — print the canonical tag for
# that image. Callers (build, publish, smoke-test, docs) go through this
# script so tag construction stays consistent across the repo.
#
# Tag scheme:
#   multi-arch list:    <cli>-rust<rust>
#   per-arch:           <cli>-rust<rust>-<arch>
#
# Output: exactly one tag on stdout, with no registry/repo prefix. Callers
# prepend `docker.io/stellar/stellar-cli:` (or whatever) as needed.

set -euo pipefail

script_dir="$(CDPATH='' builtin cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/common.sh
source "$script_dir/lib/common.sh"

usage() {
  cat <<'EOF'
Usage: scripts/tag-names.sh --stellar-cli-version <v> --rust-version <v> \
                            [--platform <p>] [--help]

Required:
  --stellar-cli-version <v>   e.g. 26.0.0
  --rust-version <v>          e.g. 1.94.0

Options:
  --platform <p>              linux/amd64 or linux/arm64 (Rust tier-1 only).
                              When set, the tag includes the per-arch suffix.
                              When omitted, the tag refers to the multi-arch
                              manifest list.
  --help                      Show this message.

Example:
  $ scripts/tag-names.sh --stellar-cli-version 26.0.0 --rust-version 1.94.0
  26.0.0-rust1.94.0
  $ scripts/tag-names.sh --stellar-cli-version 26.0.0 --rust-version 1.94.0 \
      --platform linux/amd64
  26.0.0-rust1.94.0-amd64
EOF
}

main() {
  local cli="" rust="" platform=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) cli="$2"; shift 2;;
      --rust-version)        rust="$2"; shift 2;;
      --platform)            platform="$2"; shift 2;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$cli"  || { err "--stellar-cli-version is required"; usage; exit 1; }
  test -n "$rust" || { err "--rust-version is required"; usage; exit 1; }

  # shellcheck disable=SC2119  # no required commands beyond bash itself
  preflight_checks

  local tag="${cli}-rust${rust}"
  if [ -n "$platform" ]; then
    tag="${tag}-$(arch_for_platform "$platform")"
  fi

  printf '%s\n' "$tag"
}

# Translate a buildx --platform value to the short arch suffix used in tags.
arch_for_platform() {
  local platform="$1"
  case "$platform" in
    linux/amd64) printf '%s' amd64;;
    linux/arm64) printf '%s' arm64;;
    *)           die "unsupported platform: $platform";;
  esac
}

main "$@"
