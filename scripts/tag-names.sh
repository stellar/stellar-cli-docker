#!/usr/bin/env bash
# Single source of truth for image tag naming.
#
# Given the three ingredients that fully describe an image — stellar-cli
# version, rust base key, optional platform — print the canonical tag for
# that image. Callers (build, publish, smoke-test, docs) go through this
# script so tag construction stays consistent across the repo.
#
# Tag scheme:
#   multi-arch list:   <cli>[-<ref>]-rust<key>
#   per-arch:          <cli>[-<ref>]-rust<key>-<arch>
#
# where <key> is the composite rust base key (e.g. 1.94.0-slim-trixie)
# and <ref> is the full 40-char stellar-cli git SHA. Published tags
# always include <ref>; the ref-less form exists only for local
# development helpers that don't need to disambiguate by upstream
# commit.
#
# Output: exactly one tag on stdout, with no registry/repo prefix.
# Callers prepend `docker.io/stellar/stellar-cli:` (or whatever) as
# needed.

source scripts/lib/common.sh

usage() {
  cat <<'EOF'
Usage: scripts/tag-names.sh --stellar-cli-version <v> --rust-version <key> \
                            [--platform <p>] [--help]

Required:
  --stellar-cli-version <v>   e.g. 26.0.0
  --rust-version <key>        composite rust base key, e.g. 1.94.0-trixie

Options:
  --platform <p>              linux/amd64 or linux/arm64 (Rust tier-1 only).
                              When set, the tag includes the per-arch suffix.
                              When omitted, the tag refers to the multi-arch
                              manifest list.
  --stellar-cli-ref <sha>     40-char stellar-cli git SHA. When set, the tag
                              embeds the ref between the cli version and the
                              rust segment. Publish callers always pass this;
                              local helpers may omit it.
  --help                      Show this message.

Example:
  $ scripts/tag-names.sh --stellar-cli-version 26.0.0 --rust-version 1.94.0-slim-trixie
  26.0.0-rust1.94.0-slim-trixie
  $ scripts/tag-names.sh --stellar-cli-version 26.0.0 --rust-version 1.94.0-slim-trixie \
      --platform linux/amd64
  26.0.0-rust1.94.0-slim-trixie-amd64
  $ scripts/tag-names.sh --stellar-cli-version 26.0.0 --rust-version 1.94.0-slim-trixie \
      --stellar-cli-ref ee3115b93b9c11b7a4d090f676f35736d3d86172
  26.0.0-ee3115b93b9c11b7a4d090f676f35736d3d86172-rust1.94.0-slim-trixie
  $ scripts/tag-names.sh --stellar-cli-version 26.0.0 --rust-version 1.94.0-slim-trixie \
      --platform linux/amd64 \
      --stellar-cli-ref ee3115b93b9c11b7a4d090f676f35736d3d86172
  26.0.0-ee3115b93b9c11b7a4d090f676f35736d3d86172-rust1.94.0-slim-trixie-amd64
EOF
}

main() {
  local cli="" rust_key="" platform="" ref=""

  while [ $# -gt 0 ]; do
    case "$1" in
      --stellar-cli-version) require_value "$1" "${2:-}"; cli="$2"; shift 2;;
      --rust-version)        require_value "$1" "${2:-}"; rust_key="$2"; shift 2;;
      --platform)            require_value "$1" "${2:-}"; platform="$2"; shift 2;;
      --stellar-cli-ref)     require_value "$1" "${2:-}"; ref="$2"; shift 2;;
      -h|--help)             usage; exit 0;;
      *)                     err "unknown argument: $1"; usage; exit 1;;
    esac
  done

  test -n "$cli"      || { err "--stellar-cli-version is required"; usage; exit 1; }
  test -n "$rust_key" || { err "--rust-version is required"; usage; exit 1; }

  # shellcheck disable=SC2119  # no required commands beyond bash itself
  preflight_checks

  local tag="$cli"
  if [ -n "$ref" ]; then
    tag="${tag}-${ref}"
  fi
  tag="${tag}-rust${rust_key}"
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
